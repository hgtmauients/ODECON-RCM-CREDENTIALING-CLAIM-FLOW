"""
Adversarial tenant-escape tests.

Focus areas:
1) Header spoofing (`X-Tenant-ID`) against JWT tenant binding.
2) IDOR attempts via cross-tenant related object IDs.
3) Background-job context leakage (missing tenant_id propagation).
"""

import os
from datetime import date
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

os.environ["ENV"] = "development"
os.environ["JWT_SECRET"] = os.getenv("JWT_SECRET", "dev-secret-for-local-only-min32ch")
os.environ["JWT_AUDIENCE"] = os.getenv("JWT_AUDIENCE", "claimflow")
os.environ["AUTH_LOGIN_INCLUDE_TOKEN"] = os.getenv("AUTH_LOGIN_INCLUDE_TOKEN", "true")
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
from models.base import Base
from models.audit import SecurityAuditLog
from models.tenant import Tenant
from models.user import User

pytestmark = pytest.mark.security

TENANT_A_ID = "00000000-0000-0000-0000-0000000000a1"
TENANT_B_ID = "00000000-0000-0000-0000-0000000000b2"
TENANT_A_EMAIL = "escape-a@claimflow.io"
TENANT_B_EMAIL = "escape-b@claimflow.io"
SUPER_ADMIN_EMAIL = "escape-superadmin@claimflow.io"
TEST_PASSWORD = "admin"
TEST_DB_URL = os.environ["DATABASE_URL"]


@pytest.fixture(scope="module")
def anyio_backend():
    return "asyncio"


async def _ensure_tenant_and_user(
    tenant_id: str,
    email: str,
    slug: str,
    name: str,
    roles: list[str],
) -> None:
    tenant_uuid = UUID(tenant_id)
    async with dbcore.async_session_factory() as db:
        tenant = (await db.execute(select(Tenant).where(Tenant.id == tenant_uuid))).scalar_one_or_none()
        if not tenant:
            tenant = Tenant(
                id=tenant_uuid,
                name=name,
                slug=slug,
                is_active=True,
            )
            db.add(tenant)

        user = (await db.execute(select(User).where(and_(User.tenant_id == tenant_uuid, User.email == email)))).scalar_one_or_none()
        if not user:
            user = User(
                tenant_id=tenant_uuid,
                email=email,
                full_name=name + " Admin",
                password_hash=hash_password(TEST_PASSWORD),
                roles=roles,
                is_active=True,
                created_by="tenant-escape-test",
            )
            db.add(user)
        else:
            user.password_hash = hash_password(TEST_PASSWORD)
            user.roles = roles
            user.is_active = True
        await db.commit()


@pytest.fixture(scope="module")
async def setup_db():
    # Rebind DB engine/session so this module is stable inside full-suite runs
    # regardless of earlier imports that may have captured a different URL.
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

    await _ensure_tenant_and_user(
        tenant_id=TENANT_A_ID,
        email=TENANT_A_EMAIL,
        slug="tenant-escape-a",
        name="Tenant Escape A",
        roles=["admin", "billing", "credentialing"],  # intentionally not super_admin
    )
    await _ensure_tenant_and_user(
        tenant_id=TENANT_B_ID,
        email=TENANT_B_EMAIL,
        slug="tenant-escape-b",
        name="Tenant Escape B",
        roles=["admin", "billing", "credentialing"],
    )
    await _ensure_tenant_and_user(
        tenant_id=TENANT_A_ID,
        email=SUPER_ADMIN_EMAIL,
        slug="tenant-escape-a",
        name="Tenant Escape Super Admin",
        roles=["super_admin", "admin", "billing", "credentialing"],
    )
    yield
    await dbcore.engine.dispose()


