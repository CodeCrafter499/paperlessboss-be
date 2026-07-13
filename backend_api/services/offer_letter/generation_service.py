import logging
import uuid
from pathlib import Path
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from schemas.offer_letter import (
    EmployeeLetterResult,
    EmployeeLetterStatus,
    GenerateOfferLettersResponse,
    OfferLetterStatusResponse,
)
from services.offer_letter.letterhead import get_processed_letterhead
from services.offer_letter.docx_generator import generate_appointment_docx
from services.offer_letter.pdf_generator import generate_appointment_pdf
from services.offer_letter.repository import (
    get_employee_name,
    get_employees_by_company,
    get_offer_letter_by_employee,
    upsert_offer_letter,
)
from services.offer_letter.storage import letter_paths, paths_exist

logger = logging.getLogger(__name__)


def pdf_download_url(employee_id: int) -> str:
    return f"/offer-letters/download/{employee_id}/pdf"


def docx_download_url(employee_id: int) -> str:
    return f"/offer-letters/download/{employee_id}/docx"


async def generate_letters_for_company(
    db: AsyncSession,
    company_id: uuid.UUID,
    user_id: uuid.UUID,
    letterhead_id: Optional[uuid.UUID] = None,
) -> GenerateOfferLettersResponse:
    from db.models import User, Company
    user = await db.get(User, user_id)
    company = await db.get(Company, company_id)
    company_name = company.name if company else None
    employees = await get_employees_by_company(db, company_id)
    
    if not user:
        raise ValueError("User not found")
        
    if user.remaining_copies < len(employees):
        raise ValueError(
            f"Insufficient credits. You have {user.remaining_copies} remaining copies, "
            f"but you are trying to generate letters for {len(employees)} employees."
        )
    
    # Fetch signatory for signature / stamp inclusion
    from sqlalchemy import select
    from db.models import AuthorisedSignatory
    sig_result = await db.execute(select(AuthorisedSignatory).where(AuthorisedSignatory.user_id == user_id))
    sig = sig_result.scalars().first()
    
    signature_image = None
    stamp_image = None
    if sig and sig.include_signature_stamp:
        signature_image = sig.signature_image
        stamp_image = sig.stamp_image

    # Load all existing offer letters for this company in a single batch query
    from services.offer_letter.tables import OfferLetter
    stmt = select(OfferLetter).where(OfferLetter.company_id == company_id)
    res_letters = await db.execute(stmt)
    existing_letters = {ol.employee_id: ol for ol in res_letters.scalars().all()}

    results: list[EmployeeLetterResult] = []
    generated_count = 0
    existed_count = 0

    letterheads_cache = {}

    try:
        for employee in employees:
            try:
                existing = existing_letters.get(employee.id)

                sig_id = employee.authorised_signatory_id
                cache_key = (company_id, sig_id, letterhead_id)
                if cache_key not in letterheads_cache:
                    letterheads_cache[cache_key] = await get_processed_letterhead(
                        db, company_id, sig_id, letterhead_id=letterhead_id
                    )

                letterhead = letterheads_cache[cache_key]
                pdf_path, docx_path = letter_paths(company_id, employee.id)

                if letterhead and letterhead.available:
                    generate_appointment_pdf(
                        employee,
                        pdf_path,
                        header_path=str(letterhead.header_path) if letterhead.images_available else None,
                        footer_path=str(letterhead.footer_path) if letterhead.images_available else None,
                        signature_image=signature_image,
                        stamp_image=stamp_image,
                        company_name=company_name,
                    )
                    generate_appointment_docx(
                        employee,
                        docx_path,
                        header_bytes=letterhead.header_bytes,
                        footer_bytes=letterhead.footer_bytes,
                        signature_image=signature_image,
                        stamp_image=stamp_image,
                        company_name=company_name
                    )
                else:
                    generate_appointment_pdf(
                        employee,
                        pdf_path,
                        signature_image=signature_image,
                        stamp_image=stamp_image,
                        company_name=company_name
                    )
                    generate_appointment_docx(
                        employee,
                        docx_path,
                        signature_image=signature_image,
                        stamp_image=stamp_image,
                        company_name=company_name
                    )

                from services.offer_letter.tables import IST
                from datetime import datetime
                now = datetime.now(IST).replace(tzinfo=None)
                if existing:
                    existing.pdf_path = str(pdf_path)
                    existing.docx_path = str(docx_path)
                    existing.generated_at = now
                else:
                    new_letter = OfferLetter(
                        employee_id=employee.id,
                        company_id=company_id,
                        pdf_path=str(pdf_path),
                        docx_path=str(docx_path),
                        generated_at=now,
                    )
                    db.add(new_letter)
                    existing_letters[employee.id] = new_letter

                generated_count += 1
                results.append(
                    EmployeeLetterResult(
                        employee_id=employee.id,
                        employee_name=employee.employee_name,
                        status="generated",
                        pdf_url=pdf_download_url(employee.id),
                        docx_url=docx_download_url(employee.id),
                    )
                )
            except Exception as exc:
                logger.exception("Offer letter generation failed for employee_id=%s", employee.id)
                results.append(
                    EmployeeLetterResult(
                        employee_id=employee.id,
                        employee_name=employee.employee_name,
                        status="failed",
                        error=str(exc),
                    )
                )
        
        # Batch commit all inserts and updates in a single transaction
        if generated_count > 0:
            user.remaining_copies = max(0, user.remaining_copies - generated_count)
            db.add(user)
            try:
                await db.commit()
            except Exception as commit_exc:
                logger.error("Failed to commit generated offer letters to database: %s", commit_exc)
                await db.rollback()
                for r in results:
                    if r.status == "generated":
                        r.status = "failed"
                        r.error = f"Database save failed: {str(commit_exc)}"
                generated_count = 0

    finally:
        for lh in letterheads_cache.values():
            if lh:
                lh.cleanup()

    return GenerateOfferLettersResponse(
        company_id=company_id,
        total_employees=len(employees),
        generated=generated_count,
        already_existed=existed_count,
        results=results,
    )


