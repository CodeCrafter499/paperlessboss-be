import sys
import asyncio
import logging
from pathlib import Path

# Add project root and backend_api directory to sys.path to resolve imports cleanly in development
backend_api_dir = Path(__file__).resolve().parent.parent
project_root = backend_api_dir.parent

for p in (str(project_root), str(backend_api_dir)):
    if p not in sys.path:
        sys.path.insert(0, p)

logger = logging.getLogger(__name__)

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from core.config import settings
from db.db_connection import DatabaseManager
from db.models import Base
from api.v1.auth import router as auth_router

from api.v1.excel_routes import router as excel_router
from api.v1.offer_letter_routes import router as offer_letter_router
from services.offer_letter.letterhead import is_letterhead_available
from api.v1.profile import router as profile_router
from api.v1.billing import router as billing_router
from api.v1.wage_routes import router as wage_router


async def run_db_sync(db_manager):
    print(">>> Syncing database schemas in background...")
    try:
        from sqlalchemy import text
        # 1. Base table creation
        try:
            async with db_manager.engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
        except Exception as err:
            logger.debug("Table creation note: %s", err)

        # 2. Resilient migrations executed in single batch
        async with db_manager.engine.begin() as conn:
            await conn.execute(text("""
                ALTER TABLE otp_verifications ADD COLUMN IF NOT EXISTS attempts INTEGER DEFAULT 0;
                CREATE INDEX IF NOT EXISTS ix_companies_gstin ON companies (gstin);
                CREATE INDEX IF NOT EXISTS ix_companies_cin ON companies (cin);
                CREATE INDEX IF NOT EXISTS ix_companies_pan ON companies (pan);
                CREATE INDEX IF NOT EXISTS ix_refresh_tokens_user_id ON refresh_tokens (user_id);
                ALTER TABLE generated_letter_logs ADD COLUMN IF NOT EXISTS employee_id INTEGER;
                ALTER TABLE generated_letter_logs ADD COLUMN IF NOT EXISTS company_id UUID;
                ALTER TABLE generated_letter_logs ADD COLUMN IF NOT EXISTS downloaded BOOLEAN DEFAULT FALSE;
                ALTER TABLE generated_letter_logs ADD COLUMN IF NOT EXISTS downloaded_at TIMESTAMP;
                ALTER TABLE generated_letter_logs ADD COLUMN IF NOT EXISTS downloaded_by UUID;
                ALTER TABLE generated_letter_logs ADD COLUMN IF NOT EXISTS uan_number VARCHAR(255);
                ALTER TABLE users ADD COLUMN IF NOT EXISTS remaining_copies INTEGER DEFAULT 0;
                ALTER TABLE users ADD COLUMN IF NOT EXISTS remaining_wage_copies INTEGER DEFAULT 0;
                ALTER TABLE users ADD COLUMN IF NOT EXISTS agreed_to_terms BOOLEAN DEFAULT TRUE;
                ALTER TABLE users ADD COLUMN IF NOT EXISTS mobile_no VARCHAR(20);
                ALTER TABLE authorised_signatories ADD COLUMN IF NOT EXISTS signature_image TEXT;
                ALTER TABLE authorised_signatories ADD COLUMN IF NOT EXISTS stamp_image TEXT;
                ALTER TABLE authorised_signatories ADD COLUMN IF NOT EXISTS include_signature_stamp BOOLEAN DEFAULT FALSE;
                CREATE TABLE IF NOT EXISTS payment_transactions (
                    id UUID PRIMARY KEY,
                    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    amount NUMERIC(10, 2) NOT NULL,
                    copies_added INTEGER NOT NULL,
                    created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL
                );
                ALTER TABLE payment_transactions ADD COLUMN IF NOT EXISTS merchant_transaction_id VARCHAR(100) UNIQUE;
                ALTER TABLE payment_transactions ADD COLUMN IF NOT EXISTS phonepe_transaction_id VARCHAR(100);
                ALTER TABLE payment_transactions ADD COLUMN IF NOT EXISTS status VARCHAR(20) DEFAULT 'PENDING';
                ALTER TABLE payment_transactions ADD COLUMN IF NOT EXISTS type VARCHAR(50) DEFAULT 'offer_letter';
                ALTER TABLE payment_transactions ADD COLUMN IF NOT EXISTS payment_instrument TEXT;
                CREATE TABLE IF NOT EXISTS billing_settings (
                    key VARCHAR(50) PRIMARY KEY,
                    value NUMERIC(10, 2) NOT NULL
                );
                ALTER TABLE storage_mapping ALTER COLUMN employee_id DROP NOT NULL;
            """))

        # 3. Seed billing settings and plans if needed
        try:
            async with db_manager.engine.begin() as conn:
                res = await conn.execute(text("SELECT COUNT(*) FROM billing_settings;"))
                count = res.scalar()
                if count == 0:
                    defaults = [
                        ("tier2_threshold", 1000.0),
                        ("tier2_copies", 45.0),
                        ("tier1_threshold", 500.0),
                        ("tier1_copies", 20.0),
                        ("base_rate", 30.0),
                        ("overage_rate", 15.0),
                        ("docx_addon_price", 299.0),
                    ]
                    for key, val in defaults:
                        await conn.execute(text("INSERT INTO billing_settings (key, value) VALUES (:key, :value);"), {"key": key, "value": val})
                else:
                    new_keys = [
                        ("overage_rate", 15.0),
                        ("docx_addon_price", 299.0),
                    ]
                    for key, val in new_keys:
                        await conn.execute(
                            text("INSERT INTO billing_settings (key, value) VALUES (:key, :value) ON CONFLICT (key) DO NOTHING;"),
                            {"key": key, "value": val}
                        )

                import uuid
                plan_count_res = await conn.execute(text("SELECT COUNT(*) FROM subscription_plans;"))
                plan_count = plan_count_res.scalar()
                if plan_count < 6:
                    await conn.execute(text("DELETE FROM subscription_plans;"))
                    features_standard = "Bulk upload,Appointment Letters (PDF only),Wage Slips (PDF only),Email Support"
                    initial_plans = [
                        (str(uuid.uuid4()), "Starter",      1,    25,   499.0,  False, True, features_standard),
                        (str(uuid.uuid4()), "Growth",       1,    50,   749.0,  False, True, features_standard),
                        (str(uuid.uuid4()), "Professional", 1,   100,   999.0,  False, True, features_standard),
                        (str(uuid.uuid4()), "Scale",        1,   500,  1499.0,  False, True, features_standard),
                        (str(uuid.uuid4()), "Business",     1,  1000,  2500.0,  False, True, features_standard),
                        (str(uuid.uuid4()), "Enterprise",   1001, None, 3000.0, True,  True, "Contact Sales"),
                    ]
                    for p_id, name, min_emp, max_emp, price, is_cust, is_act, feats in initial_plans:
                        await conn.execute(
                            text("""
                                INSERT INTO subscription_plans (id, name, min_employees, max_employees, price, is_custom, is_active, features, created_at, updated_at)
                                VALUES (:id, :name, :min_emp, :max_emp, :price, :is_cust, :is_act, :feats, NOW(), NOW());
                            """),
                            {"id": p_id, "name": name, "min_emp": min_emp, "max_emp": max_emp,
                             "price": price, "is_cust": is_cust, "is_act": is_act, "feats": feats}
                        )
        except Exception as seed_err:
            logger.debug("Seed note: %s", seed_err)

        print(">>> Database initialized and tables synced successfully!")
    except Exception as e:
        logger.debug("Schema sync completed: %s", e)


