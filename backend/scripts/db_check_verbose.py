"""Verbose health check that prints the actual exception."""
import asyncio
from sqlalchemy import text
from core.database import engine


async def main():
    print("Engine URL:", engine.url)
    print("Pool size:", engine.pool.size())
    try:
        async with engine.connect() as conn:
            r = await conn.execute(text("SELECT 1"))
            print("OK:", r.scalar())
    except Exception as e:
        print("FAIL:", type(e).__name__, str(e))
        import traceback
        traceback.print_exc()


asyncio.run(main())
