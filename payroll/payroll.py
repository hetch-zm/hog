"""Payroll core: Excel parsing, calculations, PDF payslip generation."""
import os
from datetime import datetime
from openpyxl import load_workbook, Workbook
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
)


REQUIRED_COLUMNS = [
    "Employee Number",
    "Full Name",
    "Position",
    "Pay Month",
    "Basic Salary",
    "Allowances",
    "Deductions",
    "Leave Days",
    "Bank Name",
    "Account Number",
    "Branch",
]


def create_template(path):
    wb = Workbook()
    ws = wb.active
    ws.title = "Payroll"
    ws.append(REQUIRED_COLUMNS)
    ws.append([
        "EMP001", "Jane Doe", "Accountant", "April 2026",
        15000, 2500, 1800, 0, "ZANACO", "1234567890", "Cairo Road",
    ])
    ws.append([
        "EMP002", "John Smith", "Farm Manager", "April 2026",
        22000, 3500, 2700, 2, "Stanbic", "9876543210", "Manda Hill",
    ])
    for i, col in enumerate(REQUIRED_COLUMNS, start=1):
        ws.column_dimensions[chr(64 + i)].width = max(15, len(col) + 2)
    wb.save(path)


def _to_float(v):
    if v is None or v == "":
        return 0.0
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def parse_excel(path):
    """Read the uploaded Excel and return a list of employee dicts."""
    wb = load_workbook(path, data_only=True)
    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))
    if not rows:
        raise ValueError("Excel file is empty")

    headers = [str(c).strip() if c else "" for c in rows[0]]
    missing = [c for c in REQUIRED_COLUMNS if c not in headers]
    if missing:
        raise ValueError(f"Missing columns: {', '.join(missing)}")

    idx = {h: headers.index(h) for h in REQUIRED_COLUMNS}
    employees = []
    for row in rows[1:]:
        if not row or all(c is None or c == "" for c in row):
            continue
        emp_no = row[idx["Employee Number"]]
        if not emp_no:
            continue
        basic = _to_float(row[idx["Basic Salary"]])
        allow = _to_float(row[idx["Allowances"]])
        deduc = _to_float(row[idx["Deductions"]])
        leave_days = _to_float(row[idx["Leave Days"]])
        gross = basic + allow
        net = gross - deduc
        employees.append({
            "employee_no": str(emp_no).strip(),
            "full_name": str(row[idx["Full Name"]] or "").strip(),
            "position": str(row[idx["Position"]] or "").strip(),
            "pay_month": str(row[idx["Pay Month"]] or "").strip(),
            "basic_salary": basic,
            "allowances": allow,
            "deductions": deduc,
            "leave_days": leave_days,
            "bank_name": str(row[idx["Bank Name"]] or "").strip(),
            "account_number": str(row[idx["Account Number"]] or "").strip(),
            "branch": str(row[idx["Branch"]] or "").strip(),
            "gross_pay": gross,
            "net_pay": net,
        })
    if not employees:
        raise ValueError("No employee rows found")
    return employees


def _money(v):
    return f"{v:,.2f}"


def generate_payslip_pdf(emp, batch_meta, out_path, company_name="Hope of Glory"):
    doc = SimpleDocTemplate(
        out_path, pagesize=A4,
        leftMargin=18 * mm, rightMargin=18 * mm,
        topMargin=18 * mm, bottomMargin=18 * mm,
    )
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "title", parent=styles["Heading1"],
        fontSize=18, alignment=1, spaceAfter=4,
    )
    sub_style = ParagraphStyle(
        "sub", parent=styles["Normal"],
        fontSize=10, alignment=1, textColor=colors.grey, spaceAfter=14,
    )

    story = [
        Paragraph(company_name, title_style),
        Paragraph(f"Payslip — {emp['pay_month']}", sub_style),
    ]

    info = [
        ["Employee Number", emp["employee_no"], "Pay Month", emp["pay_month"]],
        ["Full Name", emp["full_name"], "Position", emp["position"]],
        ["Bank", emp["bank_name"], "Account No.", emp["account_number"]],
        ["Branch", emp["branch"], "Leave Days", _money(emp["leave_days"])],
    ]
    info_tbl = Table(info, colWidths=[32 * mm, 55 * mm, 32 * mm, 55 * mm])
    info_tbl.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.4, colors.grey),
        ("INNERGRID", (0, 0), (-1, -1), 0.3, colors.lightgrey),
        ("BACKGROUND", (0, 0), (0, -1), colors.whitesmoke),
        ("BACKGROUND", (2, 0), (2, -1), colors.whitesmoke),
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTNAME", (2, 0), (2, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    story.append(info_tbl)
    story.append(Spacer(1, 10 * mm))

    earnings_deductions = [
        ["Earnings", "Amount (ZMW)", "Deductions", "Amount (ZMW)"],
        ["Basic Salary", _money(emp["basic_salary"]), "Total Deductions", _money(emp["deductions"])],
        ["Allowances", _money(emp["allowances"]), "", ""],
        ["Gross Pay", _money(emp["gross_pay"]), "", ""],
    ]
    ed_tbl = Table(earnings_deductions, colWidths=[44 * mm, 44 * mm, 44 * mm, 42 * mm])
    ed_tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0d3b66")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("ALIGN", (1, 1), (1, -1), "RIGHT"),
        ("ALIGN", (3, 1), (3, -1), "RIGHT"),
        ("BOX", (0, 0), (-1, -1), 0.4, colors.grey),
        ("INNERGRID", (0, 0), (-1, -1), 0.3, colors.lightgrey),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    story.append(ed_tbl)
    story.append(Spacer(1, 8 * mm))

    net_tbl = Table(
        [["NET PAY", f"ZMW  {_money(emp['net_pay'])}"]],
        colWidths=[88 * mm, 86 * mm],
    )
    net_tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#0d3b66")),
        ("TEXTCOLOR", (0, 0), (-1, -1), colors.white),
        ("FONTNAME", (0, 0), (-1, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 13),
        ("ALIGN", (1, 0), (1, 0), "RIGHT"),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("RIGHTPADDING", (0, 0), (-1, -1), 10),
    ]))
    story.append(net_tbl)
    story.append(Spacer(1, 12 * mm))

    approvals = [
        ["Initiated by", batch_meta.get("initiator", "—"), batch_meta.get("initiated_at", "")],
        ["Approver 1", batch_meta.get("approver1", "—"), batch_meta.get("approver1_at", "")],
        ["Approver 2", batch_meta.get("approver2", "—"), batch_meta.get("approver2_at", "")],
    ]
    ap_tbl = Table(
        [["Approval Trail", "Name", "Timestamp"]] + approvals,
        colWidths=[40 * mm, 70 * mm, 64 * mm],
    )
    ap_tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#444")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("BOX", (0, 0), (-1, -1), 0.4, colors.grey),
        ("INNERGRID", (0, 0), (-1, -1), 0.3, colors.lightgrey),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    story.append(ap_tbl)

    footer = ParagraphStyle(
        "footer", parent=styles["Normal"],
        fontSize=8, alignment=1, textColor=colors.grey,
    )
    story.append(Spacer(1, 8 * mm))
    story.append(Paragraph(
        f"Generated {datetime.now().strftime('%Y-%m-%d %H:%M')} — This is a system-generated payslip.",
        footer,
    ))

    doc.build(story)
    return out_path
