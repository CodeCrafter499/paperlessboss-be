import uuid
from datetime import datetime, timezone, timedelta
from typing import Annotated, Optional
from pydantic import BaseModel, EmailStr, Field, model_validator, PlainSerializer

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

class CompanyBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=255, description="Name of the Company")
    address: Optional[str] = Field(None, max_length=1000, description="Address of the Company")
    gstin: Optional[str] = Field(
        None, 
        pattern=r"^\d{2}[A-Za-z]{5}\d{4}[A-Za-z]{1}[A-Za-z0-9]{3}$",
        description="15-character GSTIN"
    )
    pan: Optional[str] = Field(
        None,
        pattern=r"^[A-Za-z]{5}\d{4}[A-Za-z]{1}$",
        description="10-character PAN"
    )
    cin: Optional[str] = Field(
        None,
        pattern=r"^[A-Za-z0-9]{21}$",
        description="21-character CIN"
    )
    labour_identification_number: Optional[str] = Field(None, max_length=255)
    email: Optional[EmailStr] = None
    mobile_no: Optional[str] = Field(None, max_length=20)

    @model_validator(mode="after")
    def validate_gstin_pan_match(self) -> "CompanyBase":
        if self.gstin and self.pan:
            extracted_pan = self.gstin[2:12].upper()
            if self.pan.upper() != extracted_pan:
                raise ValueError(
                    f"PAN ({self.pan.upper()}) does not match the 3rd to 12th characters of GSTIN ({extracted_pan})"
                )
        elif self.gstin and not self.pan:
            # Auto-extract PAN from GSTIN if PAN is not provided
            self.pan = self.gstin[2:12].upper()
        return self

class CompanyCreate(CompanyBase):
    mobile_no: Optional[str] = Field(
        None,
        pattern=r"^\d{10}$",
        description="10-digit Mobile Number"
    )

    @model_validator(mode="after")
    def validate_email_strict(self) -> "CompanyCreate":
        if self.email:
            import re
            email_str = str(self.email)
            if not re.match(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,6}$", email_str):
                raise ValueError("Invalid email format (TLD must be 2 to 6 characters long)")
        return self

class CompanyUpdate(CompanyCreate):
    name: Optional[str] = Field(None, min_length=1, max_length=255)

class CompanyOut(CompanyBase):
    id: uuid.UUID
    created_at: ISTDateTime
    updated_at: ISTDateTime

    model_config = {
        "from_attributes": True
    }


class SignatoryBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    address: Optional[str] = Field(None, max_length=1000)
    pan: Optional[str] = Field(
        None,
        pattern=r"^[A-Za-z]{5}\d{4}[A-Za-z]{1}$",
        description="10-character PAN of the Authorised Signatory"
    )
    email: Optional[EmailStr] = None
    mobile_no: Optional[str] = Field(None, max_length=20)
    signature_image: Optional[str] = None
    stamp_image: Optional[str] = None
    include_signature_stamp: Optional[bool] = False

    @model_validator(mode="after")
    def validate_image_sizes(self) -> "SignatoryBase":
        max_chars = 682666  # ~500 KB limit for base64 strings
        if self.signature_image and len(self.signature_image) > max_chars:
            raise ValueError("Signature image exceeds the maximum size limit of 500 KB.")
        if self.stamp_image and len(self.stamp_image) > max_chars:
            raise ValueError("Stamp image exceeds the maximum size limit of 500 KB.")
        return self

class SignatoryCreate(SignatoryBase):
    name: str = Field(
        ...,
        min_length=1,
        max_length=255,
        pattern=r"^[A-Za-z.\s]+$",
        description="Name of the Authorised Signatory (alphabets, dots, spaces only)"
    )
    mobile_no: Optional[str] = Field(
        None,
        pattern=r"^\d{10}$",
        description="10-digit Mobile Number of the Authorised Signatory"
    )

class SignatoryUpdate(SignatoryCreate):
    name: Optional[str] = Field(
        None,
        min_length=1,
        max_length=255,
        pattern=r"^[A-Za-z.\s]+$"
    )

class SignatoryOut(SignatoryBase):
    id: uuid.UUID
    user_id: uuid.UUID
    created_at: ISTDateTime
    updated_at: ISTDateTime

    model_config = {
        "from_attributes": True
    }

class CompanyLetterheadOut(BaseModel):
    id: uuid.UUID
    company_id: uuid.UUID
    version: int
    storage_file_location: str
    filename: str
    is_active: bool
    created_at: ISTDateTime
    updated_at: ISTDateTime

    model_config = {
        "from_attributes": True
    }

