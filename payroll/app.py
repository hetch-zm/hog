"""Hope of Glory site + Payroll (3-stage approval) — single Flask app.

Serves:
  /              -> existing HOG static site (index.html, styles.css, etc.)
  /payroll/*     -> payroll system (initiator → approver 1 → approver 2)
"""
import os
import sqlite3
import io
import zipfile
from datetime import datetime
from pathlib import Path
from flask import (
    Flask, Blueprint, request, redirect, url_for, render_template,
    session, flash, send_file, send_from_directory, abort,
)
from werkzeug.utils import secure_filename

import payroll as pr

BASE = Path(__file__).parent
HOG_ROOT = BASE.parent

DATA_DIR = Path(os.environ.get("PAYROLL_DATA_DIR", str(BASE)))
DB_PATH = DATA_DIR / "payroll.db"
UPLOAD_DIR = DATA_DIR / "uploads"
PAYSLIP_DIR = DATA_DIR / "payslips"

app = Flask(
    __name__,
    template_folder=str(BASE / "templates"),
    static_folder=str(HOG_ROOT),
    static_url_path="",
)
app.secret_key = os.environ.get("SECRET_KEY", "change-me-in-production")
app.config["MAX_CONTENT_LENGTH"] = 5 * 1024 * 1024


def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = db()
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS batches (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      name TEXT NOT NULL,
      pay_month TEXT,
      status TEXT NOT NULL,
      initiator TEXT,
      initiated_at TEXT,
      approver1 TEXT,
      approver1_at TEXT,
      approver2 TEXT,
      approver2_at TEXT,
      rejection_reason TEXT,
      rejected_by TEXT
    );
    CREATE TABLE IF NOT EXISTS employees (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      batch_id INTEGER NOT NULL,
      employee_no TEXT,
      full_name TEXT,
      position TEXT,
      pay_month TEXT,
      basic_salary REAL,
      allowances REAL,
      deductions REAL,
      leave_days REAL,
      bank_name TEXT,
      account_number TEXT,
      branch TEXT,
      gross_pay REAL,
      net_pay REAL,
      FOREIGN KEY (batch_id) REFERENCES batches(id)
    );
    """)
    conn.commit()
    conn.close()


def current_user():
    return session.get("user"), session.get("role")


def require_role(*roles):
    name, role = current_user()
    if not name or role not in roles:
        flash(f"You must be signed in as {' or '.join(roles)} to do that.", "error")
        return False
    return True


# ---------- HOG static site ----------

@app.route("/")
def hog_home():
    return send_from_directory(str(HOG_ROOT), "index.html")


# Flask's static handler at static_url_path="" already serves
# /styles.css, /script.js, /hog_farm/*, /ch_gallery/*, /logos/*, etc.


# ---------- Payroll Blueprint ----------

bp = Blueprint("payroll", __name__, url_prefix="/payroll")


@bp.route("/")
def index():
    if session.get("user"):
        return redirect(url_for("payroll.batches"))
    return render_template("index.html")


@bp.route("/login", methods=["POST"])
def login():
    name = (request.form.get("name") or "").strip()
    role = request.form.get("role")
    if not name or role not in {"initiator", "approver1", "approver2"}:
        flash("Enter a name and choose a role.", "error")
        return redirect(url_for("payroll.index"))
    session["user"] = name
    session["role"] = role
    return redirect(url_for("payroll.batches"))


@bp.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("payroll.index"))


@bp.route("/template")
def download_template():
    path = DATA_DIR / "payroll_template.xlsx"
    if not path.exists():
        pr.create_template(path)
    return send_file(path, as_attachment=True, download_name="payroll_template.xlsx")


@bp.route("/upload", methods=["GET", "POST"])
def upload():
    if not require_role("initiator"):
        return redirect(url_for("payroll.index"))

    if request.method == "POST":
        file = request.files.get("file")
        batch_name = (request.form.get("batch_name") or "").strip()
        if not file or not file.filename:
            flash("Please attach an Excel file.", "error")
            return redirect(url_for("payroll.upload"))
        if not batch_name:
            flash("Give the batch a name.", "error")
            return redirect(url_for("payroll.upload"))

        fname = secure_filename(file.filename)
        if not fname.lower().endswith((".xlsx", ".xlsm")):
            flash("File must be .xlsx", "error")
            return redirect(url_for("payroll.upload"))

        UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
        save_path = UPLOAD_DIR / f"{datetime.now():%Y%m%d_%H%M%S}_{fname}"
        file.save(save_path)

        try:
            employees = pr.parse_excel(save_path)
        except Exception as e:
            flash(f"Could not read Excel: {e}", "error")
            return redirect(url_for("payroll.upload"))

        pay_month = employees[0]["pay_month"] if employees else ""
        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        conn = db()
        cur = conn.execute(
            """INSERT INTO batches (name, pay_month, status, initiator, initiated_at)
               VALUES (?, ?, 'pending_approver_1', ?, ?)""",
            (batch_name, pay_month, session["user"], now),
        )
        batch_id = cur.lastrowid
        for e in employees:
            conn.execute(
                """INSERT INTO employees (batch_id, employee_no, full_name, position,
                   pay_month, basic_salary, allowances, deductions, leave_days,
                   bank_name, account_number, branch, gross_pay, net_pay)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (batch_id, e["employee_no"], e["full_name"], e["position"],
                 e["pay_month"], e["basic_salary"], e["allowances"], e["deductions"],
                 e["leave_days"], e["bank_name"], e["account_number"], e["branch"],
                 e["gross_pay"], e["net_pay"]),
            )
        conn.commit()
        conn.close()
        flash(f"Batch #{batch_id} submitted with {len(employees)} employees.", "success")
        return redirect(url_for("payroll.batch_detail", batch_id=batch_id))

    return render_template("upload.html")


