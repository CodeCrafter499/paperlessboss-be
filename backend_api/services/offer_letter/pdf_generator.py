from datetime import date
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import HRFlowable, Paragraph, SimpleDocTemplate, Spacer, Image as RLImage, Table, TableStyle, KeepTogether
import base64
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

MARGIN_TOP = 2.0 * cm
MARGIN_BOTTOM = 1.5 * cm
MARGIN_LEFT = 1.8 * cm
MARGIN_RIGHT = 1.8 * cm

HEADER_DRAW_HEIGHT = 2.8 * cm
FOOTER_DRAW_HEIGHT = 0.9 * cm


def _draw_page_decorations(canvas, doc, header_path: Optional[str] = None, footer_path: Optional[str] = None, company_name: str = "PaperlessBoss Private Limited"):
    canvas.saveState()
    page_width, page_height = A4

    if header_path:
        canvas.drawImage(
            header_path,
            0,
            page_height - HEADER_DRAW_HEIGHT - 0.4 * cm,
            width=page_width,
            height=HEADER_DRAW_HEIGHT,
            preserveAspectRatio=True,
            mask="auto",
        )
    else:
        canvas.setFont("Helvetica-Bold", 10)
        canvas.drawString(MARGIN_LEFT, page_height - 1.2 * cm, company_name)

    if footer_path:
        canvas.drawImage(
            footer_path,
            0,
            0.4 * cm,
            width=page_width,
            height=FOOTER_DRAW_HEIGHT,
            preserveAspectRatio=True,
            mask="auto",
        )

    canvas.restoreState()


def _content_top_spacer(has_header: bool) -> Spacer:
    if has_header:
        return Spacer(1, HEADER_DRAW_HEIGHT + 0.2 * cm)
    return Spacer(1, 0.4 * cm)


