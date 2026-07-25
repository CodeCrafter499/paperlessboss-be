import secrets
import hashlib
import logging
from datetime import datetime, timedelta, timezone
from sqlalchemy import select, and_, desc, delete
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException, status, BackgroundTasks

IST = timezone(timedelta(hours=5, minutes=30))

from db.models import User, OTPVerification, RefreshToken, AuthorisedSignatory, Company
from schemas.auth import UserRegister, VerifyOTP, UserLogin
from core.security import get_password_hash, verify_password
from core.config import settings
from services.email import send_otp_email

logger = logging.getLogger(__name__)

def generate_random_otp() -> str:
    return "".join(secrets.choice("0123456789") for _ in range(6))

def hash_otp_code(otp: str) -> str:
    return hashlib.sha256(otp.encode("utf-8")).hexdigest()

async def check_otp_cooldown(db: AsyncSession, email: str) -> None:
    now = datetime.now(IST).replace(tzinfo=None)
    stmt = (
        select(OTPVerification)
        .where(OTPVerification.email == email)
        .order_by(desc(OTPVerification.created_at))
    )
    result = await db.execute(stmt)
    last_otp = result.scalars().first()
    if last_otp:
        elapsed = now - last_otp.created_at
        if elapsed < timedelta(seconds=60):
            seconds_left = 60 - int(elapsed.total_seconds())
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Please wait {seconds_left} seconds before requesting a new verification code."
            )

async def register_user(db: AsyncSession, register_data: UserRegister, background_tasks: BackgroundTasks) -> User:
    stmt = select(User).where(User.email == register_data.email)
    result = await db.execute(stmt)
    existing_user = result.scalars().first()
    
    if existing_user:
        if existing_user.is_verified:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="A user with this email address is already registered."
            )
        else:
            await check_otp_cooldown(db, register_data.email)
            existing_user.hashed_password = get_password_hash(register_data.password)
            existing_user.mobile_no = register_data.mobile_no
            existing_user.created_at = datetime.now(IST).replace(tzinfo=None)
            
            stmt_invalidate = (
                select(OTPVerification)
                .where(
                    and_(
                        OTPVerification.email == register_data.email,
                        OTPVerification.is_used == False
                    )
                )
            )
            prev_otps = (await db.execute(stmt_invalidate)).scalars().all()
            for entry in prev_otps:
                entry.is_used = True
                
            otp_code = generate_random_otp()
            hashed_otp = hash_otp_code(otp_code)
            expires_at = datetime.now(IST).replace(tzinfo=None) + timedelta(minutes=settings.OTP_EXPIRY_MINUTES)
            
            new_otp_entry = OTPVerification(
                email=register_data.email,
                hashed_otp=hashed_otp,
                expires_at=expires_at,
                is_used=False
            )
            db.add(new_otp_entry)
            await db.commit()
            await db.refresh(existing_user)
            
            background_tasks.add_task(send_otp_email, register_data.email, otp_code)
            return existing_user
        
    await check_otp_cooldown(db, register_data.email)
    hashed_pwd = get_password_hash(register_data.password)
    new_user = User(
        email=register_data.email,
        hashed_password=hashed_pwd,
        mobile_no=register_data.mobile_no,
        is_verified=False,
        is_active=True,
        remaining_copies=100,
        remaining_wage_copies=100,
        agreed_to_terms=register_data.agreed_to_terms
    )
    db.add(new_user)
    await db.flush()
    
    otp_code = generate_random_otp()
    hashed_otp = hash_otp_code(otp_code)
    expires_at = datetime.now(IST).replace(tzinfo=None) + timedelta(minutes=settings.OTP_EXPIRY_MINUTES)
    
    otp_entry = OTPVerification(
        email=register_data.email,
        hashed_otp=hashed_otp,
        expires_at=expires_at,
        is_used=False
    )
    db.add(otp_entry)
    
    await db.commit()
    await db.refresh(new_user)
    
    background_tasks.add_task(send_otp_email, register_data.email, otp_code)
    return new_user

