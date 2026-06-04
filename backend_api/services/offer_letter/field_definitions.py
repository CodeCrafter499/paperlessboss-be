from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any, Callable, Optional

from schemas.employee import EmployeeRecord

BLANK = "________________________"


@dataclass(frozen=True)
class FieldDefinition:
    roman: str
    label: str
    getter: Callable[[EmployeeRecord], str]


def _format_date(d: Optional[date]) -> str:
    if d is None:
        return ""
    return d.strftime("%d/%m/%Y")


def _str_value(val: Any) -> str:
    if val is None:
        return ""
    if isinstance(val, Decimal):
        return format(val, "f").rstrip("0").rstrip(".") if val % 1 else str(int(val))
    return str(val).strip()


def _wages_composite(emp: EmployeeRecord) -> str:
    basic = _str_value(emp.basic_pay)
    da = _str_value(emp.dearness_allowance)
    if basic and da:
        return f"{basic} / {da}"
    if basic:
        return basic
    return da


FIELD_DEFINITIONS: list[FieldDefinition] = [
    FieldDefinition("i", "Name of employee", lambda e: _str_value(e.employee_name)),
    FieldDefinition("ii", "Date of birth", lambda e: _format_date(e.date_of_birth)),
    FieldDefinition("iii", "Father's / Mother's name", lambda e: _str_value(e.father_mother_name)),
    FieldDefinition("iv", "Aadhaar number (after obtaining consent)", lambda e: _str_value(e.aadhaar_number)),
    FieldDefinition("v", "Labour Identification Number (LIN) of the establishment", lambda e: _str_value(e.lin_number)),
    FieldDefinition(
        "vi",
        "Universal Account Number (UAN) and / or Insurance Number (ESIC) (if available)",
        lambda e: _str_value(e.uan_esic_number),
    ),
    FieldDefinition("vii", "Designation", lambda e: _str_value(e.designation)),
    FieldDefinition(
        "viii",
        "Type of Employment (Regular/Fixed-term-employment/Contractual)",
        lambda e: _str_value(e.employment_type),
    ),
    FieldDefinition("ix", "Category of skill", lambda e: _str_value(e.skill_category)),
    FieldDefinition("x", "Date of joining", lambda e: _format_date(e.date_of_joining)),
    FieldDefinition("xi", "Wages/Basic Pay and Dearness Allowance", _wages_composite),
    FieldDefinition(
        "xii",
        "Other allowance including accommodation whichever is/are applicable",
        lambda e: _str_value(e.other_allowance),
    ),
    FieldDefinition(
        "xiii",
        "Applicability of social security [EPFO and ESIC] benefits",
        lambda e: _str_value(e.social_security_benefits),
    ),
    FieldDefinition("xiv", "Broad Nature of duties to be performed", lambda e: _str_value(e.duties_performed)),
    FieldDefinition(
        "xv",
        "Benefits under chapter VI (Maternity Benefit) of Code on Social Security, 2020",
        lambda e: _str_value(e.benefits_under_chapter_vi),
    ),
    FieldDefinition("xvi", "Any other information", lambda e: _str_value(e.other_information)),
]


OPENING_PARAGRAPH = (
    "We are pleased to appoint you in our organisation on the terms and conditions stated below, "
    "in accordance with the Code on Wages, 2019 and the Code on Social Security, 2020. "
    "Please retain this letter for your records."
)

CLOSING_PARAGRAPH = (
    "Please sign and return a copy of this letter as acknowledgement of your acceptance "
    "of the above terms and conditions."
)


def indian_long_date(d: date) -> str:
    return d.strftime("%d %B %Y")


def appointment_ref(employee_id: int, year: int) -> str:
    return f"APT/{year}/{employee_id:04d}"
