import uuid
from datetime import date
from typing import Optional, Union

from pydantic import BaseModel, ConfigDict


class EmployeeRecord(BaseModel):
    """Employee fields used to build an appointment letter."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    company_id: uuid.UUID
    authorised_signatory_id: Optional[uuid.UUID] = None
    employee_name: str
    date_of_birth: date
    father_mother_name: str
    aadhaar_number: str
    lin_number: str
    uan_esic_number: Optional[str] = None
    designation: Optional[str] = None
    employment_type: Optional[str] = None
    skill_category: Optional[str] = None
    date_of_joining: Optional[date] = None
    basic_pay: Optional[Union[float, int, str]] = None
    dearness_allowance: Optional[Union[float, int, str]] = None
    other_allowance: Optional[Union[float, int, str]] = None
    social_security_benefits: Optional[str] = None
    duties_performed: Optional[str] = None
    benefits_under_chapter_vi: Optional[str] = None
    other_information: Optional[str] = None