@asynccontextmanager
async def lifespan(app: FastAPI):
    print(">>> Starting up PaperlessBoss Backend...")
    db_manager = DatabaseManager()
    
    # Run schema verification in background so server starts instantly (< 50ms)
    asyncio.create_task(run_db_sync(db_manager))
        
    yield
    
    print(">>> Disposing of database connection pool...")
    await db_manager.close_all()
    print(">>> Shutdown complete!")

# Check if documentation endpoints should be enabled
show_docs = settings.ENVIRONMENT.lower() == "development"

app = FastAPI(
    title=settings.PROJECT_NAME,
    description="A secure asynchronous auth backend featuring OTP email verification and JWT token authorization.",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs" if show_docs else None,
    redoc_url="/redoc" if show_docs else None,
    openapi_url="/openapi.json" if show_docs else None
)

# Allowed production and development origins
origins = [
    "https://paperlessboss.com",
    "https://www.paperlessboss.com",
    "http://localhost:3000",
    "http://localhost:5173",
    "http://127.0.0.1:8000",
    "http://127.0.0.1:5173",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

app.include_router(auth_router, prefix=f"{settings.API_V1_STR}/auth", tags=["Authentication"])
app.include_router(excel_router)
app.include_router(profile_router, prefix=f"{settings.API_V1_STR}/profile", tags=["Profile"])
app.include_router(offer_letter_router, prefix=settings.API_V1_STR)
app.include_router(billing_router, prefix=f"{settings.API_V1_STR}/billing", tags=["Billing"])
app.include_router(wage_router, prefix=f"{settings.API_V1_STR}/wages", tags=["Wages"])


@app.get("/")
async def root():
    return {
        "project": settings.PROJECT_NAME,
        "docs": "/docs" if show_docs else None,
        "status": "online"
    }
