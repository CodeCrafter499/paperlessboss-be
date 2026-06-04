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

@asynccontextmanager
async def lifespan(app: FastAPI):
    print(">>> Starting up PaperlessBoss Backend...")
    if not is_letterhead_available():
        print("[WARNING] Letterhead PDF unavailable — offer letters will use text header fallback.")
    db_manager = DatabaseManager()
    
    is_healthy = await db_manager.ping()
    if not is_healthy:
        print("[WARNING] Database ping failed. Verify that connection credentials are correct.")
    
    print(">>> Syncing database schemas (Creating tables if missing)...")
    try:
        async with db_manager.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
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
app.include_router(offer_letter_router, prefix=settings.API_V1_STR)

@app.get("/")
async def root():
    return {
        "project": settings.PROJECT_NAME,
        "docs": "/docs" if show_docs else None,
        "status": "online"
    }