def generate_appointment_pdf(
    employee: "EmployeeRecord",
    output_path: str | Path,
    header_path: Optional[str] = None,
    footer_path: Optional[str] = None,
    signature_image: Optional[str] = None,
    stamp_image: Optional[str] = None,
    company_name: Optional[str] = None,
) -> Path:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    from services.offer_letter.letterhead import LETTERHEAD_PDF_PATH
    
    has_header = header_path is not None
    top_margin = 4.0 * cm if has_header else MARGIN_TOP
    bottom_margin = MARGIN_BOTTOM

    today = date.today()
    ref_no = appointment_ref(employee.id, today.year)
    styles = getSampleStyleSheet()

    body = ParagraphStyle(
        "Body",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=10,
        leading=13,
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
    section = ParagraphStyle("Section", parent=bold, fontSize=11, spaceBefore=4, spaceAfter=2, keepWithNext=True)
    subject = ParagraphStyle("Subject", parent=bold, textDecoration="underline")

    sp_ref = Spacer(1, 0.05 * cm)
    sp_title = Spacer(1, 0.05 * cm)
    sp_terms = Spacer(1, 0.05 * cm)
    sp_closing = Spacer(1, 0.05 * cm)
    sp_sigs = Spacer(1, 0.05 * cm)

    story = []
    if not has_header:
        story.append(_content_top_spacer(has_header=False))

    story.append(Paragraph(f"Date: {indian_long_date(today)}", body))
    story.append(Paragraph(f"Ref: {ref_no}", body))
    story.append(sp_ref)
    story.append(Paragraph("<u>APPOINTMENT LETTER</u>", bold_center))
    story.append(
        HRFlowable(
            width="100%",
            thickness=1,
            color=colors.HexColor("#2E7D32"),
            spaceBefore=2,
            spaceAfter=4,
        )
    )
    company_name = company_name or employee.company_name or "PaperlessBoss Private Limited"
    story.append(sp_title)
    story.append(Paragraph("TERMS OF APPOINTMENT", section))
    story.append(HRFlowable(width="100%", thickness=0.5, color=colors.grey, spaceAfter=4))

    for field in FIELD_DEFINITIONS:
        value = field.getter(employee) or BLANK
        roman_label = f"<b>{field.roman}.</b> <b>{field.label}:</b>"
        story.append(Paragraph(f"{roman_label} {value}", body))
        story.append(Spacer(1, 0.03 * cm))

    story.append(sp_terms)
    story.append(HRFlowable(width="100%", thickness=0.5, color=colors.grey, spaceBefore=2, spaceAfter=4))
    story.append(Paragraph(CLOSING_PARAGRAPH, body))
    story.append(sp_closing)
    story.append(Paragraph(f"<b>For {company_name}</b>", body))
    
    def get_image_flowable(b64_str: str, w, h):
        try:
            if ";base64," in b64_str:
                b64_str = b64_str.split(";base64,")[1]
            img_data = base64.b64decode(b64_str)
            return RLImage(BytesIO(img_data), width=w, height=h)
        except Exception as e:
            return Spacer(1, h)

    sig_block = []
    if signature_image or stamp_image:
        sig_flow = get_image_flowable(signature_image, 3.2 * cm, 1.1 * cm) if signature_image else Spacer(1, 1.1 * cm)
        stamp_flow = get_image_flowable(stamp_image, 1.6 * cm, 1.6 * cm) if stamp_image else Spacer(1, 1.6 * cm)
        
        tbl_data = [[sig_flow, stamp_flow]]
        t = Table(tbl_data, colWidths=[3.8 * cm, 2.8 * cm])
        t.setStyle(TableStyle([
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
            ('ALIGN', (0,0), (-1,-1), 'LEFT'),
            ('LEFTPADDING', (0,0), (-1,-1), 0),
            ('RIGHTPADDING', (0,0), (-1,-1), 0),
            ('BOTTOMPADDING', (0,0), (-1,-1), 0),
            ('TOPPADDING', (0,0), (-1,-1), 0),
        ]))
        sig_block.append(t)
    else:
        sig_block.append(Spacer(1, 0.6 * cm))

    sig_block.append(Paragraph("<b>Authorised Signatory</b>", body))
    sig_block.append(Paragraph("Name &amp; Designation: ___________________________", body))
    sig_block.append(Paragraph("Date: _____________________", body))
    
    story.append(KeepTogether(sig_block))
    story.append(sp_sigs)

    # Calculate content heights and adjust spacing dynamically
    content_width = A4[0] - MARGIN_LEFT - MARGIN_RIGHT
    avail_height = A4[1] - top_margin - bottom_margin

    def get_total_height():
        h_sum = 0
        for f in story:
            if isinstance(f, KeepTogether):
                for child in f._content:
                    _, h = child.wrap(content_width, 10000)
                    h_sum += h
                    if hasattr(child, 'style'):
                        h_sum += getattr(child.style, 'spaceBefore', 0)
                        h_sum += getattr(child.style, 'spaceAfter', 0)
            else:
                _, h = f.wrap(content_width, 10000)
                h_sum += h
                if hasattr(f, 'style'):
                    h_sum += getattr(f.style, 'spaceBefore', 0)
                    h_sum += getattr(f.style, 'spaceAfter', 0)
                if hasattr(f, 'spaceBefore'):
                    h_sum += getattr(f, 'spaceBefore', 0)
                if hasattr(f, 'spaceAfter'):
                    h_sum += getattr(f, 'spaceAfter', 0)
        return h_sum

    # Try fitting content on page
    current_height = get_total_height()
    spare_space = avail_height - current_height
    
    if spare_space > 25:
        # Distribute remaining height to the flexible spacers to spread content beautifully, leaving 25pt safety margin
        usable_spare = spare_space - 25
        sp_ref.height += usable_spare * 0.15
        sp_title.height += usable_spare * 0.15
        sp_terms.height += usable_spare * 0.20
        sp_closing.height += usable_spare * 0.20
        sp_sigs.height += usable_spare * 0.30
    elif spare_space < 0:
        # Content overflows: dynamically scale font down to force single-page fit
        for fs, ld in [(9.5, 12), (9.0, 11.5), (8.5, 10.5)]:
            body.fontSize = fs
            body.leading = ld
            bold.fontSize = fs
            bold.leading = ld
            section.fontSize = fs + 1
            section.leading = ld + 1
            bold_center.fontSize = fs + 4
            bold_center.leading = ld + 4
            title.fontSize = fs + 4
            title.leading = ld + 4
            if get_total_height() <= avail_height:
                break

    doc = SimpleDocTemplate(
        str(output_path),
        pagesize=A4,
        leftMargin=MARGIN_LEFT,
        rightMargin=MARGIN_RIGHT,
        topMargin=top_margin,
        bottomMargin=bottom_margin,
        title=f"Appointment Letter – {employee.employee_name}",
    )

    company_name_for_decorations = company_name or employee.company_name or "PaperlessBoss Private Limited"
    def on_page(canvas, document):
        _draw_page_decorations(canvas, document, header_path, footer_path, company_name=company_name_for_decorations)
    doc.build(story, onFirstPage=on_page, onLaterPages=on_page)

    return output_path
