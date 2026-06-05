import uuid
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File
from sqlalchemy.ext.asyncio import AsyncSession
from api.deps import get_db_session
from api.v1.auth import get_current_user
from db.models import User
from schemas.profile import CompanyCreate, CompanyOut, SignatoryCreate, SignatoryOut
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


@router.post("/company/letterhead", status_code=status.HTTP_200_OK)
async def upload_company_letterhead(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
):
    from datetime import datetime, timezone, timedelta
    from sqlalchemy import select
    from db.models import AuthorisedSignatory, StorageMapping
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

    # Get user's signatory profile
    signatory = await db.scalar(
        select(AuthorisedSignatory).filter(AuthorisedSignatory.user_id == current_user.id)
    )
    if not signatory:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You must set up your authorised signatory details first before uploading a letterhead."
        )

    file_bytes = await file.read()

    # Upload to Supabase Storage
    filename = f"letterheads/{company_id}_{signatory.id}.pdf"
    content_type = "application/pdf"
    uploaded_path = upload_letterhead_to_supabase(file_bytes, filename, content_type)

    # Check if mapping already exists, update it, or insert a new one
    mapping = await db.scalar(
        select(StorageMapping).filter(
            StorageMapping.company_id == company_id,
            StorageMapping.authorised_signatory_id == signatory.id,
            StorageMapping.document_type == "letterhead"
        )
    )
    
    IST = timezone(timedelta(hours=5, minutes=30))
    now = datetime.now(IST).replace(tzinfo=None)

    if mapping:
        mapping.storage_file_location = uploaded_path
        mapping.updated_at = now
    else:
        mapping = StorageMapping(
            company_id=company_id,
            authorised_signatory_id=signatory.id,
            employee_id=None,
            document_type="letterhead",
            storage_file_location=uploaded_path,
            created_at=now,
            updated_at=now
        )
        db.add(mapping)
        
    try:
        await db.commit()
    except Exception as e:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to save mapping to database: {str(e)}"
        )

    return {
        "message": "Letterhead uploaded and mapped successfully.",
        "storage_file_location": uploaded_path,
        "company_id": company_id,
        "authorised_signatory_id": signatory.id
    }

