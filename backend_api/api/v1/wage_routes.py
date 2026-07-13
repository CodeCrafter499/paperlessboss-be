from fastapi import APIRouter, UploadFile, File, HTTPException, status, Depends
from fastapi.responses import FileResponse
from pathlib import Path
import uuid
import logging
import io
import pandas as pd
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from core.config import settings
from api.v1.auth import get_current_user
from api.deps import get_db_session
from db.models import User, WageSlip, Company
from services.excel.wage_validator import validate_wage_excel
from services.excel.utils import excel_value_to_str, normalize_numeric_id, get_aliased_value
from services.offer_letter.wage_pdf_generator import generate_wage_slip_pdf

logger = logging.getLogger(__name__)
router = APIRouter()

def parse_numeric_value(val):
    if val is None or pd.isna(val) or str(val).strip() == "":
        return None
    cleaned = excel_value_to_str(val).replace(",", "").strip()
    try:
        return float(cleaned)
    except ValueError:
        return None

@router.post("/validate-excel")
async def validate_wage_excel_api(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
):
    if not current_user.company_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Your user account is not linked to any company profile."
        )

    if not (file.filename.endswith(".xlsx") or file.filename.endswith(".xls")):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid file format. Please upload a valid Excel file."
        )

    await file.seek(0)
    try:
        result = validate_wage_excel(file.file)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Could not parse Excel file: {str(e)}"
        )

    if not result["success"]:
        return result

    await file.seek(0)
    file_bytes = await file.read()

    # Parse and save to database
    try:
        df = pd.read_excel(io.BytesIO(file_bytes))
        num_records = len(df)
        if current_user.remaining_wage_copies < num_records:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Insufficient credits. You have {current_user.remaining_wage_copies} remaining wage slip copies, but the file contains {num_records} rows."
            )

        # Fetch existing wage slips to perform updates instead of duplicate inserts
        existing_query = select(WageSlip).where(WageSlip.company_id == current_user.company_id)
        res = await db.execute(existing_query)
        existing_wages = {
            (w.employee_name, w.wage_month, w.wage_year): w 
            for w in res.scalars().all()
        }

        for index, row_data in df.iterrows():
            row_dict = {str(k).strip(): v for k, v in row_data.to_dict().items()}

            emp_name = excel_value_to_str(get_aliased_value(row_dict, "1. Name of employee", ""))
            father_mother_spouse = excel_value_to_str(get_aliased_value(row_dict, "2. Father's/Mother's/Spouse Name", ""))
            designation = excel_value_to_str(get_aliased_value(row_dict, "3. Designation", "")) or None
            
            uan_val = normalize_numeric_id(get_aliased_value(row_dict, "4. UAN", ""), 12)
            uan = uan_val if uan_val else None

            bank_acc = excel_value_to_str(get_aliased_value(row_dict, "5. Bank Account Number", "")) or None
            wage_month = excel_value_to_str(get_aliased_value(row_dict, "6a. Wage month", "")) or None
            
            year_val = parse_numeric_value(get_aliased_value(row_dict, "6b. Wage Year"))
            wage_year = int(year_val) if year_val else None

            rate_basic = parse_numeric_value(get_aliased_value(row_dict, "7a.Rate of Basic"))
            rate_da = parse_numeric_value(get_aliased_value(row_dict, "7b. Rate of DA"))
            rate_allow = parse_numeric_value(get_aliased_value(row_dict, "7c. Rate of Allowances"))

            attendance = parse_numeric_value(get_aliased_value(row_dict, "8. Total attendance/unit of work done"))
            ot_wages = parse_numeric_value(get_aliased_value(row_dict, "9. Overtime wages"))
            gross = parse_numeric_value(get_aliased_value(row_dict, "10. Gross wages payable"))

            pf = parse_numeric_value(get_aliased_value(row_dict, "11a. PF"))
            esi = parse_numeric_value(get_aliased_value(row_dict, "11b. ESI"))
            others = parse_numeric_value(get_aliased_value(row_dict, "11c. Others"))
            net_wages = parse_numeric_value(get_aliased_value(row_dict, "12. Net wages paid"))

            key = (emp_name, wage_month, wage_year)
            if key in existing_wages:
                # Update existing record
                wage_slip = existing_wages[key]
                wage_slip.father_mother_spouse_name = father_mother_spouse
                wage_slip.designation = designation
                wage_slip.uan = uan
                wage_slip.bank_account_number = bank_acc
                wage_slip.rate_basic = rate_basic
                wage_slip.rate_da = rate_da
                wage_slip.rate_allowances = rate_allow
                wage_slip.total_attendance = attendance
                wage_slip.overtime_wages = overtime_wages = ot_wages
                wage_slip.gross_wages = gross
                wage_slip.deduction_pf = pf
                wage_slip.deduction_esi = esi
                wage_slip.deduction_others = others
                wage_slip.net_wages = net_wages
            else:
                # Create a new record
                wage_slip = WageSlip(
                    company_id=current_user.company_id,
                    employee_name=emp_name,
                    father_mother_spouse_name=father_mother_spouse,
                    designation=designation,
                    uan=uan,
                    bank_account_number=bank_acc,
                    wage_month=wage_month,
                    wage_year=wage_year,
                    rate_basic=rate_basic,
                    rate_da=rate_da,
                    rate_allowances=rate_allow,
                    total_attendance=attendance,
                    overtime_wages=ot_wages,
                    gross_wages=gross,
                    deduction_pf=pf,
                    deduction_esi=esi,
                    deduction_others=others,
                    net_wages=net_wages
                )
                db.add(wage_slip)

        current_user.remaining_wage_copies = max(0, current_user.remaining_wage_copies - num_records)
        db.add(current_user)
        await db.commit()
    except Exception as e:
        logger.exception("Failed to save wage slips to DB")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error saving wage slips: {str(e)}"
        )

    return {"success": True, "totalRecords": len(df), "errors": []}

@router.get("/history")
async def get_wage_history(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
):
    if not current_user.company_id:
        return []
    
    stmt = select(WageSlip).where(WageSlip.company_id == current_user.company_id).order_index = WageSlip.created_at.desc()
    # Wait, SQLAlchemy order_by, not order_index:
    stmt = select(WageSlip).where(WageSlip.company_id == current_user.company_id).order_by(WageSlip.created_at.desc())
    res = await db.execute(stmt)
    return res.scalars().all()

@router.get("/download/{wage_id}/pdf")
async def download_wage_pdf(
    wage_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
):
    # Fetch wage slip
    stmt = select(WageSlip).where(WageSlip.id == wage_id)
    res = await db.execute(stmt)
    wage_slip = res.scalar_one_or_none()
    if not wage_slip:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Wage slip not found."
        )

    # Fetch company
    comp_stmt = select(Company).where(Company.id == wage_slip.company_id)
    comp_res = await db.execute(comp_stmt)
    company = comp_res.scalar_one_or_none()
    if not company:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Company not found."
        )

    # Generate PDF in a temp location
    temp_dir = Path("D:/peperless_be/paperlessboss-be/uploads")
    temp_dir.mkdir(parents=True, exist_ok=True)
    pdf_path = temp_dir / f"Wage_Slip_{wage_slip.employee_name.replace(' ', '_')}_{wage_slip.id}.pdf"
    
    generate_wage_slip_pdf(wage_slip, pdf_path, company)
    
    return FileResponse(
        path=str(pdf_path),
        media_type="application/pdf",
        filename=pdf_path.name
    )
