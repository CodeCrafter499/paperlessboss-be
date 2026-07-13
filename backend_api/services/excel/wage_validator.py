import pandas as pd

from .wage_rules import VALIDATION_RULES

from .utils import (
    excel_value_to_str,
    validate_regex,
    validate_numeric_length,
    validate_date,
    validate_word_limit,
    validate_designation,
    validate_numeric,
    get_aliased_value,
)


def validate_wage_excel(file_path):
    df = pd.read_excel(file_path)
    errors = []

    for index, row in df.iterrows():
        rec_id = index + 1
        row_dict = {str(k).strip(): v for k, v in row.to_dict().items()}

        for field, rules in VALIDATION_RULES.items():
            raw_val = get_aliased_value(row_dict, field, "")
            value = excel_value_to_str(raw_val)

            # Required field validation
            if rules.get("required") and value == "":
                errors.append({
                    "recId": rec_id,
                    "fieldName": field,
                    "errorMessage": f"{field} is required"
                })
                continue

            # Skip optional empty values
            if value == "":
                continue

            validation_type = rules["type"]

            # Text fields: any value is acceptable when provided
            if validation_type == "text":
                continue

            is_valid = True

            if validation_type == "regex":
                is_valid = validate_regex(
                    value,
                    rules["pattern"]
                )

            elif validation_type == "numeric_length":
                is_valid = validate_numeric_length(
                    value,
                    rules["length"]
                )

            elif validation_type == "date":
                is_valid = validate_date(
                    row_dict.get(field, ""),
                    rules["format"]
                )

            elif validation_type == "word_limit":
                is_valid = validate_word_limit(
                    value,
                    rules["limit"]
                )

            elif validation_type == "designation":
                is_valid = validate_designation(value)

            elif validation_type == "numeric":
                # For numeric, we can use the raw value
                is_valid = validate_numeric(row_dict.get(field, ""))

            if not is_valid:
                errors.append({
                    "recId": rec_id,
                    "fieldName": field,
                    "errorMessage": rules["message"]
                })

    return {
        "success": len(errors) == 0,
        "totalRecords": len(df),
        "validRecords": len(df) - len(set([e["recId"] for e in errors])),
        "invalidRecords": len(set([e["recId"] for e in errors])),
        "errors": errors
    }