async def _auth_headers(ac: AsyncClient, email: str, tenant_id: str) -> dict[str, str]:
    resp = await ac.post("/api/auth/login", json={"email": email, "password": TEST_PASSWORD})
    assert resp.status_code == 200, f"login failed for {email}: {resp.text}"
    token = resp.json()["access_token"]
    return {
        "Authorization": f"Bearer {token}",
        "X-Tenant-ID": tenant_id,
    }


@pytest.mark.asyncio(loop_scope="module")
async def test_header_spoofing_rejected_for_non_super_admin(setup_db, caplog):
    """
    Exploit attempt: valid token for tenant A + forged X-Tenant-ID tenant B.
    Expectation: hard reject with 403 for non-super-admin principals.
    """
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        headers_a = await _auth_headers(ac, TENANT_A_EMAIL, TENANT_A_ID)
        forged = dict(headers_a)
        forged["X-Tenant-ID"] = TENANT_B_ID

        resp = await ac.get("/api/auth/me", headers=forged)
        assert resp.status_code == 403
        assert "requires super_admin" in resp.text
        assert any("tenant_override_denied" in rec.message for rec in caplog.records)


@pytest.mark.asyncio(loop_scope="module")
async def test_super_admin_override_only_when_explicitly_requested(setup_db, caplog):
    """
    Negative control:
    - same super_admin token without X-Tenant-ID => acts in token tenant
    - same token with explicit X-Tenant-ID => acts in requested tenant
    """
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        sa_headers = await _auth_headers(ac, SUPER_ADMIN_EMAIL, TENANT_A_ID)

        no_override = dict(sa_headers)
        no_override.pop("X-Tenant-ID", None)
        me_default = await ac.get("/api/auth/me", headers=no_override)
        assert me_default.status_code == 200, me_default.text
        assert me_default.json()["tenant_id"] == TENANT_A_ID

        with_override = dict(sa_headers)
        with_override["X-Tenant-ID"] = TENANT_B_ID
        me_override = await ac.get("/api/auth/me", headers=with_override)
        assert me_override.status_code == 200, me_override.text
        assert me_override.json()["tenant_id"] == TENANT_B_ID
        assert any("tenant_override_applied" in rec.message for rec in caplog.records)


@pytest.mark.asyncio(loop_scope="module")
async def test_idor_cross_tenant_foreign_keys_blocked_on_claim_create(setup_db):
    """
    Exploit attempt: tenant B user submits claim referencing tenant A patient/payer IDs.
    Expectation: 422 validation error (cross-tenant foreign key rejected).
    """
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        headers_a = await _auth_headers(ac, TENANT_A_EMAIL, TENANT_A_ID)
        headers_b = await _auth_headers(ac, TENANT_B_EMAIL, TENANT_B_ID)

        payer_resp = await ac.post(
            "/api/rcm/payers",
            headers=headers_a,
            json={
                "name": "Escape Test Payer A",
                "payer_id": "ESCAPEA001",
                "format_837_type": "837P",
                "filing_limit_days": 365,
                "supports_270_271": True,
                "supports_276_277": True,
                "supports_835_era": True,
                "connection_method": "sftp",
            },
        )
        assert payer_resp.status_code == 200, payer_resp.text
        payer_a_id = payer_resp.json()["data"]["id"]

        patient_resp = await ac.post(
            "/api/rcm/patients",
            headers=headers_a,
            json={
                "first_name": "Victim",
                "last_name": "TenantA",
                "date_of_birth": "1985-01-01",
                "gender": "F",
                "address_line_1": "100 Test Street",
                "city": "Honolulu",
                "state": "HI",
                "zip_code": "96801",
                "member_id": "ESCAPE-MBR-A",
                "payer_id": payer_a_id,
                "relationship_to_subscriber": "18",
            },
        )
        assert patient_resp.status_code == 200, patient_resp.text
        patient_a_id = patient_resp.json()["data"]["id"]

        attack_resp = await ac.post(
            "/api/rcm/claims",
            headers=headers_b,
            json={
                "patient_id": patient_a_id,
                "payer_id": payer_a_id,
                "service_date_from": str(date.today()),
                "total_charges": 125.00,
                "claim_type": "professional",
            },
        )

        assert attack_resp.status_code == 422
        assert "not in tenant" in attack_resp.text


