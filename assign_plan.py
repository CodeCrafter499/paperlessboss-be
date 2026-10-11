"""
Script: Assign or Renew Subscription Plan for a User in Supabase PostgreSQL
Usage:
    python assign_plan.py
    python assign_plan.py --email nagannacti064.calactechnologies@gmail.com --plan Growth --days 365 --max-employees 100 --docx
"""
import sys
from pathlib import Path
from datetime import datetime, timedelta, timezone
import argparse
import asyncio

# Ensure backend_api and root are in sys.path
_root = Path(__file__).resolve().parent
_backend_api = _root / "backend_api"
for _p in [str(_backend_api), str(_root)]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

from db.db_connection import DatabaseManager
from db.models import User, SubscriptionPlan
from sqlalchemy import select

IST = timezone(timedelta(hours=5, minutes=30))

async def assign_user_plan(
    email: str,
    plan_name: str = "Growth",
    duration_days: int = 365,
    max_employees: int | None = None,
    has_docx: bool = True
):
    db_manager = DatabaseManager()
    now = datetime.now(IST).replace(tzinfo=None)
    end_date = now + timedelta(days=duration_days)

    async with db_manager.session_scope() as session:
        # Find user
        user_res = await session.execute(select(User).where(User.email == email.strip()))
        user = user_res.scalar_one_or_none()
        if not user:
            print(f"[ERROR] User '{email}' not found in database!")
            return False

        # Find plan definition if exists
        plan_res = await session.execute(select(SubscriptionPlan).where(SubscriptionPlan.name.ilike(plan_name.strip())))
        plan = plan_res.scalars().first()

        effective_max = max_employees
        if effective_max is None:
            effective_max = plan.max_employees if (plan and plan.max_employees) else 50

        user.subscription_plan_name = plan.name if plan else plan_name.strip()
        user.subscription_max_employees = effective_max
        user.subscription_end_date = end_date
        user.has_docx_addon = has_docx
        user.docx_addon_end_date = end_date if has_docx else None

        print(f"[SUCCESS] Updated user '{user.email}':")
        print(f"  - Plan Name: {user.subscription_plan_name}")
        print(f"  - Max Employees: {user.subscription_max_employees}")
        print(f"  - Subscription End Date: {user.subscription_end_date} (Active for {duration_days} days)")
        print(f"  - Has DOCX Add-on: {user.has_docx_addon}")
        print(f"  - DOCX Add-on End Date: {user.docx_addon_end_date}")
        return True

def main():
    parser = argparse.ArgumentParser(description="Assign subscription plan to user.")
    parser.add_argument("--email", default="nagannacti064.calactechnologies@gmail.com", help="User email")
    parser.add_argument("--plan", default="Growth", help="Plan name (Starter, Growth, Professional, Scale, Business)")
    parser.add_argument("--days", type=int, default=365, help="Subscription duration in days")
    parser.add_argument("--max-employees", type=int, default=100, help="Max employees allowed (default: 100)")
    parser.add_argument("--docx", action="store_true", default=True, help="Enable DOCX add-on")

    args = parser.parse_args()
    asyncio.run(assign_user_plan(
        email=args.email,
        plan_name=args.plan,
        duration_days=args.days,
        max_employees=args.max_employees,
        has_docx=args.docx
    ))

if __name__ == "__main__":
    main()
