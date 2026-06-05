from datetime import date
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import HRFlowable, Paragraph, SimpleDocTemplate, Spacer

from schemas.employee import EmployeeRecord
from services.offer_letter.field_definitions import (
    BLANK,
    CLOSING_PARAGRAPH,
    FIELD_DEFINITIONS,
    OPENING_PARAGRAPH,
    appointment_ref,
    indian_long_date,
)
from io import BytesIO
from typing import Optional
from pypdf import PdfReader, PdfWriter
from services.offer_letter.letterhead import (
    get_footer_path_for_reportlab,
    get_header_path_for_reportlab,
    is_letterhead_available,
)

MARGIN_TOP = 2.5 * cm
MARGIN_BOTTOM = 2 * cm
MARGIN_LEFT = 1.8 * cm
MARGIN_RIGHT = 1.8 * cm

HEADER_DRAW_HEIGHT = 2.8 * cm
FOOTER_DRAW_HEIGHT = 0.9 * cm


def _draw_page_decorations(canvas, doc, header_path: Optional[str] = None, footer_path: Optional[str] = None):
    canvas.saveState()
    page_width, page_height = A4

    if header_path is None:
        header_path = get_header_path_for_reportlab()

    if header_path:
        canvas.drawImage(
            header_path,
            MARGIN_LEFT,
            page_height - HEADER_DRAW_HEIGHT - 0.4 * cm,
            width=page_width - MARGIN_LEFT - MARGIN_RIGHT,
            height=HEADER_DRAW_HEIGHT,
            preserveAspectRatio=True,
            mask="auto",
        )
    else:
        canvas.setFont("Helvetica-Bold", 10)
        canvas.drawString(MARGIN_LEFT, page_height - 1.2 * cm, "NLC India Renewables Limited")

    if footer_path is None:
        footer_path = get_footer_path_for_reportlab()

    if footer_path:
        canvas.drawImage(
            footer_path,
            MARGIN_LEFT,
            0.35 * cm,
            width=page_width - MARGIN_LEFT - MARGIN_RIGHT,
            height=FOOTER_DRAW_HEIGHT,
            preserveAspectRatio=True,
            mask="auto",
        )

    canvas.restoreState()


def _content_top_spacer(has_header: bool) -> Spacer:
    if has_header:
        return Spacer(1, HEADER_DRAW_HEIGHT + 0.2 * cm)
    return Spacer(1, 0.6 * cm)


