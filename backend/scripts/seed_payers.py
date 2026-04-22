import asyncio
from core.database import async_session_factory
from models.rcm import PayerProfile
from sqlalchemy import select

async def seed():
    async with async_session_factory() as db:
        existing = await db.execute(select(PayerProfile).limit(1))
        if existing.scalar_one_or_none():
            print('Payers already exist, skipping')
            return

        tenant_id = '00000000-0000-0000-0000-000000000001'
        payers = [
            PayerProfile(
                tenant_id=tenant_id, name='Medicare Part B',
                display_name='Centers for Medicare & Medicaid Services',
                payer_id='00112', state_code=None, clearinghouse='Availity',
                connection_method='clearinghouse', is_active=True, is_draft=False,
                filing_limit_days=365, supports_835_era=True, supports_270_271=True,
                supports_telehealth=True, created_by='system-seed',
            ),
            PayerProfile(
                tenant_id=tenant_id, name='HMSA',
                display_name='Hawaii Medical Service Association',
                payer_id='34189', state_code='HI', clearinghouse='Availity',
                connection_method='clearinghouse', is_active=True, is_draft=False,
                filing_limit_days=365, supports_835_era=True, supports_270_271=True,
                supports_telehealth=True, created_by='system-seed',
            ),
            PayerProfile(
                tenant_id=tenant_id, name='Quest Integration (Medicaid HI)',
                display_name='Hawaii Quest Health Plan - Medicaid Managed Care',
                payer_id='14163', state_code='HI', clearinghouse='Availity',
                connection_method='clearinghouse', is_active=True, is_draft=False,
                filing_limit_days=180, supports_835_era=True, supports_270_271=True,
                supports_telehealth=True, created_by='system-seed',
            ),
            PayerProfile(
                tenant_id=tenant_id, name='UnitedHealthcare',
                display_name='UnitedHealthcare Insurance Company',
                payer_id='87726', state_code=None, clearinghouse='Change Healthcare',
                connection_method='clearinghouse', is_active=True, is_draft=False,
                filing_limit_days=365, supports_835_era=True, supports_270_271=True,
                supports_telehealth=True, created_by='system-seed',
            ),
        ]
        for p in payers:
            db.add(p)
        await db.commit()
        print(f'Seeded {len(payers)} payer profiles')

asyncio.run(seed())
