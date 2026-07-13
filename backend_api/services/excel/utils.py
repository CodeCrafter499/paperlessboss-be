
import math
import re
from datetime import datetime

import pandas as pd


def excel_value_to_str(raw):

    if raw is None:
        return ""

    if isinstance(raw, float) and (math.isnan(raw) or pd.isna(raw)):
        return ""

    if isinstance(raw, str):
        value = raw.strip()
        return "" if value.lower() == "nan" else value

    if isinstance(raw, bool):
        return str(raw)

    if isinstance(raw, int):
        return str(raw)

    if isinstance(raw, float):
        if math.isfinite(raw) and raw == int(raw):
            return str(int(raw))
        return str(raw).strip()

    value = str(raw).strip()
    return "" if value.lower() == "nan" else value


def normalize_numeric_id(value, length):

    value = excel_value_to_str(value) if not isinstance(value, str) else value.strip()

    if not value:
        return ""

    if re.fullmatch(r"\d+\.0+", value):
        value = value.split(".", 1)[0]

    value = value.replace(" ", "")

    if not value.isdigit():
        return value

    # Excel numeric cells drop a leading zero (e.g. 040241582989 -> 40241582989)
    if len(value) == length - 1:
        value = value.zfill(length)

    return value


def validate_regex(value, pattern):

    return bool(re.match(pattern, value))


def validate_numeric_length(value, length):

    normalized = normalize_numeric_id(value, length)
    return normalized.isdigit() and len(normalized) == length


def validate_date(value, date_format):

    if isinstance(value, pd.Timestamp):
        return True

    if isinstance(value, datetime):
        return True

    text = excel_value_to_str(value)

    if not text:
        return False

    try:
        datetime.strptime(text, date_format)
        return True
    except ValueError:
        pass

    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%Y-%m-%d %H:%M:%S"):
        try:
            datetime.strptime(text.split()[0], fmt)
            return True
        except ValueError:
            continue

    return False


def validate_word_limit(value, limit):

    return len(value.split()) <= limit


def validate_designation(value):

    return bool(value) and not re.search(r"\d", value)


def validate_numeric(value):

    cleaned = excel_value_to_str(value).replace(",", "").strip()

    if not cleaned:
        return False

    try:
        float(cleaned)
        return True
    except ValueError:
        return False


COLUMN_ALIASES = {
    "Type of Employment": [
        "Type of Employment",
        "Type of Employment (Regular/Fixed-term-employment/Contractual)",
        "Type of Employment ",
    ],
    "Applicability of social security benefits": [
        "Applicability of social security benefits",
        "Applicability of social security [EPFO and ESIC] benefits",
    ],
    "Benefits available under chapter VI (Maternity Benefit) of Code on Social Security, 2020 (in case of women employee)": [
        "Benefits available under chapter VI (Maternity Benefit) of Code on Social Security, 2020 (in case of women employee)",
        "Benefits under chapter VI (Maternity Benefit) of Code on Social Security, 2020",
        "Benefits available under chapter VI (Maternity Benefit) of Code on Social Security, 2020",
    ]
}


def get_aliased_value(row_dict, field_name, default=""):
    val = row_dict.get(field_name)
    if val is not None and not (isinstance(val, float) and math.isnan(val)):
        return val

    aliases = COLUMN_ALIASES.get(field_name, [])
    for alias in aliases:
        val = row_dict.get(alias)
        if val is not None and not (isinstance(val, float) and math.isnan(val)):
            return val

    field_lower = field_name.lower().replace(" ", "")
    for k, v in row_dict.items():
        k_clean = str(k).lower().replace(" ", "")
        if field_lower in k_clean or k_clean in field_lower:
            if v is not None and not (isinstance(v, float) and math.isnan(v)):
                return v

    return default


