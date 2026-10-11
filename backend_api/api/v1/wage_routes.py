from fastapi import APIRouter, UploadFile, File, HTTPException, status, Depends
from fastapi.responses import FileResponse
from pathlib import Path
from typing import Optional
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
    check_limits: bool = False,
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
        
        from datetime import datetime
        from services.offer_letter.tables import IST
        now = datetime.now(IST).replace(tzinfo=None)

        is_sub_active = bool(current_user.subscription_end_date and current_user.subscription_end_date >= now)
        if not is_sub_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Your subscription plan is inactive or expired. Please subscribe to a plan in Billing & Subscription to generate wage slips."
            )


        from db.models import Employee
        # Extract months and uploaded employee names from Excel
        months_found = set()
        uploaded_emp_names = set()
        for _, r_data in df.iterrows():
            r_dict = {str(k).strip(): v for k, v in r_data.to_dict().items()}
            m_val = excel_value_to_str(get_aliased_value(r_dict, "6a. Wage month", "")).strip()
            y_val = excel_value_to_str(get_aliased_value(r_dict, "6b. Wage Year", "")).strip()
            if m_val:
                months_found.add(f"{m_val} {y_val}".strip() if y_val else m_val)
            emp_n = excel_value_to_str(get_aliased_value(r_dict, "1. Name of employee", "")).strip()
            if emp_n:
                uploaded_emp_names.add(emp_n)

        months_str = ", ".join(sorted(months_found)) if months_found else "this month"
        plan_name = current_user.subscription_plan_name or "Growth"
        plan_limit = current_user.subscription_max_employees or 0

        # Query existing registered employees for this company
        emp_query = select(Employee.employee_name).where(Employee.company_id == current_user.company_id)
        emp_res = await db.execute(emp_query)
        existing_emp_names = {name.strip().lower() for name in emp_res.scalars().all() if name}

        # Identify new employees not in the existing list
        new_employees = [name for name in uploaded_emp_names if name.lower() not in existing_emp_names]
        total_unique_employees = len(existing_emp_names.union({name.lower() for name in uploaded_emp_names}))

        new_emp_sample = ", ".join(new_employees[:5])
        if len(new_employees) > 5:
            new_emp_sample += f", and {len(new_employees) - 5} more"
        new_emp_clause = f" [{new_emp_sample}]" if new_emp_sample else ""

        # If there are new employees not in the existing list and the plan limit is reached/exceeded:
        if plan_limit > 0 and len(new_employees) > 0 and (total_unique_employees > plan_limit or len(existing_emp_names) >= plan_limit):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"Limit exceeded: {len(new_employees)} new employee(s) found for month ({months_str}){new_emp_clause} "
                    f"that are not in your {plan_name} plan's {plan_limit} employee list. "
                    f"Please enable flexible overage rate in the Billing & Credits page to cover additional employees."
                )
            )

        if plan_limit > 0 and num_records > plan_limit:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"Limit exceeded: The Excel file contains {num_records} records for month ({months_str}), "
                    f"which exceeds your '{plan_name}' plan limit of {plan_limit} employees. "
                    f"Please enable flexible overage rate in the Billing & Credits page to cover additional employees."
                )
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
                # Update existing record ONLY if there are changes
                wage_slip = existing_wages[key]
                has_changes = (
                    wage_slip.father_mother_spouse_name != father_mother_spouse or
                    wage_slip.designation != designation or
                    wage_slip.uan != uan or
                    wage_slip.bank_account_number != bank_acc or
                    wage_slip.rate_basic != rate_basic or
                    wage_slip.rate_da != rate_da or
                    wage_slip.rate_allowances != rate_allow or
                    wage_slip.total_attendance != attendance or
                    wage_slip.overtime_wages != ot_wages or
                    wage_slip.gross_wages != gross or
                    wage_slip.deduction_pf != pf or
                    wage_slip.deduction_esi != esi or
                    wage_slip.deduction_others != others or
                    wage_slip.net_wages != net_wages
                )
                if has_changes:
                    wage_slip.father_mother_spouse_name = father_mother_spouse
                    wage_slip.designation = designation
                    wage_slip.uan = uan
                    wage_slip.bank_account_number = bank_acc
                    wage_slip.rate_basic = rate_basic
                    wage_slip.rate_da = rate_da
                    wage_slip.rate_allowances = rate_allow
                    wage_slip.total_attendance = attendance
                    wage_slip.overtime_wages = ot_wages
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

        await db.commit()
    except HTTPException:
        raise
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


