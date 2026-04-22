import asyncio
from core.database import engine, async_session_factory
from models.base import Base
from models.tenant import Tenant
from models import *
from models.claims import *
from models.rcm import *
from models.denials import *
from models.payer_credentialing import *
from models.credentialing import *
from models.audit import *

async def setup():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with async_session_factory() as db:
        from sqlalchemy import select
        existing = await db.execute(select(Tenant).where(Tenant.id == '00000000-0000-0000-0000-000000000001'))
        if not existing.scalar_one_or_none():
            db.add(Tenant(id='00000000-0000-0000-0000-000000000001', name='Default Tenant', slug='default'))
            await db.commit()
            print('Created tables + default tenant')
        else:
            print('Tables exist, tenant exists')

asyncio.run(setup())