@bp.route("/batches")
def batches():
    name, role = current_user()
    if not name:
        return redirect(url_for("payroll.index"))
    conn = db()
    rows = conn.execute("SELECT * FROM batches ORDER BY id DESC").fetchall()
    conn.close()
    return render_template("batches.html", batches=rows, role=role)


@bp.route("/batch/<int:batch_id>")
def batch_detail(batch_id):
    name, role = current_user()
    if not name:
        return redirect(url_for("payroll.index"))
    conn = db()
    batch = conn.execute("SELECT * FROM batches WHERE id=?", (batch_id,)).fetchone()
    if not batch:
        conn.close()
        abort(404)
    employees = conn.execute(
        "SELECT * FROM employees WHERE batch_id=? ORDER BY employee_no",
        (batch_id,),
    ).fetchall()
    conn.close()
    totals = {
        "basic": sum(e["basic_salary"] or 0 for e in employees),
        "allowances": sum(e["allowances"] or 0 for e in employees),
        "deductions": sum(e["deductions"] or 0 for e in employees),
        "gross": sum(e["gross_pay"] or 0 for e in employees),
        "net": sum(e["net_pay"] or 0 for e in employees),
    }
    return render_template(
        "batch_detail.html", batch=batch, employees=employees,
        totals=totals, role=role,
    )


@bp.route("/batch/<int:batch_id>/approve", methods=["POST"])
def approve(batch_id):
    name, role = current_user()
    if not name:
        return redirect(url_for("payroll.index"))
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    conn = db()
    batch = conn.execute("SELECT * FROM batches WHERE id=?", (batch_id,)).fetchone()
    if not batch:
        conn.close()
        abort(404)

    if role == "approver1" and batch["status"] == "pending_approver_1":
        if batch["initiator"] == name:
            flash("You cannot approve a batch you initiated.", "error")
        else:
            conn.execute(
                """UPDATE batches SET status='pending_approver_2',
                   approver1=?, approver1_at=? WHERE id=?""",
                (name, now, batch_id),
            )
            conn.commit()
            flash("Approved at stage 1. Now awaiting Approver 2.", "success")
    elif role == "approver2" and batch["status"] == "pending_approver_2":
        if batch["approver1"] == name or batch["initiator"] == name:
            flash("You cannot approve a batch you initiated or already approved.", "error")
        else:
            conn.execute(
                """UPDATE batches SET status='approved',
                   approver2=?, approver2_at=? WHERE id=?""",
                (name, now, batch_id),
            )
            conn.commit()
            flash("Final approval recorded. Payslips can now be downloaded.", "success")
    else:
        flash("This batch is not awaiting your approval.", "error")
    conn.close()
    return redirect(url_for("payroll.batch_detail", batch_id=batch_id))


