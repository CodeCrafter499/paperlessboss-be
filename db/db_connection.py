import os
import ssl
import urllib.parse
from contextlib import asynccontextmanager
from typing import AsyncGenerator
from dotenv import load_dotenv
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
dotenv_path = os.path.join(BASE_DIR, '.env')
load_dotenv(dotenv_path)

class DatabaseManager:
    
    _instance = None
    
    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super(DatabaseManager, cls).__new__(cls, *args, **kwargs)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        
        self.db_host = os.getenv("DB_HOST")
        self.db_port = os.getenv("DB_PORT", "5432")
        self.db_name = os.getenv("DB_NAME")
        self.db_user = os.getenv("DB_USER")
        self.db_pass = os.getenv("DB_PASS")
        self.db_echo = os.getenv("DB_ECHO", "False").lower() in ("true", "1", "t")

        if not all([self.db_host, self.db_name, self.db_user, self.db_pass]):
            missing = [k for k, v in {
                "DB_HOST": self.db_host,
                "DB_NAME": self.db_name,
                "DB_USER": self.db_user,
                "DB_PASS": self.db_pass
            }.items() if not v]
            raise ValueError(f"Database configuration error: Missing environment variable(s): {', '.join(missing)}")

        safe_user = urllib.parse.quote_plus(self.db_user)
        safe_pass = urllib.parse.quote_plus(self.db_pass)
        
        self.database_url = (
            f"postgresql+asyncpg://{safe_user}:{safe_pass}@"
            f"{self.db_host.strip()}:{self.db_port.strip()}/{self.db_name.strip()}"
        )

        ssl_context = ssl.create_default_context()
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE

        self.engine = create_async_engine(
            self.database_url,
            pool_size=10,
            max_overflow=20,
            pool_recycle=1800,
            pool_pre_ping=True,
            echo=self.db_echo,
            connect_args={"ssl": ssl_context}
        )

        self._session_factory = async_sessionmaker(
            bind=self.engine,
            expire_on_commit=False,
            class_=AsyncSession
        )
        
        self._initialized = True

    def get_session(self) -> AsyncSession:
        return self._session_factory()

    @asynccontextmanager
    async def session_scope(self) -> AsyncGenerator[AsyncSession, None]:
        async with self._session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception as e:
                await session.rollback()
                raise e

    async def ping(self) -> bool:
        try:
            async with self.session_scope() as session:
                await session.execute(text("SELECT 1"))
            return True
        except Exception as e:
            print(f"Database async health check failed: {e}")
            return False

    async def close_all(self):
        if hasattr(self, 'engine'):
            await self.engine.dispose()
            self._initialized = False
            DatabaseManager._instance = None
