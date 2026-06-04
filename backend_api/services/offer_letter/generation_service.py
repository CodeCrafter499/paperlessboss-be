import logging
import uuid
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from schemas.offer_letter import (
    EmployeeLetterResult,
    EmployeeLetterStatus,
    GenerateOfferLettersResponse,
    OfferLetterStatusResponse,
)
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
) -> GenerateOfferLettersResponse:
    employees = await get_employees_by_company(db, company_id)
    results: list[EmployeeLetterResult] = []
    generated_count = 0
    existed_count = 0

    for employee in employees:
        try:
            existing = await get_offer_letter_by_employee(db, employee.id)
            if existing and paths_exist(existing.pdf_path, existing.docx_path):
                existed_count += 1
                results.append(
                    EmployeeLetterResult(
                        employee_id=employee.id,
                        employee_name=employee.employee_name,
                        status="already_existed",
                        pdf_url=pdf_download_url(employee.id),
                        docx_url=docx_download_url(employee.id),
                    )
                )
                continue

            pdf_path, docx_path = letter_paths(company_id, employee.id)
            generate_appointment_pdf(employee, pdf_path)
            generate_appointment_docx(employee, docx_path)

            await upsert_offer_letter(
                db,
                employee_id=employee.id,
                company_id=company_id,
                pdf_path=str(pdf_path),
                docx_path=str(docx_path),
            )

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
    statuses: list[EmployeeLetterStatus] = []
    ready_count = 0

    for employee in employees:
        record = await get_offer_letter_by_employee(db, employee.id)
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