@pytest.mark.asyncio(loop_scope="module")
async def test_idor_cross_tenant_foreign_keys_blocked_on_claim_update(setup_db):
    """
    Exploit attempt: tenant B updates its draft claim to point at tenant A
    patient/payer IDs. Expectation: 422 validation error.
    """
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        headers_a = await _auth_headers(ac, TENANT_A_EMAIL, TENANT_A_ID)
        headers_b = await _auth_headers(ac, TENANT_B_EMAIL, TENANT_B_ID)

        payer_a_resp = await ac.post(
            "/api/rcm/payers",
            headers=headers_a,
            json={
                "name": "Escape Update Payer A",
                "payer_id": f"ESUPA{uuid4().hex[:8].upper()}",
                "format_837_type": "837P",
                "filing_limit_days": 365,
                "supports_270_271": True,
                "supports_276_277": True,
                "supports_835_era": True,
                "connection_method": "sftp",
            },
        )
        assert payer_a_resp.status_code == 200, payer_a_resp.text
        payer_a_id = payer_a_resp.json()["data"]["id"]

        patient_a_resp = await ac.post(
            "/api/rcm/patients",
            headers=headers_a,
            json={
                "first_name": "Victim",
                "last_name": "UpdateA",
                "date_of_birth": "1985-01-01",
                "gender": "F",
                "address_line_1": "100 Test Street",
                "city": "Honolulu",
                "state": "HI",
                "zip_code": "96801",
                "member_id": f"ESCAPE-UPD-A-{uuid4().hex[:8]}",
                "payer_id": payer_a_id,
                "relationship_to_subscriber": "18",
            },
        )
        assert patient_a_resp.status_code == 200, patient_a_resp.text
        patient_a_id = patient_a_resp.json()["data"]["id"]

        payer_b_resp = await ac.post(
            "/api/rcm/payers",
            headers=headers_b,
            json={
                "name": "Escape Update Payer B",
                "payer_id": f"ESUPB{uuid4().hex[:8].upper()}",
                "format_837_type": "837P",
                "filing_limit_days": 365,
                "supports_270_271": True,
                "supports_276_277": True,
                "supports_835_era": True,
                "connection_method": "sftp",
            },
        )
        assert payer_b_resp.status_code == 200, payer_b_resp.text
        payer_b_id = payer_b_resp.json()["data"]["id"]

        patient_b_resp = await ac.post(
            "/api/rcm/patients",
            headers=headers_b,
            json={
                "first_name": "Owner",
                "last_name": "UpdateB",
                "date_of_birth": "1985-01-01",
                "gender": "F",
                "address_line_1": "100 Test Street",
                "city": "Honolulu",
                "state": "HI",
                "zip_code": "96801",
                "member_id": f"ESCAPE-UPD-B-{uuid4().hex[:8]}",
                "payer_id": payer_b_id,
                "relationship_to_subscriber": "18",
            },
        )
        assert patient_b_resp.status_code == 200, patient_b_resp.text
        patient_b_id = patient_b_resp.json()["data"]["id"]

        claim_b_resp = await ac.post(
            "/api/rcm/claims",
            headers=headers_b,
            json={
                "patient_id": patient_b_id,
                "payer_id": payer_b_id,
                "service_date_from": str(date.today()),
                "total_charges": 95.00,
                "claim_type": "professional",
            },
        )
        assert claim_b_resp.status_code == 200, claim_b_resp.text
        claim_b_id = claim_b_resp.json()["data"]["id"]

        update_attack = await ac.put(
            f"/api/rcm/claims/{claim_b_id}",
            headers=headers_b,
            json={"patient_id": patient_a_id, "payer_id": payer_a_id},
        )
        assert update_attack.status_code == 422
        assert "not in tenant" in update_attack.text