async def verify_otp_code(db: AsyncSession, verify_data: VerifyOTP) -> bool:
    hashed_input = hash_otp_code(verify_data.otp_code)
    now = datetime.now(IST).replace(tzinfo=None)
    
    stmt = (
        select(OTPVerification)
        .where(
            and_(
                OTPVerification.email == verify_data.email,
                OTPVerification.is_used == False,
                OTPVerification.expires_at > now
            )
        )
        .order_by(desc(OTPVerification.created_at))
    )
    result = await db.execute(stmt)
    otp_record = result.scalars().first()
    
    if not otp_record:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The verification code is incorrect or has expired."
        )
        
    if otp_record.attempts >= 5:
        otp_record.is_used = True
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Too many failed verification attempts. Please request a new code."
        )
        
    otp_record.attempts += 1
    
    if otp_record.hashed_otp != hashed_input:
        await db.commit()
        remaining = 5 - otp_record.attempts
        if remaining <= 0:
            otp_record.is_used = True
            await db.commit()
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Too many failed verification attempts. Please request a new code."
            )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"The verification code is incorrect. Attempts remaining: {remaining}"
        )
        
    otp_record.is_used = True
    
    user_stmt = select(User).where(User.email == verify_data.email)
    user_result = await db.execute(user_stmt)
    user = user_result.scalars().first()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Associated user account not found."
        )
        
    user.is_verified = True
    await db.commit()
    return True

async def resend_otp_code(db: AsyncSession, email: str, background_tasks: BackgroundTasks) -> bool:
    user_stmt = select(User).where(User.email == email)
    user_result = await db.execute(user_stmt)
    user = user_result.scalars().first()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No account registered with this email."
        )
        
    if user.is_verified:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This account is already verified."
        )
        
    await check_otp_cooldown(db, email)
    
    stmt_invalidate = (
        select(OTPVerification)
        .where(
            and_(
                OTPVerification.email == email,
                OTPVerification.is_used == False
            )
        )
    )
    prev_otps = (await db.execute(stmt_invalidate)).scalars().all()
    for entry in prev_otps:
        entry.is_used = True
        
    otp_code = generate_random_otp()
    hashed_otp = hash_otp_code(otp_code)
    expires_at = datetime.now(IST).replace(tzinfo=None) + timedelta(minutes=settings.OTP_EXPIRY_MINUTES)
    
    new_otp_entry = OTPVerification(
        email=email,
        hashed_otp=hashed_otp,
        expires_at=expires_at,
        is_used=False
    )
    db.add(new_otp_entry)
    await db.commit()
    
    background_tasks.add_task(send_otp_email, email, otp_code)
    return True

async def authenticate_user(db: AsyncSession, login_data: UserLogin) -> User:
    stmt = select(User).where(User.email == login_data.email)
    result = await db.execute(stmt)
    user = result.scalars().first()
    
    if not user or not verify_password(login_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Incorrect email or password."
        )
        
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This account has been deactivated."
        )
        
    if not user.is_verified:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Please verify your email address first using the OTP sent to your mailbox."
        )
        
    return user

async def delete_user_account(db: AsyncSession, user_id) -> None:
    stmt = select(User).where(User.id == user_id)
    result = await db.execute(stmt)
    user = result.scalars().first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
        
    company_id = user.company_id
    
    # Delete refresh tokens
    await db.execute(delete(RefreshToken).where(RefreshToken.user_id == user_id))
    
    # Delete signatory
    await db.execute(delete(AuthorisedSignatory).where(AuthorisedSignatory.user_id == user_id))
    
    # Delete user
    await db.delete(user)
    
    # Delete company (cascades to employees, wages, and letterheads)
    if company_id:
        company = (await db.execute(select(Company).where(Company.id == company_id))).scalars().first()
        if company:
            await db.delete(company)
            
    await db.commit()
