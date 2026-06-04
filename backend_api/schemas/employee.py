import uuid
from datetime import date
from typing import Optional, Union

from pydantic import BaseModel, ConfigDict


class EmployeeRecord(BaseModel):
    """Employee fields used to build an appointment letter."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    company_id: uuid.UUID
    employee_name: str
    date_of_birth: date
    father_mother_name: str
    aadhaar_number: int
    lin_number: str
    uan_esic_number: Optional[int] = None
    designation: str
    employment_type: str
    skill_category: str
    date_of_joining: date
    basic_pay: Union[float, int, str]
    dearness_allowance: Optional[Union[float, int, str]] = None
    other_allowance: Optional[Union[float, int, str]] = None
    social_security_benefits: Optional[str] = None
    duties_performed: Optional[str] = None
    benefits_under_chapter_vi: Optional[str] = None
    other_information: Optional[str] = None