async def get_company_letter_status(
    db: AsyncSession,
    company_id: uuid.UUID,
) -> OfferLetterStatusResponse:
    employees = await get_employees_by_company(db, company_id)
    
    # Fetch all existing offer letters for this company in a single batch query
    from sqlalchemy import select
    from services.offer_letter.tables import OfferLetter
    stmt = select(OfferLetter).where(OfferLetter.company_id == company_id)
    res_letters = await db.execute(stmt)
    existing_letters = {ol.employee_id: ol for ol in res_letters.scalars().all()}

    statuses: list[EmployeeLetterStatus] = []
    ready_count = 0

    for employee in employees:
        record = existing_letters.get(employee.id)
        ready = bool(record and paths_exist(record.pdf_path, record.docx_path))
        if ready:
            ready_count += 1
        statuses.append(
            EmployeeLetterStatus(
                employee_id=employee.id,
                employee_name=employee.employee_name,
                ready=ready,
                pdf_url=pdf_download_url(employee.id) if ready else None,
                docx_url=docx_download_url(employee.id) if ready else None,
                generated_at=record.generated_at.isoformat() if record and record.generated_at else None,
            )
        )

    return OfferLetterStatusResponse(
        company_id=company_id,
        total_employees=len(employees),
        ready_count=ready_count,
        employees=statuses,
    )


async def resolve_download_path(
    db: AsyncSession,
    employee_id: int,
    fmt: str,
) -> tuple[Path, str]:
    record = await get_offer_letter_by_employee(db, employee_id)
    if not record:
        raise FileNotFoundError("Offer letter not found")

    file_path = record.pdf_path if fmt == "pdf" else record.docx_path
    if not file_path or not Path(file_path).is_file():
        raise FileNotFoundError("Offer letter file not found")

    name = await get_employee_name(db, employee_id)
    return Path(file_path), name or "Employee"
