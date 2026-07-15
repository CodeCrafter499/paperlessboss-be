from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from typing import Optional
from api.deps import get_db_session
from api.v1.auth import get_current_user
from db.models import User, PaymentTransaction, BillingSetting, SubscriptionPlan
import uuid
from datetime import datetime
from services.offer_letter.tables import IST

router = APIRouter()

class PlanResponse(BaseModel):
    id: uuid.UUID
    name: str
    min_employees: int
    max_employees: Optional[int] = None
    price: float
    is_custom: bool
    is_active: bool
    features: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

class PlanCreate(BaseModel):
    name: str
    min_employees: int
    max_employees: Optional[int] = None
    price: float
    is_custom: bool = False
    is_active: bool = True
    features: str


class PayRequest(BaseModel):
    amount: float
    type: str = "offer_letter" # "offer_letter" or "wage_slips    "

class PayResponse(BaseModel):
    amount: float
    copies_added: int
    remaining_copies: int
    remaining_wage_copies: int

class BalanceResponse(BaseModel):
    remaining_copies: int
    remaining_wage_copies: int

class BillingConfigItem(BaseModel):
    tier2_threshold: float
    tier2_copies: int
    tier1_threshold: float
    tier1_copies: int
    base_rate: float

async def get_billing_config_from_db(db: AsyncSession) -> dict[str, float]:
    stmt = select(BillingSetting)
    res = await db.execute(stmt)
    settings = {s.key: s.value for s in res.scalars().all()}
    
    # Fallback to defaults if missing in DB
    defaults = {
        "tier2_threshold": 1000.0,
        "tier2_copies": 45.0,
        "tier1_threshold": 500.0,
        "tier1_copies": 20.0,
        "base_rate": 30.0,
    }
    for k, v in defaults.items():
        if k not in settings:
            settings[k] = v
    return settings

@router.get("/balance", response_model=BalanceResponse)
async def get_balance(
    current_user: User = Depends(get_current_user),
):
    return BalanceResponse(
        remaining_copies=current_user.remaining_copies,
        remaining_wage_copies=current_user.remaining_wage_copies
    )

@router.get("/config", response_model=BillingConfigItem)
async def get_config(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
):
    cfg = await get_billing_config_from_db(db)
    return BillingConfigItem(
        tier2_threshold=cfg["tier2_threshold"],
        tier2_copies=int(cfg["tier2_copies"]),
        tier1_threshold=cfg["tier1_threshold"],
        tier1_copies=int(cfg["tier1_copies"]),
        base_rate=cfg["base_rate"]
    )

@router.post("/config", response_model=BillingConfigItem)
async def update_config(
    cfg_data: BillingConfigItem,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
):
    if current_user.email != "admin@peperlessboss.com":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. Admin access only."
        )

    for key, val in cfg_data.model_dump().items():
        stmt = select(BillingSetting).where(BillingSetting.key == key)
        res = await db.execute(stmt)
        setting = res.scalar_one_or_none()
        if setting:
            setting.value = float(val)
        else:
            db.add(BillingSetting(key=key, value=float(val)))
            
    await db.commit()
    return cfg_data

@router.post("/pay", response_model=PayResponse)
async def pay(
    req: PayRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
):
    if req.amount <= 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Amount must be greater than zero."
        )

    cfg = await get_billing_config_from_db(db)
    
    amount = float(req.amount)
    tier2_threshold = float(cfg["tier2_threshold"])
    tier2_copies = float(cfg["tier2_copies"])
    tier1_threshold = float(cfg["tier1_threshold"])
    tier1_copies = float(cfg["tier1_copies"])
    base_rate = float(cfg["base_rate"])

    if amount >= tier2_threshold:
        rate = (tier2_threshold / tier2_copies) if tier2_copies > 0 else 9999.0
        copies_added = int(amount / rate)
    elif amount >= tier1_threshold:
        rate = (tier1_threshold / tier1_copies) if tier1_copies > 0 else 9999.0
        copies_added = int(amount / rate)
    else:
        copies_added = int(amount / base_rate) if base_rate > 0 else 0

    if copies_added <= 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Paid amount is insufficient to purchase any offer letter copies."
        )

    # Update user balance
    if req.type == "wage_slip":
        current_user.remaining_wage_copies += copies_added
    else:
        current_user.remaining_copies += copies_added
        
    db.add(current_user)

    # Log payment transaction
    transaction = PaymentTransaction(
        id=uuid.uuid4(),
        user_id=current_user.id,
        amount=req.amount,
        copies_added=copies_added,
        created_at=datetime.now(IST).replace(tzinfo=None)
    )
    db.add(transaction)
    
    await db.commit()

    return PayResponse(
        amount=req.amount,
        copies_added=copies_added,
        remaining_copies=current_user.remaining_copies,
        remaining_wage_copies=current_user.remaining_wage_copies
    )


@router.get("/plans", response_model=list[PlanResponse])
async def get_plans(
    active_only: bool = False,
    db: AsyncSession = Depends(get_db_session)
):
    stmt = select(SubscriptionPlan)
    if active_only:
        stmt = stmt.where(SubscriptionPlan.is_active == True)
    stmt = stmt.order_by(SubscriptionPlan.min_employees.asc())
    res = await db.execute(stmt)
    return res.scalars().all()


@router.post("/plans", response_model=PlanResponse)
async def create_plan(
    plan_data: PlanCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
):
    if current_user.email != "admin@peperlessboss.com":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. Admin access only."
        )
    
    plan = SubscriptionPlan(
        id=uuid.uuid4(),
        name=plan_data.name,
        min_employees=plan_data.min_employees,
        max_employees=plan_data.max_employees,
        price=plan_data.price,
        is_custom=plan_data.is_custom,
        is_active=plan_data.is_active,
        features=plan_data.features,
    )
    db.add(plan)
    await db.commit()
    await db.refresh(plan)
    return plan


@router.put("/plans/{plan_id}", response_model=PlanResponse)
async def update_plan(
    plan_id: uuid.UUID,
    plan_data: PlanCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
):
    if current_user.email != "admin@peperlessboss.com":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. Admin access only."
        )
    
    stmt = select(SubscriptionPlan).where(SubscriptionPlan.id == plan_id)
    res = await db.execute(stmt)
    plan = res.scalar_one_or_none()
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found")
    
    plan.name = plan_data.name
    plan.min_employees = plan_data.min_employees
    plan.max_employees = plan_data.max_employees
    plan.price = plan_data.price
    plan.is_custom = plan_data.is_custom
    plan.is_active = plan_data.is_active
    plan.features = plan_data.features
    plan.updated_at = datetime.now(IST).replace(tzinfo=None)
    
    await db.commit()
    await db.refresh(plan)
    return plan


@router.delete("/plans/{plan_id}")
async def delete_plan(
    plan_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
):
    if current_user.email != "admin@peperlessboss.com":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. Admin access only."
        )
    
    stmt = select(SubscriptionPlan).where(SubscriptionPlan.id == plan_id)
    res = await db.execute(stmt)
    plan = res.scalar_one_or_none()
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found")
    
    await db.delete(plan)
    await db.commit()
    return {"message": "Plan deleted successfully"}

