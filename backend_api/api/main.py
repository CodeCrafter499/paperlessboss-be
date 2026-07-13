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


@asynccontextmanager
async def lifespan(app: FastAPI):
    print(">>> Starting up PaperlessBoss Backend...")
    db_manager = DatabaseManager()
    
    is_healthy = await db_manager.ping()
    if not is_healthy:
        print("[WARNING] Database ping failed. Verify that connection credentials are correct.")
    
    print(">>> Syncing database schemas (Creating tables if missing)...")
    try:
        async with db_manager.engine.begin() as conn:
            from sqlalchemy import text
            await conn.execute(text("ALTER TABLE otp_verifications ADD COLUMN IF NOT EXISTS attempts INTEGER DEFAULT 0;"))
            await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_companies_gstin ON companies (gstin);"))
            await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_companies_cin ON companies (cin);"))
            await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_companies_pan ON companies (pan);"))
            await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_refresh_tokens_user_id ON refresh_tokens (user_id);"))
            await conn.execute(text("ALTER TABLE generated_letter_logs ADD COLUMN IF NOT EXISTS employee_id INTEGER;"))
            await conn.execute(text("ALTER TABLE generated_letter_logs ADD COLUMN IF NOT EXISTS company_id UUID;"))
            await conn.execute(text("ALTER TABLE generated_letter_logs ADD COLUMN IF NOT EXISTS downloaded BOOLEAN DEFAULT FALSE;"))
            await conn.execute(text("ALTER TABLE generated_letter_logs ADD COLUMN IF NOT EXISTS downloaded_at TIMESTAMP;"))
            await conn.execute(text("ALTER TABLE generated_letter_logs ADD COLUMN IF NOT EXISTS downloaded_by UUID;"))
            await conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS remaining_copies INTEGER DEFAULT 0;"))
            await conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS remaining_wage_copies INTEGER DEFAULT 0;"))
            await conn.execute(text("ALTER TABLE authorised_signatories ADD COLUMN IF NOT EXISTS signature_image TEXT;"))
            await conn.execute(text("ALTER TABLE authorised_signatories ADD COLUMN IF NOT EXISTS stamp_image TEXT;"))
            await conn.execute(text("ALTER TABLE authorised_signatories ADD COLUMN IF NOT EXISTS include_signature_stamp BOOLEAN DEFAULT FALSE;"))
            await conn.execute(text("""
                CREATE TABLE IF NOT EXISTS payment_transactions (
                    id UUID PRIMARY KEY,
                    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    amount NUMERIC(10, 2) NOT NULL,
                    copies_added INTEGER NOT NULL,
                    created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL
                );
            """))
            await conn.execute(text("""
                CREATE TABLE IF NOT EXISTS billing_settings (
                    key VARCHAR(50) PRIMARY KEY,
                    value NUMERIC(10, 2) NOT NULL
                );
            """))
            res = await conn.execute(text("SELECT COUNT(*) FROM billing_settings;"))
            count = res.scalar()
            if count == 0:
                defaults = [
                    ("tier2_threshold", 1000.0),
                    ("tier2_copies", 45.0),
                    ("tier1_threshold", 500.0),
                    ("tier1_copies", 20.0),
                    ("base_rate", 30.0),
                ]
                for key, val in defaults:
                    await conn.execute(text("INSERT INTO billing_settings (key, value) VALUES (:key, :value);"), {"key": key, "value": val})
            await conn.run_sync(Base.metadata.create_all)
            await conn.execute(text("ALTER TABLE storage_mapping ALTER COLUMN employee_id DROP NOT NULL;"))
        print(">>> Database initialized and tables synced successfully!")
    except Exception as e:
        print(f"[FATAL] Failed to sync database tables on startup: {e}")
        
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
