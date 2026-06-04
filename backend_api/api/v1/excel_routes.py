from fastapi import APIRouter, UploadFile, File, HTTPException, status, Depends
import uuid
import urllib.request
import urllib.error
import logging
import json
import io
import pandas as pd
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from core.config import settings
from api.v1.auth import get_current_user
from api.deps import get_db_session
from db.models import User, Employee
from services.excel.validator import validate_excel
from services.excel.utils import excel_value_to_str, normalize_numeric_id

logger = logging.getLogger(__name__)
router = APIRouter()


def upload_to_supabase(file_bytes: bytes, filename: str, content_type: str) -> str:
    if not settings.SUPABASE_URL or not settings.SUPABASE_KEY:
        logger.warning("SUPABASE_URL or SUPABASE_KEY not configured. Mocking upload path.")
        return filename

    bucket = settings.SUPABASE_BUCKET
    supabase_url = settings.SUPABASE_URL.rstrip('/')
    url = f"{supabase_url}/storage/v1/object/{bucket}/{filename}"
    
    headers = {
        "Authorization": f"Bearer {settings.SUPABASE_KEY}",
        "apikey": settings.SUPABASE_KEY,
        "Content-Type": content_type
    }
    
    req = urllib.request.Request(url, data=file_bytes, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req) as response:
            return filename
    except urllib.error.HTTPError as e:
        error_msg = e.read().decode("utf-8")
        logger.error(f"Supabase upload failed: {error_msg}")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to save file to Supabase Storage: {error_msg}"
        )
    except Exception as e:
        logger.error(f"Supabase upload exception: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error uploading file to storage: {str(e)}"
        )


def get_supabase_signed_url(filename: str, expires_in: int = 900) -> str:
    if not settings.SUPABASE_URL or not settings.SUPABASE_KEY:
        logger.warning("SUPABASE_URL or SUPABASE_KEY not configured. Mocking signed URL.")
        return f"mock://supabase/storage/{settings.SUPABASE_BUCKET}/{filename}?token=mock_signed_token"

    bucket = settings.SUPABASE_BUCKET
    supabase_url = settings.SUPABASE_URL.rstrip('/')
    url = f"{supabase_url}/storage/v1/object/sign/{bucket}/{filename}"
    
    headers = {
        "Authorization": f"Bearer {settings.SUPABASE_KEY}",
        "apikey": settings.SUPABASE_KEY,
        "Content-Type": "application/json"
    }
    
    payload = json.dumps({"expiresIn": expires_in}).encode("utf-8")
    req = urllib.request.Request(url, data=payload, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req) as response:
            resp_bytes = response.read()
            resp_data = json.loads(resp_bytes.decode("utf-8"))
            signed_url = resp_data.get("signedURL") or resp_data.get("signedUrl")
            if not signed_url:
                logger.error(f"Supabase response missing signed URL fields: {resp_data}")
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail="Invalid response from Supabase Storage service."
                )
            return signed_url
    except urllib.error.HTTPError as e:
        error_msg = e.read().decode("utf-8")
        logger.error(f"Supabase signed URL generation failed: {error_msg}")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to generate signed URL from Supabase Storage: {error_msg}"
        )
    except Exception as e:
        logger.error(f"Supabase signed URL exception: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error generating download URL: {str(e)}"
        )


