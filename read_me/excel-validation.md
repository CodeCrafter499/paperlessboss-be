# Excel Validation — What We Built

This document describes only the **Employee Excel Validation** feature added to the PaperlessBoss backend.

---

## Overview

When a user uploads an employee Excel file, the backend:

1. Accepts the file via `POST /validate-excel`
2. Validates every row against business rules
3. Returns a JSON report with errors (row number, column name, message)

**Important:** Validated employee data is **not saved to the database**. The file is stored temporarily in `uploads/` on the server; the API response is sent back to the frontend or Postman.

---

## Files and Folders Created

### Folder: `backend_api/services/excel/`

This folder contains the validation engine (3 Python files).

```text
backend_api/
└── services/
    └── excel/
        ├── rules.py       # Validation rules configuration
        ├── utils.py       # Reusable validation helper functions
        └── validator.py   # Main validation engine
```

### Route file (API endpoint)

```text
backend_api/api/v1/excel_routes.py   # POST /validate-excel
```

### Runtime folder (created on first upload)

```text
uploads/   # Temporary copy of uploaded .xlsx files
```

### Related dependencies (in `requirements.txt`)

| Package | Purpose |
|---------|---------|
| `pandas` | Read Excel files |
| `openpyxl` | Excel `.xlsx` engine |
| `python-multipart` | File upload in FastAPI |

---

## What Each File Does

### 1. `rules.py`

**Purpose:** Central place for all validation rules.

- Defines which Excel columns to validate
- Sets whether a field is **required** or **optional**
- Sets validation **type** (regex, date, numeric_length, etc.)
- Stores **error messages** shown in the API response

To add or change a rule, edit this file only.

---

### 2. `utils.py`

**Purpose:** Reusable validation logic (keeps `validator.py` clean).

| Function | What it does |
|----------|----------------|
| `excel_value_to_str()` | Converts Excel cell values (float, int, string) to a clean string |
| `normalize_numeric_id()` | Fixes Excel issues: `.0` suffix, missing leading zeros on Aadhaar/LIN/UAN |
| `validate_regex()` | Checks name fields (letters, space, dot only) |
| `validate_numeric_length()` | Checks exact digit count (12 or 10) |
| `validate_date()` | Checks `dd-mm-yyyy` format |
| `validate_word_limit()` | Checks maximum word count |
| `validate_designation()` | Designation: no digits allowed |
| `validate_numeric()` | Pay/allowance fields must be valid numbers |

---

### 3. `validator.py`

**Purpose:** Main validation engine.

1. Reads the Excel file with pandas
2. Loops through each **row** (employee record)
3. Loops through each **column** defined in `rules.py`
4. Calls the correct function from `utils.py`
5. Collects all errors
6. Returns summary JSON (`success`, `totalRecords`, `validRecords`, `invalidRecords`, `errors`)

---

### 4. `excel_routes.py` (endpoint)

**Purpose:** HTTP handler for file upload.

| Item | Value |
|------|-------|
| Method | `POST` |
| URL | `/validate-excel` |
| Body | `multipart/form-data`, field name: `file` |

Flow: receive file → save to `uploads/` → call `validate_excel()` → return JSON.

---

## Request Flow

```text
Frontend / Postman
        │
        │  POST /validate-excel  (file upload)
        ▼
excel_routes.py
        │
        │  save to uploads/
        ▼
validator.py
        │
        ├── reads rules from rules.py
        └── calls helpers in utils.py
        │
        ▼
JSON response to client
```

---

## API Response Format

```json
{
  "success": false,
  "totalRecords": 15,
  "validRecords": 10,
  "invalidRecords": 5,
  "errors": [
    {
      "recId": 1,
      "fieldName": "Name of employee",
      "errorMessage": "employee name shouldn't consist special characters except . and space"
    }
  ]
}
```

| Field | Meaning |
|-------|---------|
| `recId` | Row number (1 = first data row below the header) |
| `fieldName` | Excel column header that failed |
| `errorMessage` | Why validation failed |

---

## Validation Rules (17 Fields)

Excel **Row 1** must use these **exact** column headers:

| # | Column name | Required | Rule |
|---|-------------|----------|------|
| 1 | Name of employee | Yes | Only alphabets, spaces, and dot (`.`) |
| 2 | Date of birth | Yes | Format `dd-mm-yyyy` (e.g. `15-01-1990`) |
| 3 | Father's / Mother's name | Yes | Only alphabets, spaces, and dot (`.`) |
| 4 | Aadhaar number | Yes | Exactly 12 numeric digits |
| 5 | Labour Identification Number (LIN) of the establishment | Yes | Exactly 10 numeric digits |
| 6 | Universal Account Number (UAN) and / or Insurance Number (ESIC) (if available) | No | If provided: exactly 12 numeric digits |
| 7 | Designation | No | Alphabets, spaces, and special characters only (no digits) |
| 8 | Type of Employment | No | Text — any value accepted if provided |
| 9 | Category of Skill | No | Text — any value accepted if provided |
| 10 | Date of Joining | No | Format `dd-mm-yyyy` if provided |
| 11 | Basic Pay | No | Numeric value if provided |
| 12 | Dearness Allowance | No | Numeric value if provided |
| 13 | Other Allowance | No | Numeric value if provided |
| 14 | Applicability of social security benefits | No | Text — any value accepted if provided |
| 15 | Broad nature of duties performed | No | Maximum 100 words if provided |
| 16 | Benefits available under chapter VI (Maternity Benefit) of Code on Social Security, 2020 (in case of women employee) | No | Text — any value accepted if provided |
| 17 | Any other information | No | Text — any value accepted if provided |

---

## Validation Types

| Type | Used for |
|------|----------|
| `regex` | Name of employee, Father's / Mother's name |
| `date` | Date of birth, Date of Joining |
| `numeric_length` | Aadhaar (12), LIN (10), UAN/ESIC (12) |
| `designation` | Designation |
| `numeric` | Basic Pay, Dearness Allowance, Other Allowance |
| `word_limit` | Broad nature of duties performed (max 100 words) |
| `text` | Type of Employment, Category of Skill, social security, maternity benefits, any other information |

---

## Error Messages

| Field | Error message |
|-------|----------------|
| Name of employee | employee name shouldn't consist special characters except . and space |
| Date of birth | date of birth should be in dd-mm-yyyy format |
| Father's / Mother's name | parent name shouldn't consist special characters except . and space |
| Aadhaar number | aadhaar number should be 12 digits only numeric |
| LIN | LIN should be 10 digits only numeric |
| UAN/ESIC | UAN/ESIC should be 12 digits only numeric |
| Designation | designation should contain only alphabets, spaces and special characters |
| Date of Joining | date of joining should be in dd-mm-yyyy format |
| Basic Pay | basic pay should be a numeric value |
| Dearness Allowance | dearness allowance should be a numeric value |
| Other Allowance | other allowance should be a numeric value |
| Broad nature of duties performed | text should not exceed 100 words |
| Any required field (empty) | `{field name} is required` |

---

## Excel Handling Notes

- **Leading zeros:** Excel often stores Aadhaar/UAN/LIN as numbers and drops a leading `0`. The engine restores one leading zero when the value is exactly 1 digit short.
- **Float values:** Values like `123456789012.0` are normalized before validation.
- **Dates:** Valid Excel date cells are accepted in addition to `dd-mm-yyyy` text.

---

## Quick Test

```text
POST http://127.0.0.1:8000/validate-excel
Body: form-data → key: file → type: File → select .xlsx
```

For detailed Postman steps, see **`POSTMAN_EXCEL_VALIDATION_GUIDE.md`**.