@pytest.mark.asyncio(loop_scope="module")
async def test_super_admin_impersonation_audit_keeps_original_token_tenant(setup_db):
    """
    Exploit-style verification:
    A super_admin from tenant A acts on tenant B via explicit header override.
    The audited claim_created row must retain token_tenant_id=A and effective=B.
    """
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        headers_b = await _auth_headers(ac, TENANT_B_EMAIL, TENANT_B_ID)
        sa_headers = await _auth_headers(ac, SUPER_ADMIN_EMAIL, TENANT_A_ID)
        sa_headers["X-Tenant-ID"] = TENANT_B_ID

        payer_resp = await ac.post(
            "/api/rcm/payers",
            headers=headers_b,
            json={
                "name": "Escape Test Payer B",
                "payer_id": f"ESCAPEB{uuid4().hex[:6].upper()}",
                "format_837_type": "837P",
                "filing_limit_days": 365,
                "supports_270_271": True,
                "supports_276_277": True,
                "supports_835_era": True,
                "connection_method": "sftp",
            },
        )
        assert payer_resp.status_code == 200, payer_resp.text
        payer_b_id = payer_resp.json()["data"]["id"]

        patient_resp = await ac.post(
            "/api/rcm/patients",
            headers=headers_b,
            json={
                "first_name": "Target",
                "last_name": "TenantB",
                "date_of_birth": "1980-02-02",
                "gender": "M",
                "address_line_1": "200 Test Street",
                "city": "Honolulu",
                "state": "HI",
                "zip_code": "96802",
                "member_id": f"ESCAPE-MBR-B-{uuid4().hex[:8]}",
                "payer_id": payer_b_id,
                "relationship_to_subscriber": "18",
            },
        )
        assert patient_resp.status_code == 200, patient_resp.text
        patient_b_id = patient_resp.json()["data"]["id"]

        claim_resp = await ac.post(
            "/api/rcm/claims",
            headers=sa_headers,
            json={
                "patient_id": patient_b_id,
                "payer_id": payer_b_id,
                "service_date_from": str(date.today()),
                "total_charges": 99.00,
                "claim_type": "professional",
            },
        )
        assert claim_resp.status_code == 200, claim_resp.text
        claim_id = claim_resp.json()["data"]["id"]

    async with dbcore.async_session_factory() as db:
        row = (
            await db.execute(
                select(SecurityAuditLog).where(
                    and_(
                        SecurityAuditLog.action == "claim_created",
                        SecurityAuditLog.resource_type == "claim",
                        SecurityAuditLog.resource_id == str(claim_id),
                        SecurityAuditLog.user_email == SUPER_ADMIN_EMAIL,
                    )
                )
            )
        ).scalar_one_or_none()

        assert row is not None, "Expected claim_created audit row for super_admin impersonation"
        assert str(row.tenant_id) == TENANT_B_ID
        assert row.extra_data is not None
        assert row.extra_data.get("is_impersonating") is True
        assert row.extra_data.get("token_tenant_id") == TENANT_A_ID
        assert row.extra_data.get("effective_tenant_id") == TENANT_B_ID


class _FakeScalarResult:
    def __init__(self, items):
        self._items = items

    def all(self):
        return self._items


class _FakeExecuteResult:
    def __init__(self, items):
        self._items = items

    def scalars(self):
        return _FakeScalarResult(self._items)


class _FakeDB:
    def __init__(self, execute_results):
        self._execute_results = list(execute_results)

    async def execute(self, _query):
        return _FakeExecuteResult(self._execute_results.pop(0))


