import uuid
from typing import Literal, Optional

from pydantic import BaseModel


class EmployeeLetterResult(BaseModel):
    employee_id: int
    employee_name: str
    status: Literal["generated", "already_existed", "failed"]
    pdf_url: Optional[str] = None
    docx_url: Optional[str] = None
    error: Optional[str] = None


class GenerateOfferLettersResponse(BaseModel):
    company_id: uuid.UUID
    total_employees: int
    generated: int
    already_existed: int
    results: list[EmployeeLetterResult]


class EmployeeLetterStatus(BaseModel):
    employee_id: int
    employee_name: str
    ready: bool
    pdf_url: Optional[str] = None
    docx_url: Optional[str] = None
    generated_at: Optional[str] = None


class OfferLetterStatusResponse(BaseModel):
    company_id: uuid.UUID
    total_employees: int
    ready_count: int
    employees: list[EmployeeLetterStatus]
