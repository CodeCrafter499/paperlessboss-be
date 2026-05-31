from datetime import timedelta
from fastapi import APIRouter, Depends, BackgroundTasks, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from api.deps import get_db_session
from schemas.auth import UserRegister, VerifyOTP, ResendOTP, UserLogin, TokenResponse, UserOut
from services import auth_service
from core.security import create_access_token, verify_access_token
from db.models import User

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
    db: AsyncSession = Depends(get_db_session)
):
    user = await auth_service.authenticate_user(db, login_data)
    access_token = create_access_token(subject=user.email)
    return {"access_token": access_token, "token_type": "bearer"}

@router.get("/me", response_model=UserOut)
async def read_current_user(current_user: User = Depends(get_current_user)):
    return current_user
