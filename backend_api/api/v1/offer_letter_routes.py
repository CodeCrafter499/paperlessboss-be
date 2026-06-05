import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import get_db_session
from api.v1.auth import get_current_user
from db.models import User
from schemas.offer_letter import GenerateOfferLettersResponse, OfferLetterStatusResponse
from services.offer_letter.generation_service import (
    generate_letters_for_company,
    get_company_letter_status,
    resolve_download_path,
)
from services.offer_letter.repository import get_employees_by_company

router = APIRouter(prefix="/offer-letters", tags=["Offer Letters"])


def _sanitize_filename(name: str) -> str:
    safe = "".join(c if c.isalnum() or c in " _-" else "" for c in name)
    return safe.strip().replace(" ", "_")[:60] or "Employee"


@router.post("/generate", response_model=GenerateOfferLettersResponse)
async def generate_offer_letters(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    if not current_user.company_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Your user account is not linked to any company profile. Please create or update a company profile first.",
        )
    company_id = current_user.company_id
    if not await get_employees_by_company(db, company_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No employees found for this company",
        )
    return await generate_letters_for_company(db, company_id)


@router.get("/status", response_model=OfferLetterStatusResponse)
async def offer_letter_status(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    if not current_user.company_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Your user account is not linked to any company profile. Please create or update a company profile first.",
        )
    company_id = current_user.company_id
    if not await get_employees_by_company(db, company_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No employees found for this company",
        )
    return await get_company_letter_status(db, company_id)


@router.get("/download/{employee_id}/pdf")
async def download_offer_letter_pdf(
    employee_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    from sqlalchemy import select
    from db.models import Employee

    emp_company_id = await db.scalar(
        select(Employee.company_id).where(Employee.id == employee_id)
    )
    if not emp_company_id or not current_user.company_id or emp_company_id != current_user.company_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to access this offer letter."
        )
    return await _download_letter(db, employee_id, "pdf")


@router.get("/download/{employee_id}/docx")
async def download_offer_letter_docx(
    employee_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    from sqlalchemy import select
    from db.models import Employee

    emp_company_id = await db.scalar(
        select(Employee.company_id).where(Employee.id == employee_id)
    )
    if not emp_company_id or not current_user.company_id or emp_company_id != current_user.company_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to access this offer letter."
        )
    return await _download_letter(db, employee_id, "docx")


async def _download_letter(db: AsyncSession, employee_id: int, fmt: str) -> FileResponse:
    try:
        file_path, employee_name = await resolve_download_path(db, employee_id, fmt)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    media_type = (
        "application/pdf"
        if fmt == "pdf"
        else "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )
    extension = "pdf" if fmt == "pdf" else "docx"
    filename = f"Appointment_Letter_{_sanitize_filename(employee_name)}.{extension}"

    return FileResponse(
        path=file_path,
        media_type=media_type,
        filename=filename,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
