
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

