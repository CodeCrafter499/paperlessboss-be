from fastapi import APIRouter, Depends, HTTPException, status
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
