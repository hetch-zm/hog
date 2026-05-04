"""Hope of Glory site + Payroll (3-stage approval) — single Flask app.

Serves:
  /              -> existing HOG static site (index.html, styles.css, etc.)
  /payroll/*     -> payroll system (initiator -> approver 1 -> approver 2)
"""
import os
import re
import sqlite3
import io
import zipfile
from datetime import datetime
from functools import wraps
from pathlib import Path
from flask import (
    Flask, Blueprint, request, redirect, url_for, render_template,
    session, flash, send_file, send_from_directory, abort,
)
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash

import payroll as pr

BASE = Path(__file__).parent
HOG_ROOT = BASE.parent

DATA_DIR = Path(os.environ.get("PAYROLL_DATA_DIR", str(BASE)))
DB_PATH = DATA_DIR / "payroll.db"
UPLOAD_DIR = DATA_DIR / "uploads"
PAYSLIP_DIR = DATA_DIR / "payslips"

ROLES = ("initiator", "approver1", "approver2", "admin")

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
    CREATE TABLE IF NOT EXISTS users (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      username TEXT UNIQUE NOT NULL,
      password_hash TEXT NOT NULL,
      full_name TEXT NOT NULL,
      role TEXT NOT NULL,
      active INTEGER NOT NULL DEFAULT 1,
      created_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS audit_log (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      batch_id INTEGER NOT NULL,
      action TEXT NOT NULL,
      actor_username TEXT,
      actor_full_name TEXT,
      actor_role TEXT,
      detail TEXT,
      created_at TEXT NOT NULL,
      FOREIGN KEY (batch_id) REFERENCES batches(id)
    );
    CREATE TABLE IF NOT EXISTS paye_bands (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      lower_bound REAL NOT NULL,
      upper_bound REAL,
      rate REAL NOT NULL,
      sort_order INTEGER NOT NULL
    );
    CREATE TABLE IF NOT EXISTS app_settings (
      key TEXT PRIMARY KEY,
      value TEXT NOT NULL,
      label TEXT,
      value_type TEXT NOT NULL DEFAULT 'number'
    );
    """)

    cols = {r["name"] for r in conn.execute("PRAGMA table_info(batches)").fetchall()}
    for c in ("initiator_username", "approver1_username", "approver2_username"):
        if c not in cols:
            conn.execute(f"ALTER TABLE batches ADD COLUMN {c} TEXT")

    emp_cols = {r["name"] for r in conn.execute("PRAGMA table_info(employees)").fetchall()}
    for c in ("napsa", "nhima", "paye", "taxable_income"):
        if c not in emp_cols:
            conn.execute(f"ALTER TABLE employees ADD COLUMN {c} REAL DEFAULT 0")
    conn.commit()

    if conn.execute("SELECT COUNT(*) FROM paye_bands").fetchone()[0] == 0:
        # 2026 Zambia monthly PAYE bands. Adjustable via /payroll/settings.
        conn.executemany(
            "INSERT INTO paye_bands (lower_bound, upper_bound, rate, sort_order) VALUES (?, ?, ?, ?)",
            [
                (0.0,    5100.0,  0.00, 1),
                (5100.0, 7100.0,  0.20, 2),
                (7100.0, 9200.0,  0.30, 3),
                (9200.0, None,    0.37, 4),
            ],
        )
        conn.commit()

    defaults = [
        ("napsa_rate",         "0.05",     "NAPSA employee rate (fraction, e.g. 0.05 = 5%)", "number"),
        ("napsa_ceiling",      "28455.86", "NAPSA monthly ceiling on pensionable earnings (ZMW)", "number"),
        ("nhima_rate",         "0.01",     "NHIMA employee rate (fraction, e.g. 0.01 = 1%)", "number"),
        ("napsa_deductible",   "1",        "Subtract NAPSA from gross before computing PAYE", "bool"),
        ("nhima_deductible",   "0",        "Subtract NHIMA from gross before computing PAYE", "bool"),
        ("currency_code",      "ZMW",      "Currency code shown on payslips", "text"),
        ("company_name",       "Hope of Glory", "Company name on payslips", "text"),
    ]
    for key, value, label, vtype in defaults:
        conn.execute(
            "INSERT OR IGNORE INTO app_settings (key, value, label, value_type) VALUES (?, ?, ?, ?)",
            (key, value, label, vtype),
        )
    conn.commit()

    n = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    if n == 0:
        admin_user = os.environ.get("PAYROLL_ADMIN_USER", "admin")
        admin_pass = os.environ.get("PAYROLL_ADMIN_PASSWORD", "admin123")
        admin_name = os.environ.get("PAYROLL_ADMIN_FULLNAME", "Administrator")
        conn.execute(
            """INSERT INTO users (username, password_hash, full_name, role, active, created_at)
               VALUES (?, ?, ?, 'admin', 1, ?)""",
            (admin_user, generate_password_hash(admin_pass), admin_name,
             datetime.now().strftime("%Y-%m-%d %H:%M")),
        )
        conn.commit()
        if admin_pass == "admin123":
            print(f"[init] Created default admin '{admin_user}' / 'admin123' — change this immediately.")
        else:
            print(f"[init] Created admin user '{admin_user}'.")
    conn.close()


def current_user():
    return session.get("username"), session.get("role"), session.get("full_name")


def require_role(*roles):
    name, role, _ = current_user()
    if not name or role not in roles:
        flash(f"You must be signed in as {' or '.join(roles)} to do that.", "error")
        return False
    return True


def require_login(view):
    @wraps(view)
    def wrapped(*a, **kw):
        if not session.get("username"):
            return redirect(url_for("payroll.index"))
        return view(*a, **kw)
    return wrapped


def require_admin(view):
    @wraps(view)
    def wrapped(*a, **kw):
        if session.get("role") != "admin":
            flash("Admin only.", "error")
            return redirect(url_for("payroll.batches"))
        return view(*a, **kw)
    return wrapped


def load_tax_config(conn):
    bands = [
        dict(r) for r in conn.execute(
            "SELECT lower_bound, upper_bound, rate FROM paye_bands ORDER BY sort_order"
        ).fetchall()
    ]
    rows = conn.execute("SELECT key, value, value_type FROM app_settings").fetchall()
    settings = {}
    for r in rows:
        v = r["value"]
        if r["value_type"] == "number":
            try:
                v = float(v)
            except ValueError:
                v = 0.0
        elif r["value_type"] == "bool":
            v = v in ("1", "true", "True", "yes", "on")
        settings[r["key"]] = v
    return bands, settings


def compute_statutory(gross, bands, settings):
    """Returns dict with napsa, nhima, paye, taxable_income, all numeric.
    Uses values at upload time; later setting changes do not retro-affect stored employees."""
    napsa_rate    = float(settings.get("napsa_rate", 0.05))
    napsa_ceiling = float(settings.get("napsa_ceiling", 0.0))
    nhima_rate    = float(settings.get("nhima_rate", 0.01))
    napsa_ded     = bool(settings.get("napsa_deductible", True))
    nhima_ded     = bool(settings.get("nhima_deductible", False))

    napsa_base = min(gross, napsa_ceiling) if napsa_ceiling > 0 else gross
    napsa = round(napsa_base * napsa_rate, 2)
    nhima = round(gross * nhima_rate, 2)

    taxable = gross
    if napsa_ded:
        taxable -= napsa
    if nhima_ded:
        taxable -= nhima
    taxable = max(taxable, 0.0)

    paye = 0.0
    for band in bands:
        lo = float(band["lower_bound"] or 0)
        hi = band["upper_bound"]
        rate = float(band["rate"] or 0)
        if taxable <= lo:
            break
        upper = float(hi) if hi is not None else taxable
        slice_amount = max(0.0, min(taxable, upper) - lo)
        paye += slice_amount * rate
    paye = round(paye, 2)

    return {
        "napsa": napsa,
        "nhima": nhima,
        "paye": paye,
        "taxable_income": round(taxable, 2),
    }


def _year_of_pay_month(pm):
    m = re.search(r"(\d{4})", pm or "")
    return m.group(1) if m else None


def compute_ytd(conn, employee_no, pay_month):
    year = _year_of_pay_month(pay_month)
    if not year:
        return None
    rows = conn.execute(
        """SELECT e.gross_pay, e.napsa, e.nhima, e.paye, e.deductions, e.net_pay
           FROM employees e JOIN batches b ON b.id = e.batch_id
           WHERE e.employee_no = ? AND b.status = 'approved' AND e.pay_month LIKE ?""",
        (employee_no, f"%{year}%"),
    ).fetchall()
    return {
        "year": year,
        "gross": sum(r["gross_pay"] or 0 for r in rows),
        "napsa": sum(r["napsa"] or 0 for r in rows),
        "nhima": sum(r["nhima"] or 0 for r in rows),
        "paye":  sum(r["paye"]  or 0 for r in rows),
        "deductions": sum(r["deductions"] or 0 for r in rows),
        "net":   sum(r["net_pay"] or 0 for r in rows),
    }


def log_audit(conn, batch_id, action, detail=None):
    conn.execute(
        """INSERT INTO audit_log
           (batch_id, action, actor_username, actor_full_name, actor_role, detail, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (batch_id, action,
         session.get("username"), session.get("full_name"), session.get("role"),
         detail, datetime.now().strftime("%Y-%m-%d %H:%M")),
    )


# ---------- HOG static site ----------

@app.route("/")
def hog_home():
    return send_from_directory(str(HOG_ROOT), "index.html")


# ---------- Payroll Blueprint ----------

bp = Blueprint("payroll", __name__, url_prefix="/payroll")


@bp.route("/")
def index():
    if session.get("username"):
        return redirect(url_for("payroll.batches"))
    return render_template("index.html")


@bp.route("/login", methods=["POST"])
def login():
    username = (request.form.get("username") or "").strip().lower()
    password = request.form.get("password") or ""
    if not username or not password:
        flash("Enter your username and password.", "error")
        return redirect(url_for("payroll.index"))
    conn = db()
    user = conn.execute(
        "SELECT * FROM users WHERE username=? AND active=1", (username,)
    ).fetchone()
    conn.close()
    if not user or not check_password_hash(user["password_hash"], password):
        flash("Invalid username or password.", "error")
        return redirect(url_for("payroll.index"))
    session["user_id"] = user["id"]
    session["username"] = user["username"]
    session["full_name"] = user["full_name"]
    session["role"] = user["role"]
    return redirect(url_for("payroll.batches"))


@bp.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("payroll.index"))