def parse_date_value(val):
    if val is None or pd.isna(val) or str(val).strip() == "":
        return None
    if isinstance(val, pd.Timestamp):
        return val.to_pydatetime().date()
    if isinstance(val, datetime):
        return val.date()
    text = excel_value_to_str(val)
    for fmt in ("%d-%m-%Y", "%Y-%m-%d", "%d/%m/%Y", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(text.split()[0], fmt).date()
        except (ValueError, IndexError):
            continue
    return None


def parse_numeric_value(val):
    if val is None or pd.isna(val) or str(val).strip() == "":
        return None
    cleaned = excel_value_to_str(val).replace(",", "").strip()
    try:
        return float(cleaned)
    except ValueError:
        return None


@router.post("/validate-excel")
async def validate_excel_api(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
):
    if not current_user.company_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Your user account is not linked to any company profile. Please create or update a company profile first before uploading employees."
        )

    # Enforce excel extension check
    if not (file.filename.endswith(".xlsx") or file.filename.endswith(".xls")):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid file format. Please upload a valid Excel file (.xlsx or .xls)."
        )

    # 1. Reset file pointer to ensure we start reading from the beginning
    await file.seek(0)

    try:
        # 2. Validate in-memory directly from file stream without storing locally first
        result = validate_excel(file.file)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Could not parse Excel file: {str(e)}"
        )

    # 3. If validation fails, raise 400 with the validation errors list
    if not result["success"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "message": "Excel validation failed. File has not been saved.",
                "validation_result": result
            }
        )

    # 4. If validation is successful, seek to beginning and read bytes for storage upload
    await file.seek(0)
    file_bytes = await file.read()

    # 5. Parse and save rows to the database
    try:
        df = pd.read_excel(io.BytesIO(file_bytes))
        
        employees_to_create = []
        for index, row_data in df.iterrows():
            row_dict = row_data.to_dict()
            
            emp_name = excel_value_to_str(row_dict.get("Name of employee", ""))
            dob = parse_date_value(row_dict.get("Date of birth"))
            father_mother = excel_value_to_str(row_dict.get("Father's / Mother's name", ""))
            
            aadhaar_number = normalize_numeric_id(row_dict.get("Aadhaar number", ""), 12) or None
            
            lin_number = excel_value_to_str(row_dict.get("Labour Identification Number (LIN) of the establishment", ""))
            
            uan_val = normalize_numeric_id(row_dict.get("Universal Account Number (UAN) and / or Insurance Number (ESIC) (if available)", ""), 12)
            uan_number = uan_val if uan_val else None
            
            designation = excel_value_to_str(row_dict.get("Designation", "")) or None
            employment_type = excel_value_to_str(row_dict.get("Type of Employment", "")) or None
            skill_category = excel_value_to_str(row_dict.get("Category of Skill", "")) or None
            
            doj = parse_date_value(row_dict.get("Date of Joining"))
            
            basic_pay = parse_numeric_value(row_dict.get("Basic Pay"))
            dearness_allowance = parse_numeric_value(row_dict.get("Dearness Allowance"))
            other_allowance = parse_numeric_value(row_dict.get("Other Allowance"))
            
            social_security = excel_value_to_str(row_dict.get("Applicability of social security benefits", "")) or None
            duties = excel_value_to_str(row_dict.get("Broad nature of duties performed", "")) or None
            benefits_chapter_vi = excel_value_to_str(row_dict.get("Benefits available under chapter VI (Maternity Benefit) of Code on Social Security, 2020 (in case of women employee)", "")) or None
            other_info = excel_value_to_str(row_dict.get("Any other information", "")) or None
            
            employee = Employee(
                company_id=current_user.company_id,
                employee_name=emp_name,
                date_of_birth=dob,
                father_mother_name=father_mother,
                aadhaar_number=aadhaar_number,
                lin_number=lin_number,
                uan_esic_number=uan_number,
                designation=designation,
                employment_type=employment_type,
                skill_category=skill_category,
                date_of_joining=doj,
                basic_pay=basic_pay,
                dearness_allowance=dearness_allowance,
                other_allowance=other_allowance,
                social_security_benefits=social_security,
                duties_performed=duties,
                benefits_under_chapter_vi=benefits_chapter_vi,
                other_information=other_info
            )
            employees_to_create.append(employee)
            
        db.add_all(employees_to_create)
        await db.commit()
        
    except Exception as db_err:
        logger.error(f"Error storing employees into database: {str(db_err)}")
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Excel validated successfully, but failed to save records to database: {str(db_err)}"
        )

    return {
        "message": "Excel validated and employees imported successfully.",
        "validation_result": result
    }



