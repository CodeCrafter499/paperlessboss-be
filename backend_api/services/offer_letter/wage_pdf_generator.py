from pathlib import Path
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from datetime import date
from decimal import Decimal

def format_currency(val) -> str:
    if val is None:
        return "0.00"
    if isinstance(val, Decimal):
        val = float(val)
    return f"{val:,.2f}"

def format_attendance(val) -> str:
    if val is None:
        return "0"
    if isinstance(val, Decimal):
        val = float(val)
    if val == int(val):
        return str(int(val))
    return str(val)

def generate_wage_slip_pdf(wage_slip, output_path: str | Path, company) -> Path:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Margins and dimensions
    margin = 1.5 * cm
    page_width, page_height = A4
    printable_width = page_width - 2 * margin

    styles = getSampleStyleSheet()
    
    # Styles
    title_style = ParagraphStyle(
        "TitleStyle",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=12,
        leading=15,
        alignment=TA_CENTER,
    )
    
    label_style = ParagraphStyle(
        "LabelStyle",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=10,
        leading=13,
        alignment=TA_LEFT,
    )
    
    label_indent_style = ParagraphStyle(
        "LabelIndentStyle",
        parent=label_style,
        leftIndent=15,
    )
    
    value_style = ParagraphStyle(
        "ValueStyle",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=10,
        leading=13,
        alignment=TA_LEFT,
    )

    value_right_style = ParagraphStyle(
        "ValueRightStyle",
        parent=value_style,
        alignment=TA_RIGHT,
    )

    # 1. Build the Table Data
    # Column 1 width is 60%, Column 2 width is 40% of printable_width
    col1_w = printable_width * 0.55
    col2_w = printable_width * 0.45

    # Period string
    period_str = f"{wage_slip.wage_month or ''} {wage_slip.wage_year or ''}".strip()
    issue_date_str = date.today().strftime("%d %B %Y")

    table_data = [
        # Form V Header (spans both columns)
        [Paragraph("<b>FORM V</b><br/>(See rule 52)", title_style), ""],
        [Paragraph("<b>WAGE SLIP</b>", title_style), ""],
        
        # General Fields
        [Paragraph("Date of issue", label_style), Paragraph(issue_date_str, value_style)],
        [Paragraph("Name of the Establishment", label_style), Paragraph(company.name or "", value_style)],
        [Paragraph("Address", label_style), Paragraph(company.address or "", value_style)],
        [Paragraph("Period", label_style), Paragraph(period_str, value_style)],
        
        # Employee info
        [Paragraph("1. Name of employee", label_style), Paragraph(wage_slip.employee_name or "", value_style)],
        [Paragraph("2. Father's/Mother's/Spouse Name", label_style), Paragraph(wage_slip.father_mother_spouse_name or "", value_style)],
        [Paragraph("3. Designation", label_style), Paragraph(wage_slip.designation or "", value_style)],
        [Paragraph("4. UAN", label_style), Paragraph(wage_slip.uan or "N/A", value_style)],
        [Paragraph("5. Bank Account Number", label_style), Paragraph(wage_slip.bank_account_number or "N/A", value_style)],
        [Paragraph("6. Wage period", label_style), Paragraph(period_str, value_style)],
        
        # Rate of wages
        [Paragraph("7. Rate of wages payable", label_style), ""],
        [Paragraph("a. Basic", label_indent_style), Paragraph(format_currency(wage_slip.rate_basic), value_right_style)],
        [Paragraph("b. DA", label_indent_style), Paragraph(format_currency(wage_slip.rate_da), value_right_style)],
        [Paragraph("c. Allowances", label_indent_style), Paragraph(format_currency(wage_slip.rate_allowances), value_right_style)],
        
        # Attendance/OT/Gross
        [Paragraph("8. Total attendance/unit of work done", label_style), Paragraph(format_attendance(wage_slip.total_attendance), value_style)],
        [Paragraph("9. Overtime wages", label_style), Paragraph(format_currency(wage_slip.overtime_wages), value_right_style)],
        [Paragraph("10. Gross wages payable", label_style), Paragraph(format_currency(wage_slip.gross_wages), value_right_style)],
        
        # Deductions
        [Paragraph("11. Total deductions", label_style), ""],
        [Paragraph("a. PF", label_indent_style), Paragraph(format_currency(wage_slip.deduction_pf), value_right_style)],
        [Paragraph("b. ESI", label_indent_style), Paragraph(format_currency(wage_slip.deduction_esi), value_right_style)],
        [Paragraph("c. Others", label_indent_style), Paragraph(format_currency(wage_slip.deduction_others), value_right_style)],
        
        # Net wages
        [Paragraph("12. Net wages paid", label_style), Paragraph(format_currency(wage_slip.net_wages), value_right_style)],
    ]

    t = Table(table_data, colWidths=[col1_w, col2_w])
    
    # Styling matching the exact target image
    t_style = TableStyle([
        # Headers span columns
        ('SPAN', (0, 0), (1, 0)),
        ('SPAN', (0, 1), (1, 1)),
        ('SPAN', (0, 14), (1, 14)), # Rate header doesn't span, but left empty
        ('SPAN', (0, 21), (1, 21)), # Total deductions header left empty
        
        # Alignments & Padding
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
        ('RIGHTPADDING', (0, 0), (-1, -1), 6),
        
        # Full grid border
        ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
    ])
    
    # Let's adjust SPAN indexes based on actual rows list:
    # 0: Header 1 (SPAN 0,0 to 1,0)
    # 1: Header 2 (SPAN 0,1 to 1,1)
    # 2: Date of issue
    # 3: Name of Establishment
    # 4: Address
    # 5: Period
    # 6: Name of employee
    # 7: Father's/Mother's/Spouse Name
    # 8: Designation
    # 9: UAN
    # 10: Bank Account Number
    # 11: Wage period
    # 12: 7. Rate of wages payable (SPAN 0,12 to 1,12)
    # 13: a. Basic
    # 14: b. DA
    # 15: c. Allowances
    # 16: 8. Total attendance
    # 17: 9. Overtime wages
    # 18: 10. Gross wages
    # 19: 11. Total deductions (SPAN 0,19 to 1,19)
    # 20: a. PF
    # 21: b. ESI
    # 22: c. Others
    # 23: 12. Net wages paid
    
    # Correct spans:
    t_style.add('SPAN', (0, 12), (1, 12))
    t_style.add('SPAN', (0, 19), (1, 19))
    
    t.setStyle(t_style)

    # Build PDF doc
    doc = SimpleDocTemplate(
        str(output_path),
        pagesize=A4,
        leftMargin=margin,
        rightMargin=margin,
        topMargin=margin,
        bottomMargin=margin,
        title=f"Wage Slip – {wage_slip.employee_name}",
    )
    
    doc.build([t])
    return output_path
