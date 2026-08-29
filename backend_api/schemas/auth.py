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
    mobile_no: str = Field(..., min_length=10, max_length=10, pattern=r"^\d{10}$", description="Mobile number (exactly 10 digits)")
    agreed_to_terms: bool = Field(True, description="Whether the user agreed to the terms and conditions")

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
    mobile_no: str | None = None
    is_active: bool
    is_verified: bool
    created_at: ISTDateTime
    subscription_plan_name: str | None = None
    subscription_max_employees: int = 0
    subscription_end_date: ISTDateTime | None = None
    has_docx_addon: bool = False
    docx_addon_end_date: ISTDateTime | None = None

    model_config = {
        "from_attributes": True
    }


class ContactRequest(BaseModel):
    name: str
    email: EmailStr
    mobile_no: str
    subject: str
    message: str


