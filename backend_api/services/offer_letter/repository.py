import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from services.offer_letter.tables import Employee, IST, OfferLetter
from schemas.employee import EmployeeRecord


from sqlalchemy.orm import selectinload


async def get_employees_by_company(db: AsyncSession, company_id: uuid.UUID) -> list[EmployeeRecord]:
    stmt = select(Employee).options(selectinload(Employee.company)).where(Employee.company_id == company_id)
    result = await db.execute(stmt)
    records = []
    for row in result.scalars().all():
        record = EmployeeRecord.model_validate(row)
        if row.company:
            record.company_name = row.company.name
        records.append(record)
    return records


async def get_offer_letter_by_employee(db: AsyncSession, employee_id: int) -> OfferLetter | None:
    stmt = select(OfferLetter).where(OfferLetter.employee_id == employee_id)
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def upsert_offer_letter(
    db: AsyncSession,
    employee_id: int,
    company_id: uuid.UUID,
    pdf_path: str,
    docx_path: str,
) -> None:
    existing = await get_offer_letter_by_employee(db, employee_id)
    now = datetime.now(IST).replace(tzinfo=None)
    if existing:
        existing.pdf_path = pdf_path
        existing.docx_path = docx_path
        existing.generated_at = now
    else:
        db.add(
            OfferLetter(
                employee_id=employee_id,
                company_id=company_id,
                pdf_path=pdf_path,
                docx_path=docx_path,
                generated_at=now,
            )
        )
    await db.commit()


async def get_employee_name(db: AsyncSession, employee_id: int) -> str | None:
    stmt = select(Employee.employee_name).where(Employee.id == employee_id)
    result = await db.execute(stmt)
    return result.scalar_one_or_none()
