from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from core.config import settings
from db.db_connection import DatabaseManager
from db.models import Base
from api.v1.auth import router as auth_router

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
            await conn.run_sync(Base.metadata.create_all)
        print(">>> Database initialized and tables synced successfully!")
    except Exception as e:
        print(f"[FATAL] Failed to sync database tables on startup: {e}")
        
    yield
    
    print(">>> Disposing of database connection pool...")
    await db_manager.close_all()
    print(">>> Shutdown complete!")

app = FastAPI(
    title=settings.PROJECT_NAME,
    description="A secure asynchronous auth backend featuring OTP email verification and JWT token authorization.",
    version="1.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router, prefix=f"{settings.API_V1_STR}/auth", tags=["Authentication"])

@app.get("/")
async def root():
    return {
        "project": settings.PROJECT_NAME,
        "docs": "/docs",
        "status": "online"
    }