def generate_appointment_pdf(
    employee: EmployeeRecord,
    output_path: str | Path,
    letterhead_pdf: Optional[str | Path | bytes] = None,
    header_path: Optional[str] = None,
    footer_path: Optional[str] = None
) -> Path:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    from services.offer_letter.letterhead import LETTERHEAD_PDF_PATH
    
    resolved_letterhead = letterhead_pdf
    if resolved_letterhead is None and LETTERHEAD_PDF_PATH.is_file():
        resolved_letterhead = LETTERHEAD_PDF_PATH

    has_letterhead = resolved_letterhead is not None

    top_margin = 5.2 * cm if has_letterhead else MARGIN_TOP
    bottom_margin = 2.2 * cm if has_letterhead else (MARGIN_BOTTOM + FOOTER_DRAW_HEIGHT)

    today = date.today()
    ref_no = appointment_ref(employee.id, today.year)
    styles = getSampleStyleSheet()

    body = ParagraphStyle(
        "Body",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=10,
        leading=14,
        alignment=TA_LEFT,
    )
    title = ParagraphStyle(
        "Title",
        parent=body,
        fontName="Helvetica-Bold",
        fontSize=14,
        alignment=TA_CENTER,
        spaceAfter=6,
    )
    bold = ParagraphStyle("Bold", parent=body, fontName="Helvetica-Bold")
    bold_center = ParagraphStyle(
        "BoldCenter",
        parent=bold,
        fontSize=14,
        alignment=TA_CENTER,
        textDecoration="underline",
    )
    section = ParagraphStyle("Section", parent=bold, fontSize=11, spaceBefore=8, spaceAfter=4)
    subject = ParagraphStyle("Subject", parent=bold, textDecoration="underline")

    story = []
    if not has_letterhead:
        story.append(_content_top_spacer(has_header=True))

    story.append(Paragraph(f"Date: {indian_long_date(today)}", body))
    story.append(Paragraph(f"Ref: {ref_no}", body))
    story.append(Spacer(1, 0.3 * cm))
    story.append(Paragraph("<u>APPOINTMENT LETTER</u>", bold_center))
    story.append(
        HRFlowable(
            width="100%",
            thickness=1,
            color=colors.HexColor("#2E7D32"),
            spaceBefore=4,
            spaceAfter=8,
        )
    )
    story.append(Paragraph(f"Dear {employee.employee_name},", body))
    story.append(Spacer(1, 0.15 * cm))
    story.append(
        Paragraph(
            f"Sub: Appointment as {employee.designation} – reg.",
            subject,
        )
    )
    story.append(Spacer(1, 0.2 * cm))
    story.append(Paragraph(OPENING_PARAGRAPH, body))
    story.append(Spacer(1, 0.25 * cm))
    story.append(Paragraph("TERMS OF APPOINTMENT", section))
    story.append(HRFlowable(width="100%", thickness=0.5, color=colors.grey, spaceAfter=6))

    for field in FIELD_DEFINITIONS:
        value = field.getter(employee) or BLANK
        roman_label = f"<b>{field.roman}.</b> <b>{field.label}:</b>"
        story.append(Paragraph(f"{roman_label} {value}", body))
        story.append(Spacer(1, 0.12 * cm))

    story.append(Spacer(1, 0.35 * cm))
    story.append(HRFlowable(width="100%", thickness=0.5, color=colors.grey, spaceBefore=4, spaceAfter=8))
    story.append(Paragraph(CLOSING_PARAGRAPH, body))
    story.append(Spacer(1, 0.5 * cm))
    story.append(Paragraph("<b>For NLC India Renewables Limited</b>", body))
    story.append(Spacer(1, 1.2 * cm))
    story.append(Paragraph("<b>Authorised Signatory</b>", body))
    story.append(Paragraph("Name &amp; Designation: ___________________________", body))
    story.append(Paragraph("Date: _____________________", body))
    story.append(Spacer(1, 0.6 * cm))
    story.append(Paragraph("ACKNOWLEDGEMENT BY EMPLOYEE", section))
    story.append(HRFlowable(width="100%", thickness=0.5, color=colors.grey, spaceAfter=6))
    story.append(
        Paragraph(
            f"I, {employee.employee_name}, acknowledge receipt of this Appointment Letter "
            "and confirm my acceptance of all terms and conditions stated above.",
            body,
        )
    )
    story.append(Spacer(1, 0.5 * cm))
    story.append(Paragraph("Signature of Employee: ___________________________", body))
    story.append(Paragraph("Date: _____________________", body))

    temp_pdf_path = output_path.with_suffix('.tmp.pdf') if has_letterhead else output_path

    doc = SimpleDocTemplate(
        str(temp_pdf_path),
        pagesize=A4,
        leftMargin=MARGIN_LEFT,
        rightMargin=MARGIN_RIGHT,
        topMargin=top_margin,
        bottomMargin=bottom_margin,
        title=f"Appointment Letter – {employee.employee_name}",
    )

    if not has_letterhead:
        def on_page(canvas, document):
            _draw_page_decorations(canvas, document, header_path, footer_path)
        doc.build(story, onFirstPage=on_page, onLaterPages=on_page)
    else:
        doc.build(story)

        try:
            reader = PdfReader(temp_pdf_path)
            
            if isinstance(resolved_letterhead, bytes):
                lh_reader = PdfReader(BytesIO(resolved_letterhead))
            else:
                lh_reader = PdfReader(str(resolved_letterhead))
                
            lh_page = lh_reader.pages[0]
            writer = PdfWriter()

            for page in reader.pages:
                page.merge_page(lh_page)
                writer.add_page(page)

            with open(output_path, "wb") as f:
                writer.write(f)
        finally:
            if temp_pdf_path.exists():
                temp_pdf_path.unlink()

    return output_path
