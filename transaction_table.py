from sqlalchemy import (
    Column,
    Integer,
    Date,
    Numeric,
    ForeignKey,
    Text,
    DateTime,
    Enum
)
from sqlalchemy.dialects.postgresql import UUID
import uuid
from datetime import datetime


class Transaction(Base):
    __tablename__ = "transactions"

    id = Column(Integer, primary_key=True, autoincrement=True)

    transaction_id = Column(
        UUID(as_uuid=True),
        default=uuid.uuid4,
        unique=True,
        nullable=False
    )

    transaction_date = Column(Date, nullable=False)

    authorized_signatory_id = Column(
        Integer,
        ForeignKey("authorized_signatories.id"),
        nullable=False
    )

    company_id = Column(
        Integer,
        ForeignKey("companies.id"),
        nullable=False
    )

    transaction_type = Column(
        Enum("appointment", "payslip",
             name="transaction_type_enum"),
        nullable=False
    )

    transaction_count = Column(
        Integer,
        nullable=False,
        default=1
    )

    total_bill = Column(
        Numeric(12, 2),
        nullable=False
    )

    status = Column(
        Enum(
            "pending",
            "completed",
            "cancelled",
            name="transaction_status_enum"
        ),
        nullable=False,
        default="pending"
    )

    remarks = Column(Text, nullable=True)

    created_at = Column(
        DateTime,
        default=datetime.utcnow
    )

    updated_at = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow
    )