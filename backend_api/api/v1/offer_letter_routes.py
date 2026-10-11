import uuid
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks

logger = logging.getLogger(__name__)
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import get_db_session
from api.v1.auth import get_current_user
from db.models import User
from schemas.offer_letter import (
    GenerateOfferLettersRequest,
    GenerateOfferLettersResponse,
    OfferLetterStatusResponse,
    LogGenerationRequest,
    LogGenerationResponse,
    GenerationHistoryResponse,
)
from services.offer_letter.generation_service import (
    generate_letters_background_task,
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
    background_tasks: BackgroundTasks,
    req_body: Optional[GenerateOfferLettersRequest] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    if not current_user.company_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Your user account is not linked to any company profile. Please create or update a company profile first.",
        )
    company_id = current_user.company_id
    employees = await get_employees_by_company(db, company_id)
    if not employees:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No employees found for this company",
        )
    # Synchronously check subscription active status and employee limits
    from datetime import datetime
    from services.offer_letter.tables import IST
    now = datetime.now(IST).replace(tzinfo=None)

    is_subscription_active = bool(current_user.subscription_end_date and current_user.subscription_end_date >= now)
    if not is_subscription_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Your subscription plan is inactive or expired. Please subscribe to a plan in Billing & Subscription to generate letters."
        )

    if len(employees) > current_user.subscription_max_employees:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Your company has {len(employees)} employees, which exceeds your '{current_user.subscription_plan_name or 'Current'}' plan limit of {current_user.subscription_max_employees} employees. Please upgrade your plan in Billing & Subscription."
        )

    letterhead_id = req_body.letterhead_id if req_body else None
    # Reset existing offer letter paths for this company so the status endpoint tracks fresh generation live
    from sqlalchemy import update
    from services.offer_letter.tables import OfferLetter
    await db.execute(
        update(OfferLetter)
        .where(OfferLetter.company_id == company_id)
        .values(pdf_path=None, docx_path=None)
    )
    await db.commit()

    # Delete existing physical files on disk so status API reads 0% progress at start
    from services.offer_letter.storage import letter_paths
    for employee in employees:
        pdf_path, docx_path = letter_paths(company_id, employee.id)
        try:
            if pdf_path.is_file():
                pdf_path.unlink()
            if docx_path.is_file():
                docx_path.unlink()
        except Exception as e:
            logger.warning("Failed to clean up old letter files: %s", e)
    
    # Dispatch generation to background task
    background_tasks.add_task(
        generate_letters_background_task,
        company_id,
        current_user.id,
        letterhead_id
    )
    
    return GenerateOfferLettersResponse(
        company_id=company_id,
        total_employees=len(employees),
        generated=0,
        already_existed=0,
        results=[]
    )


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
    from datetime import datetime
    from services.offer_letter.tables import IST

    emp_company_id = await db.scalar(
        select(Employee.company_id).where(Employee.id == employee_id)
    )
    if not emp_company_id or not current_user.company_id or emp_company_id != current_user.company_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to access this offer letter."
        )

    now = datetime.now(IST).replace(tzinfo=None)
    is_docx_active = bool(
        current_user.has_docx_addon and current_user.docx_addon_end_date and current_user.docx_addon_end_date >= now
    )
    if not is_docx_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="DOCX format download requires the Editable DOCX Add-on (₹299/month). Please activate the add-on in Billing & Subscription."
        )

    return await _download_letter(db, employee_id, "docx", current_user)


from pydantic import BaseModel as _BaseModel

class DownloadOfferZipRequest(_BaseModel):
    format: str = "pdf"
    employee_ids: Optional[list[int]] = None


