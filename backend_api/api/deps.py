from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession

from db.db_connection import DatabaseManager


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    db_manager = DatabaseManager()
    async with db_manager.session_scope() as session:
        yield session