@bp.route("/batch/<int:batch_id>/reject", methods=["POST"])
def reject(batch_id):
    name, role = current_user()
    if not name or role not in {"approver1", "approver2"}:
        flash("Only approvers can reject.", "error")
        return redirect(url_for("payroll.batch_detail", batch_id=batch_id))
    reason = (request.form.get("reason") or "").strip() or "No reason given"
    conn = db()
    batch = conn.execute("SELECT * FROM batches WHERE id=?", (batch_id,)).fetchone()
    if not batch:
        conn.close()
        abort(404)
    if batch["status"] in {"approved", "rejected"}:
        flash("Batch is already finalised.", "error")
    else:
        conn.execute(
            """UPDATE batches SET status='rejected',
               rejected_by=?, rejection_reason=? WHERE id=?""",
            (f"{name} ({role})", reason, batch_id),
        )
        conn.commit()
        flash("Batch rejected.", "success")
    conn.close()
    return redirect(url_for("payroll.batch_detail", batch_id=batch_id))


def _batch_meta(batch):
    return {
        "initiator": batch["initiator"] or "—",
        "initiated_at": batch["initiated_at"] or "",
        "approver1": batch["approver1"] or "—",
        "approver1_at": batch["approver1_at"] or "",
        "approver2": batch["approver2"] or "—",
        "approver2_at": batch["approver2_at"] or "",
    }


@bp.route("/batch/<int:batch_id>/payslip/<int:emp_id>")
def payslip(batch_id, emp_id):
    if not session.get("user"):
        return redirect(url_for("payroll.index"))
    conn = db()
    batch = conn.execute("SELECT * FROM batches WHERE id=?", (batch_id,)).fetchone()
    emp = conn.execute(
        "SELECT * FROM employees WHERE id=? AND batch_id=?", (emp_id, batch_id)
    ).fetchone()
    conn.close()
    if not batch or not emp:
        abort(404)
    if batch["status"] != "approved":
        flash("Payslips are available only after final approval.", "error")
        return redirect(url_for("payroll.batch_detail", batch_id=batch_id))

    out_dir = PAYSLIP_DIR / f"batch_{batch_id}"
    out_dir.mkdir(parents=True, exist_ok=True)
    safe = "".join(c if c.isalnum() else "_" for c in emp["employee_no"])
    out_path = out_dir / f"payslip_{safe}.pdf"
    pr.generate_payslip_pdf(dict(emp), _batch_meta(batch), str(out_path))
    return send_file(out_path, as_attachment=True,
                     download_name=f"payslip_{emp['employee_no']}_{emp['pay_month']}.pdf")


@bp.route("/batch/<int:batch_id>/payslips.zip")
def payslips_zip(batch_id):
    if not session.get("user"):
        return redirect(url_for("payroll.index"))
    conn = db()
    batch = conn.execute("SELECT * FROM batches WHERE id=?", (batch_id,)).fetchone()
    employees = conn.execute(
        "SELECT * FROM employees WHERE batch_id=?", (batch_id,)
    ).fetchall()
    conn.close()
    if not batch:
        abort(404)
    if batch["status"] != "approved":
        flash("Payslips are available only after final approval.", "error")
        return redirect(url_for("payroll.batch_detail", batch_id=batch_id))

    out_dir = PAYSLIP_DIR / f"batch_{batch_id}"
    out_dir.mkdir(parents=True, exist_ok=True)
    meta = _batch_meta(batch)

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for emp in employees:
            safe = "".join(c if c.isalnum() else "_" for c in emp["employee_no"])
            out_path = out_dir / f"payslip_{safe}.pdf"
            pr.generate_payslip_pdf(dict(emp), meta, str(out_path))
            zf.write(out_path, arcname=f"payslip_{emp['employee_no']}_{emp['full_name']}.pdf")
    buf.seek(0)
    return send_file(buf, mimetype="application/zip", as_attachment=True,
                     download_name=f"payslips_batch_{batch_id}.zip")


app.register_blueprint(bp)


if __name__ == "__main__":
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    PAYSLIP_DIR.mkdir(parents=True, exist_ok=True)
    init_db()
    app.run(host="127.0.0.1", port=5000, debug=True)