async def _download_zip_impl(
    format: str,
    employee_ids_list: Optional[list[int]],
    current_user: User,
    db: AsyncSession,
):
    import io
    import zipfile
    from fastapi.responses import Response
    from services.offer_letter.storage import letter_paths
    from datetime import datetime
    from db.models import IST, GeneratedLetterLog
    from sqlalchemy import update

    if not current_user.company_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Your account is not associated with a company profile."
        )

    now = datetime.now(IST).replace(tzinfo=None)
    is_plan_active = bool(
        current_user.subscription_end_date and current_user.subscription_end_date >= now
    )
    if not is_plan_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Your subscription plan is inactive or expired. Please subscribe to a plan in Billing & Credits."
        )

    # DOCX add-on validation
    if format in ("docx", "both"):
        is_docx_active = bool(
            current_user.has_docx_addon and current_user.docx_addon_end_date and current_user.docx_addon_end_date >= now
        )
        if not is_docx_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="DOCX format download requires the Editable DOCX Add-on (₹299/month). Please activate the add-on in Billing & Credits."
            )

    company_id = current_user.company_id
    employees = await get_employees_by_company(db, company_id)
    if not employees:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No employees found for this company."
        )

    if employee_ids_list:
        parsed_ids = set(employee_ids_list)
        employees = [e for e in employees if e.id in parsed_ids]
        if not employees:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No matching employees found for the requested batch."
            )

    # Check if files exist on disk; if not generated yet, generate them now
    ready_count = 0
    for emp in employees:
        p_path, d_path = letter_paths(company_id, emp.id)
        if p_path.is_file():
            ready_count += 1

    if ready_count < len(employees):
        logger.info("Generating missing letters before compiling ZIP...")
        await generate_letters_for_company(db, company_id, current_user.id)

    # Compile zip archive in-memory
    zip_buffer = io.BytesIO()
    files_added = 0
    seen_arcnames = set()

    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for emp in employees:
            pdf_path, docx_path = letter_paths(company_id, emp.id)
            emp_safe = _sanitize_filename(emp.employee_name)
            emp_unique_tag = f"_{emp.lin_number}" if emp.lin_number else f"_{emp.id}"

            if format in ("pdf", "both") and pdf_path.is_file():
                arc = f"Appointment_Letter_{emp_safe}.pdf"
                if arc in seen_arcnames:
                    arc = f"Appointment_Letter_{emp_safe}{emp_unique_tag}.pdf"
                counter = 1
                base_name = arc[:-4]
                while arc in seen_arcnames:
                    arc = f"{base_name}_{counter}.pdf"
                    counter += 1
                seen_arcnames.add(arc)
                zf.write(pdf_path, arcname=arc)
                files_added += 1

            if format in ("docx", "both") and docx_path.is_file():
                arc = f"Appointment_Letter_{emp_safe}.docx"
                if arc in seen_arcnames:
                    arc = f"Appointment_Letter_{emp_safe}{emp_unique_tag}.docx"
                counter = 1
                base_name = arc[:-5]
                while arc in seen_arcnames:
                    arc = f"{base_name}_{counter}.docx"
                    counter += 1
                seen_arcnames.add(arc)
                zf.write(docx_path, arcname=arc)
                files_added += 1

    if files_added == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No letters could be packaged into ZIP. Please try generating them first."
        )

    # Update download status in audit logs
    try:
        await db.execute(
            update(GeneratedLetterLog)
            .where(GeneratedLetterLog.company_id == company_id, GeneratedLetterLog.user_id == current_user.id)
            .values(
                downloaded=True,
                downloaded_at=now,
                downloaded_by=current_user.id
            )
        )
        await db.commit()
    except Exception as log_err:
        logger.warning("Failed to update download logs: %s", log_err)

    zip_buffer.seek(0)
    zip_filename = f"Appointment_Letters_{format.upper()}_{now.strftime('%d_%b_%Y')}.zip"

    return Response(
        content=zip_buffer.getvalue(),
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="{zip_filename}"',
            "Access-Control-Expose-Headers": "Content-Disposition"
        }
    )


@router.get("/download-zip")
async def download_offer_letters_zip_get(
    format: str = "pdf",  # "pdf", "docx", or "both"
    employee_ids: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    parsed_ids = None
    if employee_ids and employee_ids.strip():
        parsed_ids = [int(x.strip()) for x in employee_ids.split(",") if x.strip().isdigit()]
    return await _download_zip_impl(format, parsed_ids, current_user, db)


@router.post("/download-zip")
async def download_offer_letters_zip_post(
    payload: Optional[DownloadOfferZipRequest] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    fmt = payload.format if payload and payload.format else "pdf"
    emp_ids = payload.employee_ids if payload else None
    return await _download_zip_impl(fmt, emp_ids, current_user, db)
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

    # Count unique employees (by unique UAN number) for this user
    from db.models import Employee
    count_stmt = (
        select(func.count(func.distinct(Employee.uan_esic_number)))
        .join(GeneratedLetterLog, GeneratedLetterLog.employee_id == Employee.id)
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

    company_pan = None
    company_name = None
    if current_user.company_id:
        from db.models import Company
        comp = await db.get(Company, current_user.company_id)
        if comp:
            company_pan = comp.pan
            company_name = comp.name

    res_logs = []
    for l in logs:
        email = l.downloaded_by_user.email if l.downloaded_by_user else None
        item = GeneratedLetterLogResponseItem(
            id=l.id,
            employee_id=l.employee_id,
            company_id=l.company_id,
            company_pan=company_pan,
            employee_name=l.employee_name,
            lin_number=l.lin_number,
            uan_number=l.uan_number,
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
        company_pan=company_pan,
        company_name=company_name,
        logs=res_logs
    )

