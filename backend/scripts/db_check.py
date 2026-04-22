import asyncio
from core.database import engine
from sqlalchemy import text


async def main():
    async with engine.connect() as conn:
        r = await conn.execute(text("SELECT 1"))
        print("DB OK:", r.scalar())


asyncio.run(main())