@pytest.mark.asyncio
async def test_background_835_pipeline_always_propagates_tenant_context(monkeypatch):
    """
    Exploit attempt model: worker accidentally drops tenant_id and mutates
    records across tenants. This test asserts tenant_id is threaded into every
    downstream processor call in the 835 poll path.
    """
    import jobs.poll_835_files as poll_job

    tenant = SimpleNamespace(id=UUID(TENANT_A_ID), slug="tenant-a")
    payer = SimpleNamespace(id=77, name="Payer A")
    db = _FakeDB([[payer]])

    seen: dict[str, object] = {}

    class FakeTransport:
        def __init__(self, _db):
            pass

        async def poll_for_835_files(self, payer_id, tenant_id):
            seen["transport_tenant_id"] = tenant_id
            seen["transport_payer_id"] = payer_id
            return ["/tmp/fake.835"]

    class FakeEDIProcessor:
        def __init__(self, _db):
            pass

        async def parse_835(self, file_path, tenant_id=None):
            seen["parse_835_tenant_id"] = tenant_id
            seen["parse_835_file"] = file_path
            return {"payments": [{"amount": 1.0}], "denials": [{"carc": "45"}], "edi_file_id": 999}

    class FakeDenialManager:
        def __init__(self, _db):
            pass

        async def process_835_denials(self, edi_file_id, denials_data, tenant_id=None):
            seen["denial_tenant_id"] = tenant_id
            seen["denial_edi_file_id"] = edi_file_id
            seen["denial_count"] = len(denials_data)

    class FakeAutoPoster:
        def __init__(self, _db):
            pass

        async def auto_post_835(self, edi_file_id, payments_data, tenant_id=None):
            seen["autopost_tenant_id"] = tenant_id
            seen["autopost_edi_file_id"] = edi_file_id
            seen["payments_count"] = len(payments_data)

    monkeypatch.setattr(poll_job, "ClearinghouseService", FakeTransport)
    monkeypatch.setattr(poll_job, "EDIProcessor", FakeEDIProcessor)
    monkeypatch.setattr(poll_job, "DenialManager", FakeDenialManager)
    monkeypatch.setattr(poll_job, "AutoPostingEngine", FakeAutoPoster)

    await poll_job._poll_835_for_tenant(db, tenant)

    expected_tid = TENANT_A_ID
    assert seen["transport_tenant_id"] == expected_tid
    assert seen["parse_835_tenant_id"] == expected_tid
    assert seen["autopost_tenant_id"] == expected_tid
    assert seen["denial_tenant_id"] == expected_tid


@pytest.mark.asyncio
async def test_background_277_pipeline_always_propagates_tenant_context(monkeypatch):
    """
    Exploit attempt model: 277 poller passes None tenant_id and allows
    cross-tenant status updates. This verifies tenant_id is always forwarded.
    """
    import jobs.poll_835_files as poll_job

    tenant = SimpleNamespace(id=UUID(TENANT_A_ID), slug="tenant-a", is_active=True)
    payer = SimpleNamespace(id=88, name="Payer B")
    db = _FakeDB([[tenant], [payer]])

    seen: dict[str, object] = {"parse_277_tenant_ids": []}

    async def fake_get_async_session(**_kwargs):
        yield db

    class FakeTransport:
        def __init__(self, _db):
            pass

        async def poll_for_277_files(self, payer_id, tenant_id):
            seen["transport_277_tenant_id"] = tenant_id
            seen["transport_277_payer_id"] = payer_id
            return ["/tmp/fake.277"]

    class FakeEDIProcessor:
        def __init__(self, _db):
            pass

        async def parse_277(self, file_path, tenant_id=None):
            seen["parse_277_file"] = file_path
            seen["parse_277_tenant_ids"].append(tenant_id)
            return {"processed_claims": 1}

    monkeypatch.setattr(poll_job, "get_async_session", fake_get_async_session)
    monkeypatch.setattr(poll_job, "ClearinghouseService", FakeTransport)
    monkeypatch.setattr(poll_job, "EDIProcessor", FakeEDIProcessor)

    await poll_job.poll_277_files()

    expected_tid = TENANT_A_ID
    assert seen["transport_277_tenant_id"] == expected_tid
    assert seen["parse_277_tenant_ids"] == [expected_tid]

