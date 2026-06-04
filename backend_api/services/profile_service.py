from typing import Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException, status
from db.models import User, Company, AuthorisedSignatory
from schemas.profile import CompanyCreate, SignatoryCreate

async def get_company_by_user(db: AsyncSession, user: User) -> Optional[Company]:
    if not user.company_id:
        return None
    stmt = select(Company).where(Company.id == user.company_id)
    result = await db.execute(stmt)
    return result.scalars().first()

async def upsert_company(db: AsyncSession, user: User, company_data: CompanyCreate) -> Company:
    # Normalize input fields to uppercase
    gstin = company_data.gstin.upper() if company_data.gstin else None
    pan = company_data.pan.upper() if company_data.pan else None
    cin = company_data.cin.upper() if company_data.cin else None

    company = None
    
    # Case 1: User is already linked to a company
    if user.company_id:
        stmt = select(Company).where(Company.id == user.company_id)
        company = (await db.execute(stmt)).scalars().first()
        if not company:
            user.company_id = None
            
    # Case 2: User is not linked, check if company with same GSTIN/CIN exists
    if not company:
        if gstin:
            stmt = select(Company).where(Company.gstin == gstin)
            existing = (await db.execute(stmt)).scalars().first()
            if existing:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="A company with this GSTIN is already registered. Please contact support or request an invitation to join."
                )
        if cin:
            stmt = select(Company).where(Company.cin == cin)
            existing = (await db.execute(stmt)).scalars().first()
            if existing:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="A company with this CIN is already registered. Please contact support or request an invitation to join."
                )
                
        # Create a new company
        company = Company(
            name=company_data.name,
            address=company_data.address,
            gstin=gstin,
            pan=pan,
            cin=cin,
            labour_identification_number=company_data.labour_identification_number,
            email=company_data.email,
            mobile_no=company_data.mobile_no
        )
        db.add(company)
        await db.flush() # Populate company.id
    else:
        # Update existing company details
        company.name = company_data.name
        if company_data.address is not None:
            company.address = company_data.address
        if gstin is not None:
            company.gstin = gstin
        if pan is not None:
            company.pan = pan
        if cin is not None:
            company.cin = cin
        if company_data.labour_identification_number is not None:
            company.labour_identification_number = company_data.labour_identification_number
        if company_data.email is not None:
            company.email = company_data.email
        if company_data.mobile_no is not None:
            company.mobile_no = company_data.mobile_no

    # Link user to the company if not already linked
    if user.company_id != company.id:
        user.company_id = company.id
        
    await db.commit()
    await db.refresh(company)
    return company

async def get_signatory_by_user(db: AsyncSession, user: User) -> Optional[AuthorisedSignatory]:
    stmt = select(AuthorisedSignatory).where(AuthorisedSignatory.user_id == user.id)
    result = await db.execute(stmt)
    return result.scalars().first()

async def upsert_signatory(db: AsyncSession, user: User, signatory_data: SignatoryCreate) -> AuthorisedSignatory:
    pan = signatory_data.pan.upper() if signatory_data.pan else None
    
    stmt = select(AuthorisedSignatory).where(AuthorisedSignatory.user_id == user.id)
    signatory = (await db.execute(stmt)).scalars().first()
    
    if signatory:
        signatory.name = signatory_data.name
        if signatory_data.address is not None:
            signatory.address = signatory_data.address
        if pan is not None:
            signatory.pan = pan
        if signatory_data.email is not None:
            signatory.email = signatory_data.email
        if signatory_data.mobile_no is not None:
            signatory.mobile_no = signatory_data.mobile_no
    else:
        signatory = AuthorisedSignatory(
            user_id=user.id,
            name=signatory_data.name,
            address=signatory_data.address,
            pan=pan,
            email=signatory_data.email,
            mobile_no=signatory_data.mobile_no
        )
        db.add(signatory)
        
    await db.commit()
    await db.refresh(signatory)
    return signatory
