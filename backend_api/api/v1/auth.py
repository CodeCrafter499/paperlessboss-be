from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, BackgroundTasks, HTTPException, status, Request, Response
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_

from api.deps import get_db_session
from schemas.auth import UserRegister, VerifyOTP, ResendOTP, UserLogin, TokenResponse, UserOut, ContactRequest
from services import auth_service
from services.auth_service import IST
from core.security import create_access_token, verify_access_token, generate_refresh_token, hash_token
from core.config import settings
from db.models import User, RefreshToken, ContactMessage
from services.email import send_contact_email

router = APIRouter()

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")

async def get_current_user(
    db: AsyncSession = Depends(get_db_session),
    token: str = Depends(oauth2_scheme)
) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate authentication credentials.",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    email = verify_access_token(token)
    if email is None:
        raise credentials_exception
        
    stmt = select(User).where(User.email == email)
    result = await db.execute(stmt)
    user = result.scalars().first()
    
    if user is None:
        raise credentials_exception
        
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This user account has been deactivated."
        )
        
    return user

@router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
async def register(
    register_data: UserRegister,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db_session)
):
    user = await auth_service.register_user(db, register_data, background_tasks)
    return user

@router.post("/verify-otp", status_code=status.HTTP_200_OK)
async def verify_otp(
    verify_data: VerifyOTP,
    db: AsyncSession = Depends(get_db_session)
):
    await auth_service.verify_otp_code(db, verify_data)
    return {"message": "Email address verified successfully. You can now login."}

@router.post("/resend-otp", status_code=status.HTTP_200_OK)
async def resend_otp(
    data: ResendOTP,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db_session)
):
    await auth_service.resend_otp_code(db, data.email, background_tasks)
    return {"message": "A new verification code has been dispatched to your email."}

@router.post("/login", response_model=TokenResponse)
async def login(
    login_data: UserLogin,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db_session)
):
    user = await auth_service.authenticate_user(db, login_data)
    
    # Generate tokens
    access_token = create_access_token(subject=user.email)
    refresh_token = generate_refresh_token()
    hashed_refresh = hash_token(refresh_token)
    
    # Store refresh token in DB
    expires_at = datetime.now(IST).replace(tzinfo=None) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    db_refresh_token = RefreshToken(
        user_id=user.id,
        token=hashed_refresh,
        expires_at=expires_at
    )
    db.add(db_refresh_token)
    await db.commit()
    
    # Set HttpOnly Cookie
    secure_cookie = True
    if request.url.hostname in ("localhost", "127.0.0.1"):
        secure_cookie = False
        
    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        httponly=True,
        secure=secure_cookie,
        samesite="lax",
        max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60,
    )
    
    return {"access_token": access_token, "token_type": "bearer"}

@router.post("/refresh", response_model=TokenResponse)
async def refresh(
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db_session)
):
    refresh_token = request.cookies.get("refresh_token")
    if not refresh_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token is missing."
        )
        
    hashed_refresh = hash_token(refresh_token)
    now = datetime.now(IST).replace(tzinfo=None)
    
    # Query database for matching, valid refresh token
    stmt = select(RefreshToken).where(
        and_(
            RefreshToken.token == hashed_refresh,
            RefreshToken.is_revoked == False,
            RefreshToken.expires_at > now
        )
    )
    res = await db.execute(stmt)
    db_token = res.scalars().first()
    
    if not db_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token."
        )
        
    # Get user
    user_stmt = select(User).where(User.id == db_token.user_id)
    user_res = await db.execute(user_stmt)
    user = user_res.scalars().first()
    
    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account is inactive or not found."
        )
        
    # Rotate refresh token: Delete the old one
    await db.delete(db_token)
    
    # Generate new tokens
    new_refresh_token = generate_refresh_token()
    new_hashed_refresh = hash_token(new_refresh_token)
    new_expires_at = datetime.now(IST).replace(tzinfo=None) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    
    new_db_token = RefreshToken(
        user_id=user.id,
        token=new_hashed_refresh,
        expires_at=new_expires_at
    )
    db.add(new_db_token)
    await db.commit()
    
    access_token = create_access_token(subject=user.email)
    
    # Set HttpOnly Cookie
    secure_cookie = True
    if request.url.hostname in ("localhost", "127.0.0.1"):
        secure_cookie = False
        
    response.set_cookie(
        key="refresh_token",
        value=new_refresh_token,
        httponly=True,
        secure=secure_cookie,
        samesite="lax",
        max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60,
    )
    
    return {"access_token": access_token, "token_type": "bearer"}

@router.post("/logout")
async def logout(
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db_session)
):
    refresh_token = request.cookies.get("refresh_token")
    if refresh_token:
        hashed_refresh = hash_token(refresh_token)
        stmt = select(RefreshToken).where(RefreshToken.token == hashed_refresh)
        res = await db.execute(stmt)
        db_token = res.scalars().first()
        if db_token:
            await db.delete(db_token)
            await db.commit()
            
    secure_cookie = True
    if request.url.hostname in ("localhost", "127.0.0.1"):
        secure_cookie = False
        
    response.delete_cookie(
        key="refresh_token",
        httponly=True,
        secure=secure_cookie,
        samesite="lax"
    )
    return {"message": "Successfully logged out."}

@router.get("/me", response_model=UserOut)
async def read_current_user(current_user: User = Depends(get_current_user)):
    return current_user


@router.post("/contact")
async def contact_us(
    contact_data: ContactRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db_session)
):
    import uuid
    contact_msg = ContactMessage(
        id=uuid.uuid4(),
        name=contact_data.name,
        email=contact_data.email,
        mobile_no=contact_data.mobile_no,
        subject=contact_data.subject,
        message=contact_data.message
    )
    db.add(contact_msg)
    await db.commit()

    background_tasks.add_task(
        send_contact_email,
        contact_data.name,
        contact_data.email,
        contact_data.mobile_no,
        contact_data.subject,
        contact_data.message
    )
    return {"message": "Thank you for getting in touch! We will get back to you shortly."}


