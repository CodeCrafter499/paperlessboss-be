from fastapi import APIRouter, UploadFile, File, HTTPException, status, Depends
import uuid
import urllib.request
import urllib.error
import logging
import json
from core.config import settings
from api.v1.auth import get_current_user
from db.models import User
from services.excel.validator import validate_excel

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


@router.post("/validate-excel")
async def validate_excel_api(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user)
):
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

    # Create a unique filename to avoid duplicates
    unique_filename = f"{uuid.uuid4().hex}_{file.filename}"
    content_type = file.content_type or "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

    # Upload to Supabase Storage
    upload_to_supabase(file_bytes, unique_filename, content_type)

    # Generate a signed URL for secure access
    signed_url = get_supabase_signed_url(unique_filename)

    return {
        "message": "Excel validated and stored successfully.",
        "storage_url": signed_url,
        "validation_result": result
    }



