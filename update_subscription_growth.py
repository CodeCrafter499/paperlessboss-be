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
            import calendar
            from datetime import datetime
            d = datetime.now()
            month = d.month + 1
            year = d.year
            if month > 12:
                month = 1
                year += 1
            max_day = calendar.monthrange(year, month)[1]
            day = min(d.day, max_day)
            next_month_date = d.replace(year=year, month=month, day=day)

            print(f"Updating subscription to Growth Plan for nagannacti064.calactechnologies@gmail.com (expires {next_month_date})...")
            result = await conn.execute("""
                UPDATE users 
                SET subscription_plan_name = 'Growth', 
                    subscription_max_employees = 50, 
                    subscription_end_date = $1
                WHERE email = 'nagannacti064.calactechnologies@gmail.com';
            """, next_month_date)
            print(f"Result: {result}")
    finally:
        await conn.close()

asyncio.run(main())
