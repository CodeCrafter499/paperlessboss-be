import uuid
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File
from sqlalchemy.ext.asyncio import AsyncSession
from api.deps import get_db_session
from api.v1.auth import get_current_user
from db.models import User
from schemas.profile import CompanyCreate, CompanyOut, SignatoryCreate, SignatoryOut, CompanyLetterheadOut
from services import profile_service

router = APIRouter()

@router.get("/company", response_model=CompanyOut)
async def get_company(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
):
    company = await profile_service.get_company_by_user(db, current_user)
    if not company:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Company profile has not been filled out yet."
        )
    return company

@router.post("/company", response_model=CompanyOut, status_code=status.HTTP_200_OK)
async def upsert_company(
    company_data: CompanyCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
):
    company = await profile_service.upsert_company(db, current_user, company_data)
    return company

@router.get("/signatory", response_model=SignatoryOut)
async def get_signatory(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
):
    signatory = await profile_service.get_signatory_by_user(db, current_user)
    if not signatory:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Authorised signatory details have not been filled out yet."
        )
    return signatory

@router.post("/signatory", response_model=SignatoryOut, status_code=status.HTTP_200_OK)
async def upsert_signatory(
    signatory_data: SignatoryCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
):
    signatory = await profile_service.upsert_signatory(db, current_user, signatory_data)
    return signatory


@router.post("/company/letterhead", response_model=CompanyLetterheadOut, status_code=status.HTTP_200_OK)
async def upload_company_letterhead(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
):
    from sqlalchemy import select, func, update
    from db.models import CompanyLetterhead
    from services.offer_letter.letterhead import upload_letterhead_to_supabase

    if not current_user.company_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Your user account is not linked to any company profile. Please create or update a company profile first before uploading a letterhead."
        )

    company_id = current_user.company_id

    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid file format. Only PDF files are allowed for letterheads."
        )

    # 1. Determine next version number
    stmt_max_version = select(func.max(CompanyLetterhead.version)).where(
        CompanyLetterhead.company_id == company_id
    )
    max_version = await db.scalar(stmt_max_version)
    next_version = (max_version or 0) + 1

    # 2. Read bytes and upload to Supabase Storage
    file_bytes = await file.read()
    filename = f"letterheads/{company_id}_v{next_version}.pdf"
    content_type = "application/pdf"
    uploaded_path = upload_letterhead_to_supabase(file_bytes, filename, content_type)

    # 3. Mark all previous versions as inactive
    stmt_deactivate = (
        update(CompanyLetterhead)
        .where(CompanyLetterhead.company_id == company_id)
        .values(is_active=False)
    )
    await db.execute(stmt_deactivate)

    # 4. Insert new letterhead version
    new_letterhead = CompanyLetterhead(
        company_id=company_id,
        version=next_version,
        storage_file_location=uploaded_path,
        filename=file.filename,
        is_active=True
    )
    db.add(new_letterhead)
    
    try:
        await db.commit()
        await db.refresh(new_letterhead)
    except Exception as e:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to save letterhead details: {str(e)}"
        )

    return new_letterhead


@router.get("/company/letterheads", response_model=list[CompanyLetterheadOut])
async def list_company_letterheads(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
):
    from sqlalchemy import select
    from db.models import CompanyLetterhead

    if not current_user.company_id:
        return []

    stmt = select(CompanyLetterhead).where(
        CompanyLetterhead.company_id == current_user.company_id
    ).order_by(CompanyLetterhead.version.desc())
    
    result = await db.execute(stmt)
    return result.scalars().all()


@router.put("/company/letterheads/{letterhead_id}/activate", response_model=CompanyLetterheadOut)
async def activate_company_letterhead(
    letterhead_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
):
    from sqlalchemy import select, update
    from db.models import CompanyLetterhead

    if not current_user.company_id:
        raise HTTPException(status_code=400, detail="User is not associated with a company")

    stmt = select(CompanyLetterhead).where(
        CompanyLetterhead.id == letterhead_id,
        CompanyLetterhead.company_id == current_user.company_id
    )
    result = await db.execute(stmt)
    letterhead = result.scalar_one_or_none()

    if not letterhead:
        raise HTTPException(status_code=404, detail="Letterhead version not found")

    # Deactivate all other versions
    stmt_deactivate = (
        update(CompanyLetterhead)
        .where(CompanyLetterhead.company_id == current_user.company_id)
        .values(is_active=False)
    )
    await db.execute(stmt_deactivate)

    # Activate selected
    letterhead.is_active = True

    try:
        await db.commit()
        await db.refresh(letterhead)
    except Exception as e:
        await db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Failed to activate letterhead: {str(e)}"
        )

    return letterhead


@router.get("/company/letterheads/active/pdf")
async def get_active_letterhead_pdf(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
):
    from sqlalchemy import select
    from fastapi.responses import Response
    from db.models import CompanyLetterhead
    from services.offer_letter.letterhead import download_from_supabase, LETTERHEAD_PDF_PATH

    if not current_user.company_id:
        raise HTTPException(status_code=400, detail="User is not associated with a company")

    stmt = select(CompanyLetterhead).where(
        CompanyLetterhead.company_id == current_user.company_id,
        CompanyLetterhead.is_active == True
    )
    result = await db.execute(stmt)
    letterhead = result.scalar_one_or_none()

    if letterhead:
        try:
            pdf_bytes = download_from_supabase(letterhead.storage_file_location)
            return Response(content=pdf_bytes, media_type="application/pdf")
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to download active letterhead: {str(e)}")

    # Fallback to local default letterhead PDF
    if LETTERHEAD_PDF_PATH.is_file():
        try:
            with open(LETTERHEAD_PDF_PATH, "rb") as f:
                return Response(content=f.read(), media_type="application/pdf")
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to read local fallback letterhead: {str(e)}")

    raise HTTPException(status_code=404, detail="No active letterhead found")


@router.get("/company/letterheads/{letterhead_id}/pdf")
async def get_letterhead_pdf(
    letterhead_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
):
    from sqlalchemy import select
    from fastapi.responses import Response
    from db.models import CompanyLetterhead
    from services.offer_letter.letterhead import download_from_supabase

    if not current_user.company_id:
        raise HTTPException(status_code=400, detail="User is not associated with a company")

    stmt = select(CompanyLetterhead).where(
        CompanyLetterhead.id == letterhead_id,
        CompanyLetterhead.company_id == current_user.company_id
    )
    result = await db.execute(stmt)
    letterhead = result.scalar_one_or_none()

    if not letterhead:
        raise HTTPException(status_code=404, detail="Letterhead not found")

    try:
        pdf_bytes = download_from_supabase(letterhead.storage_file_location)
        return Response(content=pdf_bytes, media_type="application/pdf")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to download letterhead: {str(e)}")

