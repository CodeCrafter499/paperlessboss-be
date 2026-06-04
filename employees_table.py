from sqlalchemy import (
    create_engine,
    Column,
    Integer,
    String,
    BigInteger,
    Text,
    Date,
    Numeric,
    CheckConstraint
)
from sqlalchemy.orm import declarative_base

DATABASE_URL = (
    "postgresql+psycopg2://postgres.skzceavurcikyajjtpar:"
    "PaperLessBoss2026@aws-1-ap-northeast-2.pooler.supabase.com:5432/postgres"
)

engine = create_engine(DATABASE_URL)

Base = declarative_base()


class Employee(Base):
    __tablename__ = "employees"

    id = Column(Integer, primary_key=True, autoincrement=True)

    # Employee Details
    employee_name = Column(String(100), nullable=False)

    date_of_birth = Column(Date, nullable=False)

    father_mother_name = Column(String(100), nullable=False)

    # Aadhaar Number - 12 digits
    aadhaar_number = Column(
        BigInteger,
        CheckConstraint(
            "aadhaar_number >= 100000000000 AND aadhaar_number <= 999999999999",
            name="chk_aadhaar_12_digits"
        ),
        unique=True,
        nullable=False
    )

    # LIN Number - 10 digits
    lin_number = Column(
        BigInteger,
        CheckConstraint(
            "lin_number >= 1000000000 AND lin_number <= 9999999999",
            name="chk_lin_10_digits"
        ),
        unique=True,
        nullable=False
    )

    # UAN / ESIC Number - 10 digits
    uan_esic_number = Column(
        BigInteger,
        CheckConstraint(
            "uan_esic_number >= 1000000000 AND uan_esic_number <= 9999999999",
            name="chk_uan_esic_10_digits"
        ),
        unique=True,
        nullable=True
    )

    # Employment Details
    designation = Column(
        String(150),
        nullable=False,
        index=True
    )

    employment_type = Column(
        String(100),
        nullable=False
    )

    skill_category = Column(
        String(100),
        nullable=False
    )

    date_of_joining = Column(
        Date,
        nullable=False,
        index=True
    )

    # Monetary Fields
    basic_pay = Column(
        Numeric(12, 2),
        nullable=False
    )

    dearness_allowance = Column(
        Numeric(12, 2),
        nullable=True
    )

    other_allowance = Column(
        Numeric(12, 2),
        nullable=True
    )

    social_security_benefits = Column(
        String(255),
        nullable=True
    )

    duties_performed = Column(
        Text,
        nullable=True
    )

    benefits_under_chapter_vi = Column(
        Text,
        nullable=True
    )

    other_information = Column(
        Text,
        nullable=True
    )


Base.metadata.create_all(engine)

print("Employee table created successfully!")