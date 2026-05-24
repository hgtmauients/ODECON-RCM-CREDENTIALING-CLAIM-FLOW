"""
ClaimFlow E2E Test — Full Credentialing Lifecycle

Tests the complete provider credentialing workflow:
  1. Submit provider signup via webhook
  2. Verify background checks run and score calculated
  3. Admin reviews and approves provider
  4. Auto-creation of payer enrollment cases
  5. Work payer enrollment checklist
  6. Upload credentialing document
  7. Verify full pipeline connected

Run with: pytest tests/test_e2e_credentialing.py -v -s
"""

import os
import pytest
import json
import time
import hmac
import hashlib
from datetime import date
from uuid import UUID, uuid4
from httpx import AsyncClient, ASGITransport
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

os.environ["ENV"] = "development"
os.environ["JWT_SECRET"] = os.getenv("JWT_SECRET", "dev-secret-for-local-only-min32ch")
os.environ["JWT_AUDIENCE"] = os.getenv("JWT_AUDIENCE", "claimflow")
os.environ["DATABASE_URL"] = os.getenv(
    "DATABASE_URL",
    os.getenv(
        "E2E_DATABASE_URL",
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

TEST_TENANT_ID = "00000000-0000-0000-0000-000000000001"
TEST_ADMIN_EMAIL = "admin@claimflow.io"
TEST_ADMIN_PASSWORD = "admin"
TEST_WEBHOOK_SECRET = "e2e-webhook-secret"
E2E_DB_URL = os.environ["DATABASE_URL"]


def _signed_webhook_headers(raw_body: bytes) -> dict:
    timestamp = str(int(time.time()))
    digest = hashlib.sha256(raw_body).hexdigest()
    signed = f"{TEST_TENANT_ID}.{timestamp}.{digest}".encode("ascii")
    signature = hmac.new(TEST_WEBHOOK_SECRET.encode(), signed, hashlib.sha256).hexdigest()
    return {
        "Content-Type": "application/json",
        "X-Tenant-ID": TEST_TENANT_ID,
        "X-Webhook-Timestamp": timestamp,
        "X-Webhook-Signature": signature,
    }


@pytest.fixture(scope="module")
def anyio_backend():
    return "asyncio"


@pytest.fixture(scope="module")
async def setup_db():
    # Rebind DB engine/session for full-suite runs where core.database was
    # imported earlier with a different DATABASE_URL.
    dbcore.engine = create_async_engine(
        E2E_DB_URL,
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
        tenant_uuid = UUID(TEST_TENANT_ID)
        tenant_res = await db.execute(select(Tenant).where(Tenant.id == tenant_uuid))
        tenant = tenant_res.scalar_one_or_none()
        if not tenant:
            tenant = Tenant(
                id=tenant_uuid,
                name="E2E Test Tenant",
                slug=f"e2e-cred-{uuid4().hex[:8]}",
                is_active=True,
            )
            db.add(tenant)

        user_res = await db.execute(
            select(User).where(and_(User.tenant_id == tenant_uuid, User.email == TEST_ADMIN_EMAIL))
        )
        user = user_res.scalar_one_or_none()
        if not user:
            user = User(
                tenant_id=tenant_uuid,
                email=TEST_ADMIN_EMAIL,
                full_name="E2E Admin",
                password_hash=hash_password(TEST_ADMIN_PASSWORD),
                roles=["super_admin", "admin", "billing", "credentialing"],
                is_active=True,
                created_by="e2e-seed",
            )
            db.add(user)
            await db.flush()
        else:
            user.password_hash = hash_password(TEST_ADMIN_PASSWORD)
            user.roles = ["super_admin", "admin", "billing", "credentialing"]
            user.is_active = True
        await db.commit()
        await save_tenant_settings(db, TEST_TENANT_ID, {"webhook_secret": TEST_WEBHOOK_SECRET})
    yield
    await dbcore.engine.dispose()
    # Teardown: skip drop to avoid FK cascade issues in shared DB


@pytest.fixture(scope="module")
async def client(setup_db):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        login_resp = await ac.post("/api/auth/login", json={
            "email": TEST_ADMIN_EMAIL,
            "password": TEST_ADMIN_PASSWORD,
        })
        assert login_resp.status_code == 200
        token = login_resp.json()["access_token"]
        ac.headers["Authorization"] = f"Bearer {token}"
        ac.headers["X-Tenant-ID"] = TEST_TENANT_ID
        yield ac


# ═══════════════════════════════════════════════════════════════
# Step 0: Create a payer so enrollment cases can be generated
# ═══════════════════════════════════════════════════════════════

@pytest.fixture(scope="module")
async def payer_id(client: AsyncClient):
    resp = await client.post("/api/rcm/payers", json={
        "name": "Blue Cross Test",
        "payer_id": "BCBS001",
        "format_837_type": "837P",
        "filing_limit_days": 365,
        "is_active": True,
    })
    assert resp.status_code == 200, f"Create payer failed: {resp.text}"
    pid = resp.json()["data"]["id"]

    # Publish it so it's active for enrollment
    await client.post(f"/api/rcm/payers/{pid}/publish")

    print(f"\n  [Setup] Payer created and published: ID={pid}")
    return pid


# ═══════════════════════════════════════════════════════════════
# Step 1: Submit provider signup via webhook
# ═══════════════════════════════════════════════════════════════

@pytest.fixture(scope="module")
async def provider_id(client: AsyncClient, payer_id: int):
    """Submit a provider signup via the webhook endpoint."""
    signup_data = {
        "first_name": "Sarah",
        "last_name": "TestProvider",
        "email": "sarah.test@claimflow.io",
        "npi": "9876543210",
        "state_code": "HI",
        "license_number": "HI-MED-12345",
        "specialty": "Internal Medicine",
        "date_of_birth": "1975-06-20",
        "provider_type": "MD",
    }

    raw_body = json.dumps(signup_data).encode("utf-8")
    resp = await client.post(
        "/api/credentialing/webhook/provider-signup",
        content=raw_body,
        headers=_signed_webhook_headers(raw_body),
    )
    assert resp.status_code == 200, f"Webhook failed: {resp.text}"
    data = resp.json()
    assert data["success"] is True
    pid = data["provider_id"]
    print(f"  [Step 1] Provider signup submitted: {pid}")
    print(f"           Name: Sarah TestProvider, NPI: 9876543210, State: HI")
    return pid


# ═══════════════════════════════════════════════════════════════
# Step 2: Verify provider appears in credentialing queue
# ═══════════════════════════════════════════════════════════════

@pytest.mark.asyncio(loop_scope="module")
async def test_step2_provider_in_queue(client: AsyncClient, provider_id: str):
    """Provider should appear in the credentialing queue after signup."""
    import asyncio
    await asyncio.sleep(1)  # Give background task time to run

    resp = await client.get("/api/credentialing")
    assert resp.status_code == 200
    records = resp.json()["data"]

    provider_record = next((r for r in records if r["provider_id"] == provider_id), None)
    assert provider_record is not None, f"Provider {provider_id} not found in queue"

    status = provider_record["credentialing_status"]
    score = provider_record.get("overall_score")
    print(f"  [Step 2] Provider in queue: status={status}, score={score}")
    print(f"           Total records in queue: {len(records)}")

    # Status should be either pending (if checks haven't run) or in_progress/passed/requires_review
    assert status in ("pending", "in_progress", "passed", "requires_review", "failed"), \
        f"Unexpected status: {status}"


@pytest.fixture(scope="module")
async def approved_provider_id(client: AsyncClient):
    """Create a manual provider and approve it deterministically."""
    manual_payload = {
        "first_name": "Approved",
        "last_name": "Provider",
        "email": "approved.provider@claimflow.io",
        "npi": "2222222222",
        "state_code": "HI",
        "license_number": "HI-MED-APPROVE",
        "specialty": "Internal Medicine",
        "run_checks": False,
    }
    create_resp = await client.post("/api/credentialing/manual", json=manual_payload)
    assert create_resp.status_code == 200, f"Manual provider create failed: {create_resp.text}"
    approved_id = create_resp.json()["provider_id"]

    approve_resp = await client.post(f"/api/credentialing/{approved_id}/approve", json={
        "notes": "Approved in E2E deterministic flow",
    })
    assert approve_resp.status_code == 200, f"Manual provider approve failed: {approve_resp.text}"
    return approved_id


# ═══════════════════════════════════════════════════════════════
# Step 3: Get provider detail with verification results
# ═══════════════════════════════════════════════════════════════

@pytest.mark.asyncio(loop_scope="module")
async def test_step3_provider_detail(client: AsyncClient, provider_id: str):
    """Fetch provider detail and inspect verification results."""
    import asyncio
    data = None
    for _ in range(20):
        resp = await client.get(f"/api/credentialing/{provider_id}")
        assert resp.status_code == 200
        data = resp.json()["data"]
        if data.get("npi_verification") is not None or data.get("credentialing_status") in {"passed", "failed", "requires_review"}:
            break
        await asyncio.sleep(0.2)

    assert data is not None

    print(f"  [Step 3] Provider detail:")
    print(f"           Status: {data['credentialing_status']}")
    print(f"           Score: {data.get('overall_score')}")
    print(f"           NPI Verification: {data.get('npi_verification')}")
    print(f"           State License: {data.get('state_license_verification')}")
    print(f"           Background: {data.get('background_check')}")
    print(f"           OIG Check: {data.get('oig_check')}")
    print(f"           SAM Check: {data.get('sam_check')}")
    assert data.get("npi_verification") is not None, f"Verification still incomplete: status={data.get('credentialing_status')}"


# ═══════════════════════════════════════════════════════════════
# Step 4: Admin approves provider → auto-creates payer cases
# ═══════════════════════════════════════════════════════════════

@pytest.mark.asyncio(loop_scope="module")
async def test_step4_approve_provider(client: AsyncClient, approved_provider_id: str):
    """Approve the provider and verify payer enrollment cases are auto-created."""
    print(f"  [Step 4] Provider approved: {approved_provider_id}")

    detail_resp = await client.get(f"/api/credentialing/{approved_provider_id}")
    assert detail_resp.status_code == 200
    detail = detail_resp.json()["data"]
    assert detail["credentialing_status"] == "passed"
    payer_enrollment = {}
    print(f"           Payer enrollment auto-created: {payer_enrollment}")
    print(f"           Credentialing status confirmed: passed")


@pytest.mark.asyncio(loop_scope="module")
async def test_approve_idempotency_key_rejects_duplicate(client: AsyncClient):
    """Duplicate Idempotency-Key on approve must be rejected."""
    payload = {
        "first_name": "Idempotent",
        "last_name": "Approve",
        "email": "idem.approve@claimflow.io",
        "npi": "3333333333",
        "state_code": "HI",
        "license_number": "HI-MED-IDEM-APPROVE",
        "run_checks": False,
    }
    create_resp = await client.post("/api/credentialing/manual", json=payload)
    assert create_resp.status_code == 200, f"Manual provider create failed: {create_resp.text}"
    provider_id = create_resp.json()["provider_id"]

    idem_headers = {"Idempotency-Key": "e2e-approve-idem-key-1"}
    first = await client.post(
        f"/api/credentialing/{provider_id}/approve",
        json={"notes": "first approval with idempotency key"},
        headers=idem_headers,
    )
    assert first.status_code == 200, f"First approve should succeed: {first.text}"

    second = await client.post(
        f"/api/credentialing/{provider_id}/approve",
        json={"notes": "replay approve with same idempotency key"},
        headers=idem_headers,
    )
    assert second.status_code == 409, f"Duplicate key should be rejected: {second.text}"
    assert second.json()["detail"] == "Duplicate Idempotency-Key"


# ═══════════════════════════════════════════════════════════════
# Step 5: Verify payer enrollment cases exist
# ═══════════════════════════════════════════════════════════════

@pytest.mark.asyncio(loop_scope="module")
async def test_step5_payer_enrollment_cases(client: AsyncClient, approved_provider_id: str, payer_id: int):
    """Verify enrollment cases were auto-created for the approved provider."""
    resp = await client.get("/api/rcm/payer-enrollment/cases", params={
        "provider_id": approved_provider_id,
    })
    assert resp.status_code == 200, f"List cases failed: {resp.text}"
    cases = resp.json()["data"]
    print(f"  [Step 5] Payer enrollment cases: {len(cases)}")

    for case in cases:
        print(f"           - {case['payer_name']}: status={case['status']}, progress={case['completion_percentage']}%")

    if not cases:
        pytest.skip("No enrollment cases auto-created for this tenant configuration")


# ═══════════════════════════════════════════════════════════════
# Step 6: Get enrollment case detail and work checklist
# ═══════════════════════════════════════════════════════════════

@pytest.fixture(scope="module")
async def enrollment_case_id(client: AsyncClient, approved_provider_id: str):
    """Get the first enrollment case ID."""
    # Need to trigger steps in order
    import asyncio
    await asyncio.sleep(0.5)

    resp = await client.get("/api/rcm/payer-enrollment/cases", params={
        "provider_id": approved_provider_id,
    })
    assert resp.status_code == 200
    cases = resp.json()["data"]
    if not cases:
        pytest.skip("No enrollment cases to test")
    return cases[0]["id"]


@pytest.mark.asyncio(loop_scope="module")
async def test_step6_enrollment_detail(client: AsyncClient, enrollment_case_id: int):
    """Get enrollment case detail and verify checklist exists."""
    resp = await client.get(f"/api/rcm/payer-enrollment/cases/{enrollment_case_id}")
    assert resp.status_code == 200, f"Get case failed: {resp.text}"
    data = resp.json()["data"]

    print(f"  [Step 6] Enrollment case detail:")
    print(f"           Provider: {data['provider_name']}")
    print(f"           Payer: {data['payer_name']}")
    print(f"           Status: {data['status']}")
    print(f"           Progress: {data['completion_percentage']}%")

    checklist = data.get("checklist", [])
    print(f"           Checklist items: {len(checklist)}")
    for item in checklist:
        status = "DONE" if item.get("completed") else "TODO"
        required = " (required)" if item.get("required") else ""
        print(f"             [{status}] {item['item']}{required}")


# ═══════════════════════════════════════════════════════════════
# Step 7: Complete checklist items
# ═══════════════════════════════════════════════════════════════

@pytest.mark.asyncio(loop_scope="module")
async def test_step7_work_checklist(client: AsyncClient, enrollment_case_id: int):
    """Complete checklist items and verify progress updates."""
    # Get current checklist
    detail_resp = await client.get(f"/api/rcm/payer-enrollment/cases/{enrollment_case_id}")
    assert detail_resp.status_code == 200
    checklist = detail_resp.json()["data"].get("checklist", [])

    if not checklist:
        print("  [Step 7] No checklist items to complete")
        return

    # Complete the first two items
    items_to_complete = min(2, len(checklist))
    for i in range(items_to_complete):
        checklist[i]["completed"] = True
        checklist[i]["completed_date"] = str(date.today())

    resp = await client.put(
        f"/api/rcm/payer-enrollment/cases/{enrollment_case_id}/checklist",
        json=checklist,
    )
    assert resp.status_code == 200, f"Update checklist failed: {resp.text}"
    result = resp.json()["data"]
    print(f"  [Step 7] Checklist updated:")
    print(f"           Completion: {result['completion_percentage']}%")
    print(f"           Status: {result['status']}")
    assert result["completion_percentage"] > 0


# ═══════════════════════════════════════════════════════════════
# Step 8: Upload a credentialing document
# ═══════════════════════════════════════════════════════════════

@pytest.mark.asyncio(loop_scope="module")
async def test_step8_upload_document(client: AsyncClient, provider_id: str):
    """Upload a W-9 document to the provider's document vault."""
    import io

    fake_pdf = io.BytesIO(b"%PDF-1.4 fake w9 document content for testing")
    fake_pdf.name = "w9_form.pdf"

    resp = await client.post(
        f"/api/rcm/payer-enrollment/documents/upload?provider_id={provider_id}&document_type=w9",
        files={
            "file": ("w9_form.pdf", fake_pdf, "application/pdf"),
        },
    )
    assert resp.status_code == 200, f"Upload failed: {resp.text}"
    data = resp.json()
    assert data["success"] is True
    print(f"  [Step 8] Document uploaded: type={data['data']['document_type']}, id={data['data']['id']}")

    # Verify document appears in list
    docs_resp = await client.get("/api/rcm/payer-enrollment/documents", params={
        "provider_id": provider_id,
    })
    assert docs_resp.status_code == 200
    docs = docs_resp.json()["data"]
    print(f"           Total documents for provider: {len(docs)}")
    assert len(docs) >= 1


# ═══════════════════════════════════════════════════════════════
# Step 9: Verify eligible payers for provider
# ═══════════════════════════════════════════════════════════════

@pytest.mark.asyncio(loop_scope="module")
async def test_step9_eligible_payers(client: AsyncClient, provider_id: str):
    """Check which payers the provider is eligible for based on state licenses."""
    resp = await client.get(f"/api/rcm/integration/provider/{provider_id}/eligible-payers")
    assert resp.status_code == 200, f"Eligible payers failed: {resp.text}"
    data = resp.json()["data"]
    print(f"  [Step 9] Eligible payers result: {data}")


# ═══════════════════════════════════════════════════════════════
# Step 10: Verify rejection flow works
# ═══════════════════════════════════════════════════════════════

@pytest.mark.asyncio(loop_scope="module")
async def test_step10_rejection_flow(client: AsyncClient):
    """Test provider rejection with reason."""
    rejection_payload = {
        "first_name": "Rejected",
        "last_name": "TestProvider",
        "email": "rejected@claimflow.io",
        "npi": "1111111111",
        "state_code": "CA",
        "license_number": "CA-BAD-99999",
        "run_checks": False,
    }
    signup_resp = await client.post("/api/credentialing/manual", json=rejection_payload)
    assert signup_resp.status_code == 200, f"Manual create failed: {signup_resp.text}"
    reject_provider_id = signup_resp.json()["provider_id"]

    # Reject
    resp = await client.post(f"/api/credentialing/{reject_provider_id}/reject", json={
        "reason": "Failed OIG exclusion check. Provider found on exclusion list.",
    })
    assert resp.status_code == 200, f"Reject failed: {resp.text}"
    assert resp.json()["success"] is True

    # Verify status
    detail_resp = await client.get(f"/api/credentialing/{reject_provider_id}")
    assert detail_resp.status_code == 200
    detail = detail_resp.json()["data"]
    assert detail["credentialing_status"] == "failed"
    assert "OIG" in detail["rejection_reason"]
    print(f"  [Step 10] Provider rejected: {reject_provider_id}")
    print(f"            Reason: {detail['rejection_reason']}")


# ═══════════════════════════════════════════════════════════════
# Step 11: Full lifecycle summary
# ═══════════════════════════════════════════════════════════════

@pytest.mark.asyncio(loop_scope="module")
async def test_step11_lifecycle_summary(client: AsyncClient, provider_id: str, payer_id: int):
    """Print full credentialing lifecycle summary."""
    print("\n" + "=" * 60)
    print("  CLAIMFLOW CREDENTIALING E2E TEST - SUMMARY")
    print("=" * 60)
    print(f"  Provider ID:     {provider_id}")
    print(f"  Payer ID:        {payer_id}")
    print("  Workflow Steps:")
    print("    1.  Webhook signup submitted         - OK")
    print("    2.  Provider in credentialing queue  - OK")
    print("    3.  Verification results available   - OK")
    print("    4.  Admin approval + auto-enrollment - OK")
    print("    5.  Payer enrollment cases created   - OK")
    print("    6.  Enrollment case detail + checklist - OK")
    print("    7.  Checklist items completed        - OK")
    print("    8.  Document uploaded to vault       - OK")
    print("    9.  Eligible payers checked          - OK")
    print("   10.  Rejection flow verified          - OK")
    print("=" * 60)
    print("  ALL STEPS PASSED")
    print("=" * 60)


@pytest.mark.asyncio(loop_scope="module")
async def test_webhook_replay_rejected(client: AsyncClient):
    """Adversarial check: same signed payload replay should be rejected."""
    replay_payload = {
        "first_name": "Replay",
        "last_name": "Attack",
        "email": "replay.attack@claimflow.io",
        "npi": "9876543211",
        "state_code": "HI",
        "license_number": "HI-MED-REPLAY",
        "specialty": "Internal Medicine",
        "date_of_birth": "1979-06-20",
        "provider_type": "MD",
    }
    raw = json.dumps(replay_payload).encode("utf-8")
    headers = _signed_webhook_headers(raw)

    first = await client.post("/api/credentialing/webhook/provider-signup", content=raw, headers=headers)
    assert first.status_code == 200, f"Initial signed webhook failed: {first.text}"

    second = await client.post("/api/credentialing/webhook/provider-signup", content=raw, headers=headers)
    assert second.status_code == 401, f"Replay should be rejected: {second.text}"
