import uuid
from datetime import datetime, timezone, timedelta
from typing import Annotated
from pydantic import BaseModel, EmailStr, Field, PlainSerializer

IST = timezone(timedelta(hours=5, minutes=30))

def ensure_ist(v: datetime) -> datetime:
    if v is None:
        return v
    if v.tzinfo is None:
        return v.replace(tzinfo=IST)
    return v.astimezone(IST)

ISTDateTime = Annotated[
    datetime,
    PlainSerializer(lambda v: ensure_ist(v).isoformat(), return_type=str)
]

class UserRegister(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=8, description="Password must be at least 8 characters long")

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class VerifyOTP(BaseModel):
    email: EmailStr
    otp_code: str = Field(
        ..., 
        min_length=6, 
        max_length=6, 
        pattern=r"^\d{6}$", 
        description="6-digit numeric OTP code"
    )

class ResendOTP(BaseModel):
    email: EmailStr

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"

class UserOut(BaseModel):
    id: uuid.UUID
    email: EmailStr
    is_active: bool
    is_verified: bool
    created_at: ISTDateTime

    model_config = {
        "from_attributes": True
    }

