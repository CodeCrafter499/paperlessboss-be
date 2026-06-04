# Offer Letter Generation

**PaperlessBoss · NLC India Renewables Limited · Appointment Letters (PDF + DOCX)**

Backend feature that generates formal NIRL appointment letters for every employee in a company, stores PDF and DOCX on disk, and exposes status and download APIs for the frontend.

---

## Table of contents

1. [Overview](#1-overview)
2. [Where this fits in PaperlessBoss](#2-where-this-fits-in-paperlessboss)
3. [How it works](#3-how-it-works)
4. [API reference](#4-api-reference)
5. [Code architecture](#5-code-architecture)
6. [Generate flow (step by step)](#6-generate-flow-step-by-step)
7. [Letter content](#7-letter-content)
8. [PDF, DOCX, and letterhead](#8-pdf-docx-and-letterhead)
9. [Storage](#9-storage)
10. [Error handling](#10-error-handling)
11. [Dependencies and deployment](#11-dependencies-and-deployment)
12. [Frontend integration](#12-frontend-integration)
13. [FAQ](#13-faq)

---

## 1. Overview

### The problem

HR at **NLC India Renewables Limited (NIRL)** must issue a formal **Appointment Letter** for each employee. Each letter must:

- Use the **official NIRL letterhead** on every page
- Follow a **fixed legal format** (Code on Wages 2019, Code on Social Security 2020, terms i–xvi, acknowledgement block)
- Be available as **PDF** (print/sign) and **DOCX** (edit in Word)

Doing this manually for hundreds of employees is slow and inconsistent.

### What we built

Four HTTP endpoints under `/api/v1/offer-letters/`:

| Endpoint | Purpose |
|----------|---------|
| `POST /generate/{company_id}` | Build PDF + DOCX for all employees in a company |
| `GET /status/{company_id}` | Per-employee readiness for the UI list |
| `GET /download/{employee_id}/pdf` | Stream the PDF |
| `GET /download/{employee_id}/docx` | Stream the DOCX |

**Input:** only `company_id` in the URL — no Excel, no JSON body.

**Data source:** employee rows already saved in the database after Excel validation. This feature reads them; it does not ingest or validate Excel.

**Scope of this doc:** routes, orchestration, PDF/DOCX generation, and file storage. The database is treated as an existing dependency — no schema work or local DB setup required to build or review this code.

---

## 2. Where this fits in PaperlessBoss

```text
  Excel file
      │
      ▼
  POST /validate-excel              "Is every row valid?"
      │
      ▼
  (Save validated rows to DB)       rows in `employees` for a `company_id`
      │
      ▼
  POST /offer-letters/generate/{company_id}    ← this feature
      │
      ▼
  GET /status  +  GET /download               UI list + file downloads
```

| Feature | Endpoint | Relation to offer letters |
|---------|----------|---------------------------|
| Auth | `/api/v1/auth/*` | Same DB session pattern via `get_db_session` |
| Excel validation | `POST /validate-excel` | Runs before data is trusted; see [`excel-validation.md`](excel-validation.md) |
| Employee persistence | *(import/save flow)* | Must run before generate |
| **Offer letters** | `/api/v1/offer-letters/*` | **This document** |

The React app (`paperlessboss/`) can still generate letters in the browser (`pdfGenerator.js`, `docxGenerator.js`). The backend mirrors that layout in Python so generation is centralized, consistent, and stored on the server.

---

## 3. How it works

```text
  company_id
      │
      ▼
  POST /generate/{company_id}
      │
      ├─ Load all employees for company from DB
      │
      └─ For each employee:
            ├─ Skip if PDF + DOCX already exist on disk
            ├─ Build PDF  (ReportLab + letterhead)
            ├─ Build DOCX (python-docx + letterhead)
            ├─ Save to generated_letters/{company_id}/{employee_id}/
            └─ Upsert paths in offer_letters table
      │
      ▼
  JSON: per-employee status + download URLs
```

After a successful run, the server holds:

**On disk:**

```text
paperlessboss-be/generated_letters/
  550e8400-e29b-41d4-a716-446655440000/    ← company_id
    1/                                      ← employee id
      appointment_letter.pdf
      appointment_letter.docx
```

**In the database** (`offer_letters` table): file paths and `generated_at` per employee.

---

## 4. API reference

Base URL: `http://localhost:8000` (local) or your deployed host.  
All paths are prefixed with **`/api/v1`**.

### Summary

| Method | Path | Body | Returns |
|--------|------|------|---------|
| POST | `/offer-letters/generate/{company_id}` | None | Batch result + URLs |
| GET | `/offer-letters/status/{company_id}` | — | Per-employee ready flag |
| GET | `/offer-letters/download/{employee_id}/pdf` | — | PDF file stream |
| GET | `/offer-letters/download/{employee_id}/docx` | — | DOCX file stream |

---

### POST `/offer-letters/generate/{company_id}`

```http
POST /api/v1/offer-letters/generate/550e8400-e29b-41d4-a716-446655440000
```

**Response (200):**

```json
{
  "company_id": "550e8400-e29b-41d4-a716-446655440000",
  "total_employees": 3,
  "generated": 2,
  "already_existed": 1,
  "results": [
    {
      "employee_id": 1,
      "employee_name": "Employee-6",
      "status": "generated",
      "pdf_url": "/offer-letters/download/1/pdf",
      "docx_url": "/offer-letters/download/1/docx"
    },
    {
      "employee_id": 2,
      "employee_name": "Employee-7",
      "status": "already_existed",
      "pdf_url": "/offer-letters/download/2/pdf",
      "docx_url": "/offer-letters/download/2/docx"
    },
    {
      "employee_id": 3,
      "employee_name": "Bad Row",
      "status": "failed",
      "error": "..."
    }
  ]
}
```

| `status` | Meaning |
|----------|---------|
| `generated` | New PDF + DOCX created; DB updated |
| `already_existed` | Files on disk and DB record OK — skipped |
| `failed` | Error for this employee only; others still processed |

| HTTP code | When |
|-----------|------|
| 404 | No employees for this `company_id` |

---

### GET `/offer-letters/status/{company_id}`

Returns readiness for every employee in the company. Used by the frontend for a list like "Letters ready: 8/10".

**Logic:** `ready = true` when an `offer_letters` row exists **and** both files are still on disk.

Returns **404** if the company has zero employees.

---

### GET `/offer-letters/download/{employee_id}/pdf|docx`

Streams the file with:

```http
Content-Disposition: attachment; filename="Appointment_Letter_Employee-6.pdf"
```

Filename is built from the sanitized `employee_name` in the database.

Returns **404** if no record exists or the file was deleted from disk.

---

## 5. Code architecture

Four layers — routes stay thin; generators never touch SQL.

```text
┌─────────────────────────────────────────────────────────┐
│  HTTP          offer_letter_routes.py                   │
│                URLs, status codes, FileResponse         │
└──────────────────────────┬──────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────┐
│  Orchestration generation_service.py                    │
│                Loop, skip-if-exists, per-row errors      │
└────────────┬─────────────────────────────┬──────────────┘
             │                             │
┌────────────▼────────────┐   ┌────────────▼─────────────┐
│  Data access            │   │  Document generation       │
│  repository.py          │   │  pdf_generator.py          │
│  tables.py              │   │  docx_generator.py         │
│                         │   │  field_definitions.py      │
│                         │   │  letterhead.py, storage.py │
└────────────┬────────────┘   └────────────────────────────┘
             │
┌────────────▼────────────────────────────────────────────┐
│  PostgreSQL (employees, offer_letters) + disk + assets  │
└─────────────────────────────────────────────────────────┘
```

### Why `EmployeeRecord`?

Generators take a Pydantic `EmployeeRecord` (`schemas/employee.py`), not an ORM object. That keeps PDF/DOCX code independent of SQLAlchemy. The repository converts DB rows with `EmployeeRecord.model_validate(row)`.

### File tree

```text
paperlessboss-be/
├── offer_letter_generation.md          ← this doc
├── generated_letters/                  ← output (gitignored)
└── backend_api/
    ├── api/
    │   ├── main.py                     ← registers router, letterhead startup check
    │   ├── deps.py                     ← get_db_session()
    │   └── v1/offer_letter_routes.py
    ├── assets/
    │   ├── NIRL_Letter_Head_Mar_2026.pdf
    │   └── .letterhead_cache/          ← auto-created, gitignored
    ├── schemas/
    │   ├── employee.py                 ← EmployeeRecord
    │   └── offer_letter.py             ← API response models
    └── services/offer_letter/
        ├── tables.py                   ← ORM mappings to existing DB tables
        ├── repository.py               ← reads employees, upserts offer_letters
        ├── generation_service.py       ← orchestration
        ├── storage.py                  ← path rules + existence checks
        ├── field_definitions.py        ← letter text (terms i–xvi)
        ├── letterhead.py               ← PDF → header/footer images
        ├── pdf_generator.py
        └── docx_generator.py
```

### Database contract (assumed to exist)

These tables are already in place when this feature runs. This code does not create or migrate them.

| Table | Role |
|-------|------|
| `companies` | Org grouping; `company_id` in URLs references this |
| `employees` | Letter content — one row per person |
| `offer_letters` | Generated file paths; one row per employee (`employee_id` unique) |

**Employee fields used in the letter:**

| Column | Used in letter |
|--------|----------------|
| `employee_name` | Dear line, term (i), acknowledgement |
| `date_of_birth` | Term (ii), `dd/mm/yyyy` |
| `father_mother_name` | Term (iii) |
| `aadhaar_number` | Term (iv) |
| `lin_number` | Term (v) |
| `uan_esic_number` | Term (vi), or blank if null |
| `designation` | Subject + term (vii) |
| `employment_type` | Term (viii) |
| `skill_category` | Term (ix) |
| `date_of_joining` | Term (x) |
| `basic_pay`, `dearness_allowance` | Term (xi), e.g. `20000 / 2000` |
| `other_allowance` | Term (xii) |
| `social_security_benefits` | Term (xiii) |
| `duties_performed` | Term (xiv) |
| `benefits_under_chapter_vi` | Term (xv) |
| `other_information` | Term (xvi) |

---

## 6. Generate flow (step by step)

Use this chain when debugging.

```text
offer_letter_routes.generate_offer_letters(company_id, db)
    │
    ├─ repository.get_employees_by_company(db, company_id)
    │     → list[EmployeeRecord]
    │
    ├─ if empty → HTTP 404
    │
    └─ generation_service.generate_letters_for_company(db, company_id)
           │
           └─ FOR EACH employee:
                  │
                  ├─ get_offer_letter_by_employee(db, employee.id)
                  ├─ paths_exist(pdf, docx)?  → yes: status=already_existed, continue
                  │
                  ├─ letter_paths(company_id, employee.id)
                  ├─ generate_appointment_pdf(employee, pdf_path)
                  ├─ generate_appointment_docx(employee, docx_path)
                  ├─ upsert_offer_letter(db, ids, paths)
                  └─ status=generated
                  │
                  ON EXCEPTION → log + status=failed (loop continues)
```

**Skip-if-exists:** if both files are on disk and the DB row points to them, regeneration is skipped. If files were deleted manually but the DB row remains, `paths_exist` returns false and the letter is rebuilt.

---

## 7. Letter content

All wording lives in **`field_definitions.py`** so PDF and DOCX stay identical.

### Structure

| # | Content | Source |
|---|---------|--------|
| 1 | `Date: 04 June 2026` | Today, Indian long format |
| 2 | `Ref: APT/2026/0007` | `appointment_ref(employee.id)` — id zero-padded to 4 digits |
| 3 | `APPOINTMENT LETTER` | Centered, bold, underlined |
| 4 | Green horizontal rule | Styling |
| 5 | `Dear {employee_name},` | DB |
| 6 | `Sub: Appointment as {designation} – reg.` | Bold + underlined |
| 7 | Opening paragraph | Legal boilerplate constant |
| 8 | `TERMS OF APPOINTMENT` | Section heading |
| 9 | Terms i–xvi | `FIELD_DEFINITIONS` |
| 10 | Closing paragraph | Constant |
| 11 | `For NLC India Renewables Limited` | Signature block |
| 12 | Authorised signatory lines | Blank underscores |
| 13 | `ACKNOWLEDGEMENT BY EMPLOYEE` | Employee name filled in |
| 14 | Signature / date lines | Blank underscores |

Empty optional values print `________________________`.

This matches the sample `Appointment_Employee-6.pdf` and the frontend `docxGenerator.js` field list.

---

## 8. PDF, DOCX, and letterhead

### Letterhead (`letterhead.py`)

The brand PDF is rasterized once and cached:

1. Load `backend_api/assets/NIRL_Letter_Head_Mar_2026.pdf`
2. Render page 1 at 150 DPI (`pdf2image` + Poppler)
3. Crop top ~35% → header; bottom ~10% → footer
4. Cache PNGs in `assets/.letterhead_cache/`

- **PDF:** drawn on every page via ReportLab canvas callbacks
- **DOCX:** embedded in section header and footer

If the PDF is missing, startup logs a warning and generators fall back to plain text `"NLC India Renewables Limited"`.

### PDF (`pdf_generator.py`)

ReportLab `SimpleDocTemplate`, A4. Margins: top 2.5 cm, bottom 2 cm, sides 1.8 cm.

### DOCX (`docx_generator.py`)

python-docx, Arial 10 pt body / 14 pt title / 11 pt headings. Each term row uses three runs: bold roman, bold label, normal value.

**Why both formats?** PDF for the official record; DOCX for last-minute edits before printing.

---

## 9. Storage

| Store | Holds | Why |
|-------|-------|-----|
| **Disk** (`generated_letters/`) | PDF and DOCX bytes | Large files; direct download |
| **DB** (`offer_letters`) | Paths + `generated_at` | Fast lookup, UI status, skip-if-exists |

Path rule (`storage.py`):

```text
paperlessboss-be/generated_letters/{company_id}/{employee_id}/appointment_letter.pdf
paperlessboss-be/generated_letters/{company_id}/{employee_id}/appointment_letter.docx
```

---

## 10. Error handling

| Situation | Behaviour |
|-----------|-----------|
| No employees for company | HTTP 404 |
| One employee fails mid-batch | `status: failed` for that row only |
| Letterhead missing | Warning at startup; plain text header in letters |
| Download, no DB row | HTTP 404 |
| Download, file deleted from disk | HTTP 404 |
| Second generate, files intact | `already_existed` |

Failures are logged with `logger.exception` and the employee id in `generation_service.py`.

---

## 11. Dependencies and deployment

### Python packages

| Package | Used for |
|---------|----------|
| `reportlab` | PDF |
| `python-docx` | DOCX |
| `pdf2image` | Letterhead rasterization |
| `Pillow` | Image crop/cache |

### System

| Environment | Requirement |
|-------------|-------------|
| Docker | `poppler-utils` in `backend_api/Dockerfile` |
| Windows local | Poppler on PATH for `pdf2image` |

### Git

| Path | Action |
|------|--------|
| `generated_letters/` | Gitignore — generated output |
| `backend_api/assets/.letterhead_cache/` | Gitignore — derived images |
| `backend_api/assets/NIRL_Letter_Head_Mar_2026.pdf` | **Commit** — required in production |

### Startup

1. Check letterhead PDF → warn if missing
2. Ping database (existing auth startup)
3. Serve requests — offer-letter routes work once employee rows exist

End-to-end verification happens when the shared database is live and populated; no local DB setup is needed to develop this feature.

---

## 12. Frontend integration

When wiring the React app to this backend instead of client-side jsPDF/docx:

1. After validated rows are saved, keep `company_id` in app state.
2. **Generate:** `POST ${API}/api/v1/offer-letters/generate/${companyId}` — no body; show progress from `results`.
3. **List:** `GET ${API}/api/v1/offer-letters/status/${companyId}` → map `employees` to `LettersList`.
4. **Download:** `window.open(\`${API}/api/v1${pdf_url}\`)` (add auth header when JWT is enforced).

Response URLs are relative (`/offer-letters/download/1/pdf`) — prefix with `/api/v1` and your API host.

---

## 13. FAQ

**Why doesn't generate accept Excel or JSON?**  
Data ingestion is a separate step. Generate only reads trusted rows already in the database.

**Where does `0007` in `APT/2026/0007` come from?**  
`employees.id`, zero-padded to four digits — not the Excel row number.

**Can one employee have two offer letter rows?**  
No. `employee_id` is unique on `offer_letters`; upsert updates the same row.

**What if employee data changes after generating?**  
Old files remain until regeneration. Delete the files (and optionally the `offer_letters` row) to force a rebuild. A future `force=true` flag is not implemented yet.

**Same layout as the React generators?**  
Yes — same field labels and structure; backend uses ReportLab and python-docx.

**Who saves employees after Excel validation?**  
Outside this feature. Generate only requires rows to exist for the given `company_id`.

---

*For Excel validation only, see [`excel-validation.md`](excel-validation.md).*
