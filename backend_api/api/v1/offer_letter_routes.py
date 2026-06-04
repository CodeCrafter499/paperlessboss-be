import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import get_db_session
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


@router.post("/generate/{company_id}", response_model=GenerateOfferLettersResponse)
async def generate_offer_letters(
    company_id: uuid.UUID,
    db: AsyncSession = Depends(get_db_session),
):
    if not await get_employees_by_company(db, company_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No employees found for this company",
        )
    return await generate_letters_for_company(db, company_id)


@router.get("/status/{company_id}", response_model=OfferLetterStatusResponse)
async def offer_letter_status(
    company_id: uuid.UUID,
    db: AsyncSession = Depends(get_db_session),
):
    if not await get_employees_by_company(db, company_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No employees found for this company",
        )
    return await get_company_letter_status(db, company_id)


@router.get("/download/{employee_id}/pdf")
async def download_offer_letter_pdf(
    employee_id: int,
    db: AsyncSession = Depends(get_db_session),
):
    return await _download_letter(db, employee_id, "pdf")


@router.get("/download/{employee_id}/docx")
async def download_offer_letter_docx(
    employee_id: int,
    db: AsyncSession = Depends(get_db_session),
):
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