@bp.route("/template")
def download_template():
    path = DATA_DIR / "payroll_template.xlsx"
    conn = db()
    bands, settings = load_tax_config(conn)
    conn.close()
    band_tuples = [(b["lower_bound"], b["upper_bound"], b["rate"]) for b in bands]
    pr.create_template(path, bands=band_tuples, settings=settings)
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
        bands, settings = load_tax_config(conn)
        cur = conn.execute(
            """INSERT INTO batches (name, pay_month, status, initiator,
               initiator_username, initiated_at)
               VALUES (?, ?, 'pending_approver_1', ?, ?, ?)""",
            (batch_name, pay_month, session["full_name"], session["username"], now),
        )
        batch_id = cur.lastrowid
        for e in employees:
            stat = compute_statutory(e["gross_pay"], bands, settings)
            other_ded = e["deductions"]
            net = round(e["gross_pay"] - stat["napsa"] - stat["nhima"] - stat["paye"] - other_ded, 2)
            conn.execute(
                """INSERT INTO employees (batch_id, employee_no, full_name, position,
                   pay_month, basic_salary, allowances, deductions, leave_days,
                   bank_name, account_number, branch, gross_pay, net_pay,
                   napsa, nhima, paye, taxable_income)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (batch_id, e["employee_no"], e["full_name"], e["position"],
                 e["pay_month"], e["basic_salary"], e["allowances"], other_ded,
                 e["leave_days"], e["bank_name"], e["account_number"], e["branch"],
                 e["gross_pay"], net,
                 stat["napsa"], stat["nhima"], stat["paye"], stat["taxable_income"]),
            )
        log_audit(conn, batch_id, "created",
                  detail=f"{len(employees)} employees, pay month {pay_month or '-'}")
        conn.commit()
        conn.close()
        flash(f"Batch #{batch_id} submitted with {len(employees)} employees.", "success")
        return redirect(url_for("payroll.batch_detail", batch_id=batch_id))

    return render_template("upload.html")


@bp.route("/batches")
@require_login
def batches():
    username, role, _ = current_user()
    conn = db()
    rows = conn.execute("SELECT * FROM batches ORDER BY id DESC").fetchall()

    awaiting_me = 0
    if role == "approver1":
        awaiting_me = sum(
            1 for b in rows
            if b["status"] == "pending_approver_1" and (b["initiator_username"] or "") != username
        )
    elif role == "approver2":
        awaiting_me = sum(
            1 for b in rows
            if b["status"] == "pending_approver_2"
            and (b["initiator_username"] or "") != username
            and (b["approver1_username"] or "") != username
        )

    this_year = datetime.now().strftime("%Y")
    gross_year_row = conn.execute(
        """SELECT COALESCE(SUM(e.gross_pay), 0)
           FROM employees e JOIN batches b ON b.id = e.batch_id
           WHERE b.status = 'approved' AND e.pay_month LIKE ?""",
        (f"%{this_year}%",),
    ).fetchone()
    gross_year = gross_year_row[0] if gross_year_row else 0

    kpi = {
        "total": len(rows),
        "awaiting_me": awaiting_me,
        "approved_this_year": sum(
            1 for b in rows if b["status"] == "approved" and (b["pay_month"] or "").endswith(this_year)
        ),
        "gross_year": gross_year,
        "pending": sum(1 for b in rows if b["status"] in ("pending_approver_1", "pending_approver_2")),
        "year": this_year,
    }
    conn.close()
    return render_template("batches.html", batches=rows, role=role, kpi=kpi)


@bp.route("/batch/<int:batch_id>")
@require_login
def batch_detail(batch_id):
    _, role, _ = current_user()
    conn = db()
    batch = conn.execute("SELECT * FROM batches WHERE id=?", (batch_id,)).fetchone()
    if not batch:
        conn.close()
        abort(404)
    employees = conn.execute(
        "SELECT * FROM employees WHERE batch_id=? ORDER BY employee_no",
        (batch_id,),
    ).fetchall()
    audit = conn.execute(
        "SELECT * FROM audit_log WHERE batch_id=? ORDER BY id ASC",
        (batch_id,),
    ).fetchall()
    conn.close()
    totals = {
        "basic": sum(e["basic_salary"] or 0 for e in employees),
        "allowances": sum(e["allowances"] or 0 for e in employees),
        "deductions": sum(e["deductions"] or 0 for e in employees),
        "gross": sum(e["gross_pay"] or 0 for e in employees),
        "net": sum(e["net_pay"] or 0 for e in employees),
        "napsa": sum(e["napsa"] or 0 for e in employees),
        "nhima": sum(e["nhima"] or 0 for e in employees),
        "paye": sum(e["paye"] or 0 for e in employees),
    }
    return render_template(
        "batch_detail.html", batch=batch, employees=employees,
        totals=totals, role=role, audit=audit,
    )


@bp.route("/batch/<int:batch_id>/approve", methods=["POST"])
@require_login
def approve(batch_id):
    username, role, full_name = current_user()
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    conn = db()
    batch = conn.execute("SELECT * FROM batches WHERE id=?", (batch_id,)).fetchone()
    if not batch:
        conn.close()
        abort(404)

    if role == "approver1" and batch["status"] == "pending_approver_1":
        if batch["initiator_username"] == username:
            flash("You cannot approve a batch you initiated.", "error")
        else:
            conn.execute(
                """UPDATE batches SET status='pending_approver_2',
                   approver1=?, approver1_username=?, approver1_at=? WHERE id=?""",
                (full_name, username, now, batch_id),
            )
            log_audit(conn, batch_id, "approved_stage_1")
            conn.commit()
            flash("Approved at stage 1. Now awaiting Approver 2.", "success")
    elif role == "approver2" and batch["status"] == "pending_approver_2":
        if batch["approver1_username"] == username or batch["initiator_username"] == username:
            flash("You cannot approve a batch you initiated or already approved.", "error")
        else:
            conn.execute(
                """UPDATE batches SET status='approved',
                   approver2=?, approver2_username=?, approver2_at=? WHERE id=?""",
                (full_name, username, now, batch_id),
            )
            log_audit(conn, batch_id, "approved_stage_2")
            conn.commit()
            flash("Final approval recorded. Payslips can now be downloaded.", "success")
    else:
        flash("This batch is not awaiting your approval.", "error")
    conn.close()
    return redirect(url_for("payroll.batch_detail", batch_id=batch_id))


@bp.route("/batch/<int:batch_id>/reject", methods=["POST"])
@require_login
def reject(batch_id):
    _, role, full_name = current_user()
    if role not in {"approver1", "approver2"}:
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
            (f"{full_name} ({role})", reason, batch_id),
        )
        log_audit(conn, batch_id, "rejected", detail=reason)
        conn.commit()
        flash("Batch rejected.", "success")
    conn.close()
    return redirect(url_for("payroll.batch_detail", batch_id=batch_id))


def _batch_meta(batch):
    return {
        "initiator": batch["initiator"] or "-",
        "initiated_at": batch["initiated_at"] or "",
        "approver1": batch["approver1"] or "-",
        "approver1_at": batch["approver1_at"] or "",
        "approver2": batch["approver2"] or "-",
        "approver2_at": batch["approver2_at"] or "",
    }


@bp.route("/batch/<int:batch_id>/payslip/<int:emp_id>")
@require_login
def payslip(batch_id, emp_id):
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
    conn = db()
    _, settings = load_tax_config(conn)
    ytd = compute_ytd(conn, emp["employee_no"], emp["pay_month"])
    conn.close()
    pr.generate_payslip_pdf(
        dict(emp), _batch_meta(batch), str(out_path),
        company_name=str(settings.get("company_name", "Hope of Glory")),
        currency=str(settings.get("currency_code", "ZMW")),
        ytd=ytd,
    )
    return send_file(out_path, as_attachment=True,
                     download_name=f"payslip_{emp['employee_no']}_{emp['pay_month']}.pdf")


@bp.route("/batch/<int:batch_id>/payslips.zip")
@require_login
def payslips_zip(batch_id):
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

    conn = db()
    _, settings = load_tax_config(conn)
    company = str(settings.get("company_name", "Hope of Glory"))
    currency = str(settings.get("currency_code", "ZMW"))
    ytd_by_emp = {
        e["id"]: compute_ytd(conn, e["employee_no"], e["pay_month"])
        for e in employees
    }
    conn.close()

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for emp in employees:
            safe = "".join(c if c.isalnum() else "_" for c in emp["employee_no"])
            out_path = out_dir / f"payslip_{safe}.pdf"
            pr.generate_payslip_pdf(
                dict(emp), meta, str(out_path),
                company_name=company, currency=currency, ytd=ytd_by_emp.get(emp["id"]),
            )
            zf.write(out_path, arcname=f"payslip_{emp['employee_no']}_{emp['full_name']}.pdf")
    buf.seek(0)
    return send_file(buf, mimetype="application/zip", as_attachment=True,
                     download_name=f"payslips_batch_{batch_id}.zip")


# ---------- Admin: user management ----------

@bp.route("/users")
@require_login
@require_admin
def users():
    conn = db()
    rows = conn.execute(
        "SELECT * FROM users ORDER BY active DESC, role, username"
    ).fetchall()
    conn.close()
    return render_template("users.html", users=rows, roles=ROLES)


@bp.route("/users/create", methods=["POST"])
@require_login
@require_admin
def users_create():
    username = (request.form.get("username") or "").strip().lower()
    full_name = (request.form.get("full_name") or "").strip()
    role = request.form.get("role")
    password = request.form.get("password") or ""
    if not username or not full_name or role not in ROLES or len(password) < 6:
        flash("Username, full name, valid role, and password (6+ chars) required.", "error")
        return redirect(url_for("payroll.users"))
    conn = db()
    try:
        conn.execute(
            """INSERT INTO users (username, password_hash, full_name, role, active, created_at)
               VALUES (?, ?, ?, ?, 1, ?)""",
            (username, generate_password_hash(password), full_name, role,
             datetime.now().strftime("%Y-%m-%d %H:%M")),
        )
        conn.commit()
        flash(f"User '{username}' created.", "success")
    except sqlite3.IntegrityError:
        flash(f"Username '{username}' already exists.", "error")
    conn.close()
    return redirect(url_for("payroll.users"))


@bp.route("/users/<int:user_id>/toggle", methods=["POST"])
@require_login
@require_admin
def users_toggle(user_id):
    conn = db()
    u = conn.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
    if not u:
        conn.close()
        abort(404)
    if u["id"] == session.get("user_id"):
        flash("You cannot deactivate yourself.", "error")
    else:
        conn.execute("UPDATE users SET active=? WHERE id=?",
                     (0 if u["active"] else 1, user_id))
        conn.commit()
        flash(
            f"User '{u['username']}' {'deactivated' if u['active'] else 'reactivated'}.",
            "success",
        )
    conn.close()
    return redirect(url_for("payroll.users"))


@bp.route("/users/<int:user_id>/reset", methods=["POST"])
@require_login
@require_admin
def users_reset(user_id):
    new_password = request.form.get("password") or ""
    if len(new_password) < 6:
        flash("New password must be at least 6 characters.", "error")
        return redirect(url_for("payroll.users"))
    conn = db()
    u = conn.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
    if not u:
        conn.close()
        abort(404)
    conn.execute("UPDATE users SET password_hash=? WHERE id=?",
                 (generate_password_hash(new_password), user_id))
    conn.commit()
    conn.close()
    flash(f"Password reset for '{u['username']}'.", "success")
    return redirect(url_for("payroll.users"))


# ---------- Admin: tax settings ----------

@bp.route("/settings")
@require_login
@require_admin
def settings_view():
    conn = db()
    bands = conn.execute(
        "SELECT * FROM paye_bands ORDER BY sort_order"
    ).fetchall()
    settings_rows = conn.execute(
        "SELECT key, value, label, value_type FROM app_settings ORDER BY key"
    ).fetchall()
    conn.close()
    return render_template("settings.html", bands=bands, settings=settings_rows)


@bp.route("/settings/save", methods=["POST"])
@require_login
@require_admin
def settings_save():
    # Read submitted bands. Each row uses indexed names: band_lower_<i>, band_upper_<i>, band_rate_<i>.
    indices = sorted({
        int(k.split("_")[-1])
        for k in request.form.keys()
        if k.startswith("band_lower_")
    })
    new_bands = []
    for i in indices:
        lower = request.form.get(f"band_lower_{i}", "").strip()
        upper = request.form.get(f"band_upper_{i}", "").strip()
        rate_pct = request.form.get(f"band_rate_{i}", "").strip()
        delete = request.form.get(f"band_delete_{i}") == "1"
        if delete or (not lower and not rate_pct):
            continue
        try:
            lo = float(lower)
            up = float(upper) if upper else None
            rt = float(rate_pct) / 100.0
        except ValueError:
            flash(f"Band {i}: numeric values required.", "error")
            return redirect(url_for("payroll.settings_view"))
        if rt < 0 or rt > 1:
            flash(f"Band {i}: rate must be between 0 and 100.", "error")
            return redirect(url_for("payroll.settings_view"))
        if up is not None and up <= lo:
            flash(f"Band {i}: upper bound must exceed lower bound.", "error")
            return redirect(url_for("payroll.settings_view"))
        new_bands.append((lo, up, rt))

    # Optional new band row
    nl = request.form.get("band_lower_new", "").strip()
    nu = request.form.get("band_upper_new", "").strip()
    nr = request.form.get("band_rate_new", "").strip()
    if nl or nr:
        try:
            new_bands.append((float(nl), float(nu) if nu else None, float(nr) / 100.0))
        except ValueError:
            flash("New band: numeric values required.", "error")
            return redirect(url_for("payroll.settings_view"))

    new_bands.sort(key=lambda b: b[0])
    for a, b in zip(new_bands, new_bands[1:]):
        a_upper = a[1] if a[1] is not None else float("inf")
        if a_upper > b[0]:
            flash("PAYE bands overlap. Each upper bound must equal the next lower bound.", "error")
            return redirect(url_for("payroll.settings_view"))
    if not new_bands:
        flash("At least one PAYE band is required.", "error")
        return redirect(url_for("payroll.settings_view"))

    conn = db()
    try:
        conn.execute("DELETE FROM paye_bands")
        for order, (lo, up, rt) in enumerate(new_bands, start=1):
            conn.execute(
                "INSERT INTO paye_bands (lower_bound, upper_bound, rate, sort_order) VALUES (?, ?, ?, ?)",
                (lo, up, rt, order),
            )

        for r in conn.execute("SELECT key, value_type FROM app_settings").fetchall():
            field = f"setting_{r['key']}"
            if r["value_type"] == "bool":
                val = "1" if request.form.get(field) == "1" else "0"
            else:
                val = (request.form.get(field) or "").strip()
                if r["value_type"] == "number":
                    try:
                        float(val)
                    except ValueError:
                        conn.rollback()
                        conn.close()
                        flash(f"Setting '{r['key']}': numeric value required.", "error")
                        return redirect(url_for("payroll.settings_view"))
            conn.execute("UPDATE app_settings SET value=? WHERE key=?", (val, r["key"]))
        conn.commit()
        flash("Settings saved. Future batches will use these values.", "success")
    except Exception as e:
        conn.rollback()
        flash(f"Could not save settings: {e}", "error")
    conn.close()
    return redirect(url_for("payroll.settings_view"))


app.register_blueprint(bp)


UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
PAYSLIP_DIR.mkdir(parents=True, exist_ok=True)
init_db()


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True)
