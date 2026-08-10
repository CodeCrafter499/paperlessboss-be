"""
Migration script: Add subscription columns to users table in Supabase PostgreSQL
"""
import asyncio
import asyncpg

DB_HOST = "aws-1-ap-northeast-2.pooler.supabase.com"
DB_PORT = 5432
DB_NAME = "postgres"
DB_USER = "postgres.skzceavurcikyajjtpar"
DB_PASS = "PaperLessBoss2026"

async def main():
    conn = await asyncpg.connect(
        host=DB_HOST, port=DB_PORT, database=DB_NAME,
        user=DB_USER, password=DB_PASS
    )
    try:
        async with conn.transaction():
            print("Adding subscription columns to users table...")
            await conn.execute("""
                ALTER TABLE users 
                ADD COLUMN IF NOT EXISTS subscription_plan_name VARCHAR(100),
                ADD COLUMN IF NOT EXISTS subscription_max_employees INT DEFAULT 0,
                ADD COLUMN IF NOT EXISTS subscription_end_date TIMESTAMP,
                ADD COLUMN IF NOT EXISTS has_docx_addon BOOLEAN DEFAULT FALSE,
                ADD COLUMN IF NOT EXISTS docx_addon_end_date TIMESTAMP;
            """)
            print("Columns added successfully!")
    finally:
        await conn.close()

asyncio.run(main())
