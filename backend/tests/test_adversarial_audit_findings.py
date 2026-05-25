"""
Adversarial audit verification tests.

These tests intentionally codify currently exploitable behaviors so the risks
are proven in code and can be regression-tested after remediation.
"""

import hashlib
import hmac
import json
import os
import time
from uuid import UUID, uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

os.environ["ENV"] = "development"
os.environ["JWT_SECRET"] = os.getenv("JWT_SECRET", "dev-secret-for-local-only-min32ch")
os.environ["JWT_AUDIENCE"] = os.getenv("JWT_AUDIENCE", "claimflow")
os.environ["DATABASE_URL"] = os.getenv(
    "E2E_DATABASE_URL",
    os.getenv(
        "DATABASE_URL",
        "postgresql+asyncpg://postgres:postgres@localhost:5432/postgres",
    ),
)

from app.main import app
import core.database as dbcore
from core.password import hash_password
from core.tenant_config import save_tenant_settings
from models.base import Base
from models.tenant import Tenant
from models.user import User

pytestmark = pytest.mark.security

ACTIVE_TENANT_ID = "00000000-0000-0000-0000-0000000000c1"
INACTIVE_TENANT_ID = "00000000-0000-0000-0000-0000000000d2"
ADMIN_EMAIL = "audit-adversarial-admin@claimflow.io"
ADMIN_PASSWORD = "admin"
TEST_DB_URL = os.environ["DATABASE_URL"]
INACTIVE_WEBHOOK_SECRET = "inactive-tenant-secret"


@pytest.fixture(scope="module")
def anyio_backend():
    return "asyncio"


def _signed_webhook_headers(tenant_id: str, secret: str, raw_body: bytes) -> dict:
    timestamp = str(int(time.time()))
    digest = hashlib.sha256(raw_body).hexdigest()
    signed_message = f"{tenant_id}.{timestamp}.{digest}".encode("ascii")
    signature = hmac.new(secret.encode(), signed_message, hashlib.sha256).hexdigest()
    return {
        "Content-Type": "application/json",
        "X-Tenant-ID": tenant_id,
        "X-Webhook-Timestamp": timestamp,
        "X-Webhook-Signature": signature,
    }


@pytest.fixture(scope="module")
async def setup_db():
    dbcore.engine = create_async_engine(
        TEST_DB_URL,
        echo=False,
        pool_size=10,
        max_overflow=20,
        pool_pre_ping=True,
    )
    dbcore.async_session_factory = async_sessionmaker(
        dbcore.engine,
        class_=dbcore.AsyncSession,
        expire_on_commit=False,
    )

    async with dbcore.engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with dbcore.async_session_factory() as db:
        active_uuid = UUID(ACTIVE_TENANT_ID)
        inactive_uuid = UUID(INACTIVE_TENANT_ID)

        active_tenant = (
            await db.execute(select(Tenant).where(Tenant.id == active_uuid))
        ).scalar_one_or_none()
        if not active_tenant:
            active_tenant = Tenant(
                id=active_uuid,
                name="Audit Active Tenant",
                slug=f"audit-active-{uuid4().hex[:8]}",
                is_active=True,
            )
            db.add(active_tenant)

        inactive_tenant = (
            await db.execute(select(Tenant).where(Tenant.id == inactive_uuid))
        ).scalar_one_or_none()
        if not inactive_tenant:
            inactive_tenant = Tenant(
                id=inactive_uuid,
                name="Audit Inactive Tenant",
                slug=f"audit-inactive-{uuid4().hex[:8]}",
                is_active=False,
            )
            db.add(inactive_tenant)
        else:
            inactive_tenant.is_active = False

        user = (
            await db.execute(
                select(User).where(and_(User.tenant_id == active_uuid, User.email == ADMIN_EMAIL))
            )
        ).scalar_one_or_none()
        if not user:
            user = User(
                tenant_id=active_uuid,
                email=ADMIN_EMAIL,
                full_name="Audit Adversarial Admin",
                password_hash=hash_password(ADMIN_PASSWORD),
                roles=["super_admin", "admin", "billing", "credentialing"],
                is_active=True,
                created_by="audit-adversarial-tests",
            )
            db.add(user)
        else:
            user.password_hash = hash_password(ADMIN_PASSWORD)
            user.roles = ["super_admin", "admin", "billing", "credentialing"]
            user.is_active = True

        await db.commit()
        await save_tenant_settings(db, INACTIVE_TENANT_ID, {"webhook_secret": INACTIVE_WEBHOOK_SECRET})

    yield
    await dbcore.engine.dispose()


@pytest.fixture(scope="module")
async def client(setup_db):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        login = await ac.post("/api/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
        assert login.status_code == 200, login.text
        token = login.json()["access_token"]
        ac.headers["Authorization"] = f"Bearer {token}"
        ac.headers["X-Tenant-ID"] = ACTIVE_TENANT_ID
        yield ac


@pytest.mark.asyncio(loop_scope="module")
async def test_admin_cannot_approve_while_pending_without_checks(client: AsyncClient):
    """
    Security requirement:
    A provider must not be approvable from pending before verification completes.
    """
    create_resp = await client.post(
        "/api/credentialing/manual",
        json={
            "first_name": "Pending",
            "last_name": "Bypass",
            "email": "pending.bypass@claimflow.io",
            "npi": "7777777777",
            "state_code": "HI",
            "license_number": "HI-MED-PENDING-BYPASS",
            "specialty": "Internal Medicine",
            "run_checks": False,
        },
    )
    assert create_resp.status_code == 200, create_resp.text
    provider_id = create_resp.json()["provider_id"]

    approve_resp = await client.post(
        f"/api/credentialing/{provider_id}/approve",
        json={"notes": "Adversarial verification approve-before-checks"},
    )
    assert approve_resp.status_code == 409, approve_resp.text
    assert approve_resp.json()["detail"] == "Verification has not completed; run checks before approving"

    detail_resp = await client.get(f"/api/credentialing/{provider_id}")
    assert detail_resp.status_code == 200, detail_resp.text
    data = detail_resp.json()["data"]
    assert data["credentialing_status"] == "pending"
    assert data["npi_verification"] is None
    assert data["state_license_verification"] is None
    assert data["background_check"] is None
    assert data["oig_check"] is None
    assert data["sam_check"] is None


@pytest.mark.asyncio(loop_scope="module")
async def test_inactive_tenant_signed_webhook_is_rejected(setup_db):
    """
    Security requirement:
    Signed webhook for an inactive tenant must be rejected.
    """
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        payload = {
            "first_name": "Inactive",
            "last_name": "TenantWebhook",
            "email": "inactive.tenant.webhook@claimflow.io",
            "npi": "8888888888",
            "state_code": "HI",
            "license_number": "HI-MED-INACTIVE-TENANT",
            "specialty": "Internal Medicine",
            "date_of_birth": "1980-08-08",
            "provider_type": "MD",
        }
        raw_body = json.dumps(payload).encode("utf-8")
        headers = _signed_webhook_headers(INACTIVE_TENANT_ID, INACTIVE_WEBHOOK_SECRET, raw_body)
        resp = await ac.post("/api/credentialing/webhook/provider-signup", content=raw_body, headers=headers)

    assert resp.status_code == 401, resp.text
    assert resp.json()["detail"] == "Invalid webhook signature"
