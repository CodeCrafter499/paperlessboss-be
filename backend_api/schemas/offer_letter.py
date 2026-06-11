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


from datetime import date, datetime

class GeneratedLetterLogItem(BaseModel):
    employee_name: str
    lin_number: str
    designation: Optional[str] = None
    date_of_joining: Optional[date] = None
    format: str
    employee_id: Optional[int] = None
    company_id: Optional[uuid.UUID] = None

class GeneratedLetterLogResponseItem(BaseModel):
    id: uuid.UUID
    employee_id: Optional[int] = None
    company_id: Optional[uuid.UUID] = None
    employee_name: str
    lin_number: str
    designation: Optional[str] = None
    date_of_joining: Optional[date] = None
    format: str
    downloaded: bool
    downloaded_at: Optional[datetime] = None
    downloaded_by: Optional[uuid.UUID] = None
    downloaded_by_email: Optional[str] = None
    generated_at: datetime

    class Config:
        from_attributes = True

class LogGenerationRequest(BaseModel):
    logs: list[GeneratedLetterLogItem]

class LogGenerationResponse(BaseModel):
    success: bool
    count: int
    logs: list[GeneratedLetterLogResponseItem] = []

class GenerationHistoryResponse(BaseModel):
    unique_employees_count: int
    logs: list[GeneratedLetterLogResponseItem]

