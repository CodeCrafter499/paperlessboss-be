import uuid
import logging

from fastapi import APIRouter, Depends, HTTPException, status

logger = logging.getLogger(__name__)
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import get_db_session
from api.v1.auth import get_current_user
from db.models import User
from schemas.offer_letter import (
    GenerateOfferLettersResponse,
    OfferLetterStatusResponse,
    LogGenerationRequest,
    LogGenerationResponse,
    GenerationHistoryResponse,
)
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
    res = await generate_letters_for_company(db, company_id)
    
    # Log the successful generation event in generated_letter_logs for statistics
    if res.results:
        from sqlalchemy import select
        from db.models import Employee, GeneratedLetterLog
        
        emp_ids = [r.employee_id for r in res.results if r.status in ("generated", "already_existed")]
        if emp_ids:
            emp_stmt = select(Employee).where(Employee.id.in_(emp_ids))
            emp_res = await db.execute(emp_stmt)
            employees_map = {e.id: e for e in emp_res.scalars().all()}
            
            logs_to_add = []
            for r in res.results:
                if r.status in ("generated", "already_existed") and r.employee_id in employees_map:
                    emp = employees_map[r.employee_id]
                    # We can log it as a historical event
                    log_entry = GeneratedLetterLog(
                        user_id=current_user.id,
                        employee_id=emp.id,
                        company_id=current_user.company_id,
                        employee_name=emp.employee_name,
                        lin_number=emp.lin_number,
                        designation=emp.designation,
                        date_of_joining=emp.date_of_joining,
                        format="both",  # Server-side generate makes both
                        downloaded=False,
                    )
                    logs_to_add.append(log_entry)
            if logs_to_add:
                db.add_all(logs_to_add)
                try:
                    await db.commit()
                except Exception as db_err:
                    # Log the DB error, but don't fail the response since offer letters were generated
                    db.rollback()
                    logger.error(f"Failed to save generated letter history log: {db_err}")
                    
    return res


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
    return await _download_letter(db, employee_id, "pdf", current_user)


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
    return await _download_letter(db, employee_id, "docx", current_user)


async def _download_letter(db: AsyncSession, employee_id: int, fmt: str, current_user: User) -> FileResponse:
    try:
        file_path, employee_name = await resolve_download_path(db, employee_id, fmt)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    # Mark as downloaded in GeneratedLetterLog
    try:
        from sqlalchemy import update
        from db.models import GeneratedLetterLog
        from datetime import datetime
        from db.models import IST
        stmt = (
            update(GeneratedLetterLog)
            .where(
                GeneratedLetterLog.employee_id == employee_id,
                GeneratedLetterLog.user_id == current_user.id
            )
            .values(
                downloaded=True,
                downloaded_at=datetime.now(IST).replace(tzinfo=None),
                downloaded_by=current_user.id
            )
        )
        await db.execute(stmt)
        await db.commit()
    except Exception as log_err:
        logger.error(f"Failed to update download log: {log_err}")

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


@router.post("/log-generation", response_model=LogGenerationResponse)
async def log_generation(
    payload: LogGenerationRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    from db.models import GeneratedLetterLog
    
    logs_to_add = []
    for item in payload.logs:
        log_entry = GeneratedLetterLog(
            user_id=current_user.id,
            employee_id=item.employee_id,
            company_id=item.company_id or current_user.company_id,
            employee_name=item.employee_name,
            lin_number=item.lin_number,
            designation=item.designation,
            date_of_joining=item.date_of_joining,
            format=item.format,
            downloaded=False,
        )
        logs_to_add.append(log_entry)
        
    if logs_to_add:
        db.add_all(logs_to_add)
        await db.commit()
        for log in logs_to_add:
            await db.refresh(log)
        
    return LogGenerationResponse(
        success=True,
        count=len(logs_to_add),
        logs=logs_to_add
    )


@router.post("/log/{log_id}/download")
async def mark_log_as_downloaded(
    log_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    from db.models import GeneratedLetterLog
    from sqlalchemy import select
    from datetime import datetime
    from db.models import IST

    stmt = select(GeneratedLetterLog).where(
        GeneratedLetterLog.id == log_id,
        GeneratedLetterLog.user_id == current_user.id
    )
    res = await db.execute(stmt)
    log_entry = res.scalar_one_or_none()
    if not log_entry:
        raise HTTPException(status_code=404, detail="Log entry not found")

    log_entry.downloaded = True
    log_entry.downloaded_at = datetime.now(IST).replace(tzinfo=None)
    log_entry.downloaded_by = current_user.id
    await db.commit()
    return {"success": True}


@router.get("/generation-history", response_model=GenerationHistoryResponse)
async def get_generation_history(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    from sqlalchemy import select, func
    from sqlalchemy.orm import selectinload
    from db.models import GeneratedLetterLog
    from schemas.offer_letter import GeneratedLetterLogResponseItem

    # Count unique employees (by unique lin_number) for this user
    count_stmt = (
        select(func.count(func.distinct(GeneratedLetterLog.lin_number)))
        .where(GeneratedLetterLog.user_id == current_user.id)
    )
    unique_count = await db.scalar(count_stmt) or 0

    # Fetch history logs, ordered by generated_at desc
    history_stmt = (
        select(GeneratedLetterLog)
        .where(GeneratedLetterLog.user_id == current_user.id)
        .options(selectinload(GeneratedLetterLog.downloaded_by_user))
        .order_by(GeneratedLetterLog.generated_at.desc())
    )
    history_res = await db.execute(history_stmt)
    logs = history_res.scalars().all()

    res_logs = []
    for l in logs:
        email = l.downloaded_by_user.email if l.downloaded_by_user else None
        item = GeneratedLetterLogResponseItem(
            id=l.id,
            employee_id=l.employee_id,
            company_id=l.company_id,
            employee_name=l.employee_name,
            lin_number=l.lin_number,
            designation=l.designation,
            date_of_joining=l.date_of_joining,
            format=l.format,
            downloaded=l.downloaded,
            downloaded_at=l.downloaded_at,
            downloaded_by=l.downloaded_by,
            downloaded_by_email=email,
            generated_at=l.generated_at
        )
        res_logs.append(item)

    return GenerationHistoryResponse(
        unique_employees_count=unique_count,
        logs=res_logs
    )

