from __future__ import annotations
import uuid
from typing import Optional
from datetime import datetime, timezone, timedelta, date
from sqlalchemy import String, Boolean, DateTime, ForeignKey, Integer, BigInteger, CheckConstraint, Numeric, Text, Date
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

IST = timezone(timedelta(hours=5, minutes=30))

class Base(DeclarativeBase):
    pass

class Company(Base):
    __tablename__ = "companies"
    
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    address: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    gstin: Mapped[str | None] = mapped_column(String(15), nullable=True, index=True)
    pan: Mapped[str | None] = mapped_column(String(10), nullable=True, index=True)
    cin: Mapped[str | None] = mapped_column(String(21), nullable=True, index=True)
    labour_identification_number: Mapped[str | None] = mapped_column(String(255), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    mobile_no: Mapped[str | None] = mapped_column(String(20), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(IST).replace(tzinfo=None))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, 
        default=lambda: datetime.now(IST).replace(tzinfo=None), 
        onupdate=lambda: datetime.now(IST).replace(tzinfo=None)
    )
    
    users: Mapped[list["User"]] = relationship("User", back_populates="company")

class User(Base):
    __tablename__ = "users"
    
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    company_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(IST).replace(tzinfo=None))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, 
        default=lambda: datetime.now(IST).replace(tzinfo=None), 
        onupdate=lambda: datetime.now(IST).replace(tzinfo=None)
    )
    
    company: Mapped[Optional[Company]] = relationship("Company", back_populates="users")
    authorised_signatory: Mapped[Optional[AuthorisedSignatory]] = relationship("AuthorisedSignatory", back_populates="user", uselist=False)

class AuthorisedSignatory(Base):
    __tablename__ = "authorised_signatories"
    
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    address: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    pan: Mapped[str | None] = mapped_column(String(10), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    mobile_no: Mapped[str | None] = mapped_column(String(20), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(IST).replace(tzinfo=None))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, 
        default=lambda: datetime.now(IST).replace(tzinfo=None), 
        onupdate=lambda: datetime.now(IST).replace(tzinfo=None)
    )
    
    user: Mapped["User"] = relationship("User", back_populates="authorised_signatory")

class OTPVerification(Base):
    __tablename__ = "otp_verifications"
    
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    hashed_otp: Mapped[str] = mapped_column(String(255), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    is_used: Mapped[bool] = mapped_column(Boolean, default=False)
    attempts: Mapped[int] = mapped_column(default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(IST).replace(tzinfo=None))

class RefreshToken(Base):
    __tablename__ = "refresh_tokens"
    
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    token: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    is_revoked: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(IST).replace(tzinfo=None))
    
    user: Mapped["User"] = relationship("User")


class Employee(Base):
    __tablename__ = "employees"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), 
        ForeignKey("companies.id", ondelete="CASCADE"), 
        nullable=False,
        index=True
    )
    authorised_signatory_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("authorised_signatories.id", ondelete="SET NULL"),
        nullable=True,
        index=True
    )

    # Employee Details
    employee_name: Mapped[str] = mapped_column(String(100), nullable=False)
    date_of_birth: Mapped[date] = mapped_column(Date, nullable=False)
    father_mother_name: Mapped[str] = mapped_column(String(100), nullable=False)

    # Aadhaar Number - 12 digits
    aadhaar_number: Mapped[str] = mapped_column(
        String(12),
        CheckConstraint(
            "aadhaar_number ~ '^[0-9]{12}$'",
            name="chk_aadhaar_12_digits"
        ),
        unique=True,
        nullable=False
    )

    # LIN Number - Alphanumeric (allows characters & special symbols)
    lin_number: Mapped[str] = mapped_column(
        String(100),
        nullable=False
    )

    # UAN / ESIC Number - 12 digits (matches the 12-digit Excel validator constraint)
    uan_esic_number: Mapped[Optional[str]] = mapped_column(
        String(12),
        CheckConstraint(
            "uan_esic_number ~ '^[0-9]{12}$'",
            name="chk_uan_esic_12_digits"
        ),
        unique=True,
        nullable=True
    )

    # Employment Details
    designation: Mapped[Optional[str]] = mapped_column(
        String(150),
        nullable=True,
        index=True
    )
    employment_type: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True
    )
    skill_category: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True
    )
    date_of_joining: Mapped[Optional[date]] = mapped_column(
        Date,
        nullable=True,
        index=True
    )

    # Monetary Fields
    basic_pay: Mapped[Optional[float]] = mapped_column(
        Numeric(12, 2),
        nullable=True
    )
    dearness_allowance: Mapped[Optional[float]] = mapped_column(
        Numeric(12, 2),
        nullable=True
    )
    other_allowance: Mapped[Optional[float]] = mapped_column(
        Numeric(12, 2),
        nullable=True
    )

    social_security_benefits: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True
    )
    duties_performed: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True
    )
    benefits_under_chapter_vi: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True
    )
    other_information: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(IST).replace(tzinfo=None))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, 
        default=lambda: datetime.now(IST).replace(tzinfo=None), 
        onupdate=lambda: datetime.now(IST).replace(tzinfo=None)
    )

    company: Mapped["Company"] = relationship("Company")
    authorised_signatory: Mapped[Optional["AuthorisedSignatory"]] = relationship("AuthorisedSignatory")



class StorageMapping(Base):
    __tablename__ = "storage_mapping"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4
    )

    authorised_signatory_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("authorised_signatories.id", ondelete="CASCADE"),
        nullable=False
    )

    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False
    )

    employee_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("employees.id", ondelete="CASCADE"),
        nullable=True
    )

    document_type: Mapped[str] = mapped_column(
        String(100),
        nullable=False
    )

    storage_file_location: Mapped[str] = mapped_column(
        Text,
        nullable=False
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(IST).replace(tzinfo=None),
        nullable=False
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(IST).replace(tzinfo=None),
        onupdate=lambda: datetime.now(IST).replace(tzinfo=None),
        nullable=False
    )


class OfferLetter(Base):
    __tablename__ = "offer_letters"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    employee_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("employees.id", ondelete="CASCADE"), nullable=False, unique=True, index=True
    )
    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    pdf_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    docx_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    generated_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(IST).replace(tzinfo=None)
    )

    employee: Mapped[Employee] = relationship("Employee")
