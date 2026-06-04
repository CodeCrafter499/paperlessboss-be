"""ORM mappings for existing `employees` and `offer_letters` tables (created elsewhere)."""

import uuid
from datetime import date, datetime, timezone, timedelta
from typing import Optional

from sqlalchemy import BigInteger, Date, DateTime, ForeignKey, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

IST = timezone(timedelta(hours=5, minutes=30))


class OfferLetterBase(DeclarativeBase):
    pass


class Employee(OfferLetterBase):
    __tablename__ = "employees"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    employee_name: Mapped[str] = mapped_column(String(100), nullable=False)
    date_of_birth: Mapped[date] = mapped_column(Date, nullable=False)
    father_mother_name: Mapped[str] = mapped_column(String(100), nullable=False)
    aadhaar_number: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False)
    lin_number: Mapped[str] = mapped_column(String(12), unique=True, nullable=False)
    uan_esic_number: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    designation: Mapped[str] = mapped_column(String(150), nullable=False)
    employment_type: Mapped[str] = mapped_column(String(100), nullable=False)
    skill_category: Mapped[str] = mapped_column(String(100), nullable=False)
    date_of_joining: Mapped[date] = mapped_column(Date, nullable=False)
    basic_pay: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    dearness_allowance: Mapped[Optional[float]] = mapped_column(Numeric(12, 2), nullable=True)
    other_allowance: Mapped[Optional[float]] = mapped_column(Numeric(12, 2), nullable=True)
    social_security_benefits: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    duties_performed: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    benefits_under_chapter_vi: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    other_information: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(IST).replace(tzinfo=None))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(IST).replace(tzinfo=None),
        onupdate=lambda: datetime.now(IST).replace(tzinfo=None),
    )


class OfferLetter(OfferLetterBase):
    __tablename__ = "offer_letters"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    employee_id: Mapped[int] = mapped_column(
        ForeignKey("employees.id", ondelete="CASCADE"), nullable=False, unique=True, index=True
    )
    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    pdf_path: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    docx_path: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    generated_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(IST).replace(tzinfo=None))
    employee: Mapped["Employee"] = relationship("Employee")
