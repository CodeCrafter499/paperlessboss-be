from fastapi import APIRouter, UploadFile, File
import shutil
import os

from services.excel.validator import validate_excel

router = APIRouter()


@router.post("/validate-excel")
async def validate_excel_api(
    file: UploadFile = File(...)
):

    os.makedirs("uploads", exist_ok=True)

    file_path = f"uploads/{file.filename}"

    with open(file_path, "wb") as buffer:

        shutil.copyfileobj(file.file, buffer)

    result = validate_excel(file_path)

    return result

