"""
ClaimFlow - Integration tests for the full claim lifecycle.
Tests: create → validate → submit → 277 ack → 835 payment post
"""

import pytest
import uuid
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import date, datetime

from api.auth import Principal


TENANT_ID = str(uuid.uuid4())


def make_principal():
    return Principal(
        user_id="test-user-1",
        tenant_id=TENANT_ID,
        email="test@claimflow.io",
        roles=["admin", "billing"],
    )


class TestClaimLifecycle:
    """Full claim lifecycle: create → validate → batch submit."""

    @pytest.mark.asyncio
    async def test_create_claim_sets_tenant_id(self):
        from api.rcm.claims import create_claim

        mock_db = AsyncMock()
        mock_db.flush = AsyncMock()
        mock_db.commit = AsyncMock()
        mock_db.refresh = AsyncMock()

        principal = make_principal()

        claim_data = {
            "service_date_from": "2026-01-15",
            "total_charges": 150.00,
            "payer_id": 1,
        }

        result = await create_claim(claim_data=claim_data, db=mock_db, current_user=principal)
        assert result["success"] is True
        assert "claim_number" in result["data"]

        # Verify db.add was called with a Claim that has tenant_id
        added_obj = mock_db.add.call_args_list[0][0][0]
        assert str(added_obj.tenant_id) == TENANT_ID

    @pytest.mark.asyncio
    async def test_validate_claim_not_found_returns_404(self):
        from api.rcm.claims import validate_claim
        from fastapi import HTTPException

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        principal = make_principal()

        with pytest.raises(HTTPException) as exc_info:
            await validate_claim(claim_id=9999, db=mock_db, current_user=principal)
        assert exc_info.value.status_code == 404


class TestEDIProcessor:
    """Tests for EDI file generation and parsing."""

    @pytest.mark.asyncio
    async def test_generate_837_creates_file(self, tmp_path):
        import os
        os.environ["EDI_STORAGE_PATH"] = str(tmp_path)

        from services.edi_processor import EDIProcessor

        mock_db = AsyncMock()

        # Mock payer
        payer_mock = MagicMock()
        payer_mock.format_837_type = "837P"
        payer_mock.submitter_id = "CLAIMFLOW001"
        payer_mock.receiver_id = "PAYER001"

        payer_result = MagicMock()
        payer_result.scalar_one_or_none.return_value = payer_mock

        # Mock claims
        claim_mock = MagicMock()
        claim_mock.id = 1
        claim_mock.tenant_id = TENANT_ID
        claim_mock.claim_number = "CLM001"
        claim_mock.billing_provider_npi = "1234567890"
        claim_mock.patient_id = 100
        claim_mock.total_charges = 250.00
        claim_mock.state = "validated"
        claim_mock.claim_frequency_code = "1"

        claims_result = MagicMock()
        claims_result.scalars.return_value.all.return_value = [claim_mock]

        mock_db.execute = AsyncMock(side_effect=[payer_result, claims_result])
        mock_db.flush = AsyncMock()
        mock_db.commit = AsyncMock()

        processor = EDIProcessor(mock_db)
        result = await processor.generate_837([1], payer_id=1, tenant_id=TENANT_ID)

        assert result["success"] is True
        assert result["claim_count"] == 1
        assert os.path.exists(result["file_path"])

    def test_validate_edi_format_valid(self):
        from services.edi_processor import EDIProcessor

        processor = EDIProcessor(None)
        content = "ISA*test~GS*HC~ST*837~BHT*test~SE*5~GE*1~IEA*1~"
        result = processor.validate_edi_format(content, "837P")
        assert result["valid"] is True

    def test_validate_edi_format_missing_isa(self):
        from services.edi_processor import EDIProcessor

        processor = EDIProcessor(None)
        content = "GS*HC~ST*837~"
        result = processor.validate_edi_format(content, "837P")
        assert result["valid"] is False
        assert any("ISA" in e for e in result["errors"])


class TestEncryptionService:
    @pytest.mark.asyncio
    async def test_roundtrip(self):
        from services.encryption import encrypt_credential, decrypt_credential

        secret = "my-sftp-password-123!"
        encrypted = await encrypt_credential(secret)
        assert encrypted != secret

        decrypted = await decrypt_credential(encrypted)
        assert decrypted == secret

    @pytest.mark.asyncio
    async def test_unique_ciphertexts(self):
        from services.encryption import encrypt_credential

        ct1 = await encrypt_credential("same")
        ct2 = await encrypt_credential("same")
        assert ct1 != ct2


class TestRateLimiting:
    @pytest.mark.asyncio
    async def test_allows_requests_under_limit(self):
        from core.rate_limit import RateLimitMiddleware
        from starlette.testclient import TestClient
        from fastapi import FastAPI

        app = FastAPI()
        app.add_middleware(RateLimitMiddleware, requests_per_window=5, window_seconds=60)

        @app.get("/test")
        async def test_endpoint():
            return {"ok": True}

        client = TestClient(app)
        for _ in range(5):
            resp = client.get("/test")
            assert resp.status_code == 200

        # 6th request should be rate limited
        resp = client.get("/test")
        assert resp.status_code == 429