from pydantic import BaseModel as _BaseModel

class DownloadWageZipRequest(_BaseModel):
    wage_ids: Optional[list[uuid.UUID]] = None
    wage_month: Optional[str] = None
    wage_year: Optional[int] = None


async def _download_wages_zip_impl(
    wage_ids: Optional[list[uuid.UUID]],
    wage_month: Optional[str],
    wage_year: Optional[int],
    current_user: User,
    db: AsyncSession,
):
    import io
    import zipfile
    from fastapi.responses import Response
    from services.offer_letter.tables import IST
    from datetime import datetime
    import tempfile

    if not current_user.company_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Your account is not associated with a company profile."
        )

    # Fetch company
    comp_stmt = select(Company).where(Company.id == current_user.company_id)
    comp_res = await db.execute(comp_stmt)
    company = comp_res.scalar_one_or_none()
    if not company:
        raise HTTPException(status_code=404, detail="Company profile not found.")

    # Query wage slips
    stmt = select(WageSlip).where(WageSlip.company_id == current_user.company_id)
    if wage_ids and len(wage_ids) > 0:
        stmt = stmt.where(WageSlip.id.in_(wage_ids))
    if wage_month and wage_month.strip():
        stmt = stmt.where(WageSlip.wage_month.ilike(wage_month.strip()))
    if wage_year:
        stmt = stmt.where(WageSlip.wage_year == wage_year)
    stmt = stmt.order_by(WageSlip.employee_name.asc())

    res = await db.execute(stmt)
    slips = res.scalars().all()
    if not slips:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No wage slips found matching the selected period."
        )

    zip_buffer = io.BytesIO()
    seen_names = set()
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            for slip in slips:
                safe_name = slip.employee_name.replace(" ", "_")[:50]
                period = f"{slip.wage_month or ''}_{slip.wage_year or ''}".strip("_")
                base_arc = f"Wage_Slip_{safe_name}_{period}"
                arc = f"{base_arc}.pdf"
                if arc in seen_names:
                    emp_tag = f"_{slip.uan}" if slip.uan else f"_{slip.id}"
                    arc = f"{base_arc}{emp_tag}.pdf"
                counter = 1
                while arc in seen_names:
                    arc = f"{base_arc}_{counter}.pdf"
                    counter += 1
                seen_names.add(arc)
                pdf_file = tmp_path / arc
                try:
                    generate_wage_slip_pdf(slip, pdf_file, company)
                    if pdf_file.is_file():
                        zf.write(pdf_file, arcname=arc)
                except Exception as exc:
                    logger.warning("Failed to generate wage slip PDF for %s: %s", slip.employee_name, exc)

    zip_buffer.seek(0)
    month_label = f"_{wage_month}" if wage_month else ""
    year_label = f"_{wage_year}" if wage_year else ""
    zip_filename = f"Wage_Slips{month_label}{year_label}.zip"

    return Response(
        content=zip_buffer.getvalue(),
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="{zip_filename}"',
            "Access-Control-Expose-Headers": "Content-Disposition"
        }
    )


@router.get("/download-zip")
async def download_wages_zip_get(
    wage_month: Optional[str] = None,
    wage_year: Optional[int] = None,
    wage_ids: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    parsed_ids = None
    if wage_ids and wage_ids.strip():
        try:
            parsed_ids = [uuid.UUID(x.strip()) for x in wage_ids.split(",") if x.strip()]
        except Exception:
            pass
    return await _download_wages_zip_impl(parsed_ids, wage_month, wage_year, current_user, db)


@router.post("/download-zip")
async def download_wages_zip_post(
    payload: Optional[DownloadWageZipRequest] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    w_ids = payload.wage_ids if payload else None
    w_month = payload.wage_month if payload else None
    w_year = payload.wage_year if payload else None
    return await _download_wages_zip_impl(w_ids, w_month, w_year, current_user, db)

