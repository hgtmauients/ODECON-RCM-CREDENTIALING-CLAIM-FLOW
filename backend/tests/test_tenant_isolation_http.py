"""
Adversarial tenant isolation integration test.

Proves over HTTP that tenant B cannot read tenant A patient/claim records.
"""

import os
from datetime import date
from uuid import UUID, uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import and_, select

os.environ["ENV"] = "development"
os.environ["JWT_SECRET"] = os.getenv("JWT_SECRET", "dev-secret-for-local-only-min32ch")
os.environ["JWT_AUDIENCE"] = os.getenv("JWT_AUDIENCE", "claimflow")
os.environ["DATABASE_URL"] = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://claimflow:claimflow@localhost:5432/claimflow",
)

from app.main import app
from core.database import async_session_factory, engine
from core.password import hash_password
from models.base import Base
from models.tenant import Tenant
from models.user import User

TENANT_A_ID = "00000000-0000-0000-0000-0000000000a1"
TENANT_B_ID = "00000000-0000-0000-0000-0000000000b2"
TENANT_A_EMAIL = "isolation-tenant-a@claimflow.io"
TENANT_B_EMAIL = "isolation-tenant-b@claimflow.io"
TEST_PASSWORD = "admin"


@pytest.fixture(scope="module")
def anyio_backend():
    return "asyncio"


async def _ensure_tenant_and_user(tenant_id: str, email: str, slug: str, name: str) -> None:
    tenant_uuid = UUID(tenant_id)
    async with async_session_factory() as db:
        tenant = (
            await db.execute(select(Tenant).where(Tenant.id == tenant_uuid))
        ).scalar_one_or_none()
        if not tenant:
            tenant = Tenant(
                id=tenant_uuid,
                name=name,
                slug=slug,
                is_active=True,
            )
            db.add(tenant)

        user = (
            await db.execute(select(User).where(and_(User.tenant_id == tenant_uuid, User.email == email)))
        ).scalar_one_or_none()
        if not user:
            user = User(
                tenant_id=tenant_uuid,
                email=email,
                full_name=name + " Admin",
                password_hash=hash_password(TEST_PASSWORD),
                roles=["super_admin", "admin", "billing", "credentialing"],
                is_active=True,
                created_by="tenant-isolation-test",
            )
            db.add(user)
        else:
            user.password_hash = hash_password(TEST_PASSWORD)
            user.roles = ["super_admin", "admin", "billing", "credentialing"]
            user.is_active = True
        await db.commit()


@pytest.fixture(scope="module")
async def setup_db():
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    except Exception as exc:
        pytest.skip(f"Database unavailable for tenant isolation HTTP test: {exc}")
    await _ensure_tenant_and_user(
        tenant_id=TENANT_A_ID,
        email=TENANT_A_EMAIL,
        slug="tenant-isolation-a",
        name="Tenant Isolation A",
    )
    await _ensure_tenant_and_user(
        tenant_id=TENANT_B_ID,
        email=TENANT_B_EMAIL,
        slug="tenant-isolation-b",
        name="Tenant Isolation B",
    )
    yield


async def _auth_headers(ac: AsyncClient, email: str, tenant_id: str) -> dict:
    resp = await ac.post("/api/auth/login", json={"email": email, "password": TEST_PASSWORD})
    assert resp.status_code == 200, f"login failed for {email}: {resp.text}"
    token = resp.json()["access_token"]
    return {
        "Authorization": f"Bearer {token}",
        "X-Tenant-ID": tenant_id,
    }


@pytest.mark.asyncio(loop_scope="module")
async def test_cross_tenant_patient_and_claim_reads_are_blocked(setup_db):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        headers_a = await _auth_headers(ac, TENANT_A_EMAIL, TENANT_A_ID)
        headers_b = await _auth_headers(ac, TENANT_B_EMAIL, TENANT_B_ID)

        payer_resp = await ac.post(
            "/api/rcm/payers",
            headers=headers_a,
            json={
                "name": "Isolation Test Payer A",
                "payer_id": f"TNAISO{uuid4().hex[:8]}",
                "format_837_type": "837P",
                "filing_limit_days": 365,
                "supports_270_271": True,
                "supports_276_277": True,
                "supports_835_era": True,
                "connection_method": "sftp",
            },
        )
        assert payer_resp.status_code == 200, payer_resp.text
        payer_id = payer_resp.json()["data"]["id"]

        patient_resp = await ac.post(
            "/api/rcm/patients",
            headers=headers_a,
            json={
                "first_name": "Isolated",
                "last_name": "PatientA",
                "date_of_birth": "1985-01-01",
                "gender": "F",
                "address_line_1": "100 Test Street",
                "city": "Honolulu",
                "state": "HI",
                "zip_code": "96801",
                "member_id": "ISO-MBR-A-1",
                "payer_id": payer_id,
                "relationship_to_subscriber": "18",
            },
        )
        assert patient_resp.status_code == 200, patient_resp.text
        patient_id = patient_resp.json()["data"]["id"]

        claim_resp = await ac.post(
            "/api/rcm/claims",
            headers=headers_a,
            json={
                "patient_id": patient_id,
                "payer_id": payer_id,
                "service_date_from": str(date.today()),
                "total_charges": 125.00,
                "claim_type": "professional",
            },
        )
        assert claim_resp.status_code == 200, claim_resp.text
        claim_id = claim_resp.json()["data"]["id"]

        cross_patient = await ac.get(f"/api/rcm/patients/{patient_id}", headers=headers_b)
        assert cross_patient.status_code == 404

        list_patients_b = await ac.get("/api/rcm/patients", headers=headers_b)
        assert list_patients_b.status_code == 200
        assert all(row["id"] != patient_id for row in list_patients_b.json()["data"])

        cross_claim = await ac.get(f"/api/rcm/claims/{claim_id}", headers=headers_b)
        assert cross_claim.status_code == 404

        list_claims_b = await ac.get("/api/rcm/claims", headers=headers_b)
        assert list_claims_b.status_code == 200
        assert all(row["id"] != claim_id for row in list_claims_b.json()["data"])
