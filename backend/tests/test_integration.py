"""
ClaimFlow - Integration tests for the full claim lifecycle.
Tests: create → validate → submit → 277 ack → 835 payment post
"""

import pytest
import uuid
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import date, datetime
from fastapi import HTTPException

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
        exists_result = MagicMock()
        exists_result.scalar_one_or_none.return_value = 1
        mock_db.execute = AsyncMock(return_value=exists_result)
        mock_db.flush = AsyncMock()
        mock_db.commit = AsyncMock()
        mock_db.refresh = AsyncMock()
        mock_db.add = MagicMock()

        principal = make_principal()

        claim_data = {
            "service_date_from": "2026-01-15",
            "total_charges": 150.00,
            "payer_id": 1,
        }

        result = await create_claim(
            claim_data=claim_data,
            request=MagicMock(),
            db=mock_db,
            current_user=principal,
        )
        assert result["success"] is True
        assert "claim_number" in result["data"]

        # Verify db.add was called with a Claim that has tenant_id
        added_obj = mock_db.add.call_args_list[0][0][0]
        assert str(added_obj.tenant_id) == TENANT_ID

    @pytest.mark.asyncio
    async def test_create_claim_rejects_foreign_payer_id(self):
        from api.rcm.claims import create_claim

        mock_db = AsyncMock()
        missing_result = MagicMock()
        missing_result.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(return_value=missing_result)

        principal = make_principal()
        claim_data = {
            "service_date_from": "2026-01-15",
            "total_charges": 150.00,
            "payer_id": 999,
        }

        with pytest.raises(HTTPException) as exc_info:
            await create_claim(
                claim_data=claim_data,
                request=MagicMock(),
                db=mock_db,
                current_user=principal,
            )
        assert exc_info.value.status_code == 422
        assert "payer_id 999 not in tenant" in str(exc_info.value.detail)

    @pytest.mark.asyncio
    async def test_validate_claim_not_found_returns_404(self):
        from api.rcm.claims import validate_claim

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        principal = make_principal()

        with pytest.raises(HTTPException) as exc_info:
            await validate_claim(claim_id=9999, db=mock_db, current_user=principal)
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_validate_claim_passes_tenant_to_rules_engine(self):
        from api.rcm.claims import validate_claim

        mock_db = AsyncMock()
        claim_row = MagicMock()
        claim_row.state = "draft"
        claim_result = MagicMock()
        claim_result.scalar_one_or_none.return_value = claim_row
        mock_db.execute.return_value = claim_result
        mock_db.commit = AsyncMock()

        principal = make_principal()

        with patch("api.rcm.claims.RulesEngine") as rules_engine_cls:
            rules_engine_instance = rules_engine_cls.return_value
            rules_engine_instance.validate_claim = AsyncMock(return_value={"passed": True, "errors": []})

            resp = await validate_claim(claim_id=123, db=mock_db, current_user=principal)

        assert resp["success"] is True
        rules_engine_instance.validate_claim.assert_awaited_once_with(123, tenant_id=TENANT_ID)

    @pytest.mark.security
    @pytest.mark.asyncio
    async def test_batch_validate_uses_non_committing_rules_engine_path(self):
        from api.rcm.claims import batch_validate_claims_alias

        mock_db = MagicMock()
        claim_row = MagicMock()
        claim_row.id = 1
        claim_row.tenant_id = TENANT_ID
        claim_result = MagicMock()
        claim_result.scalar_one_or_none.return_value = claim_row
        mock_db.execute = AsyncMock(return_value=claim_result)
        nested_tx = MagicMock()
        nested_tx.__aenter__ = AsyncMock(return_value=None)
        nested_tx.__aexit__ = AsyncMock(return_value=False)
        mock_db.begin_nested = MagicMock(return_value=nested_tx)
        mock_db.add = MagicMock()
        mock_db.commit = AsyncMock()
        mock_db.rollback = AsyncMock()

        principal = make_principal()
        with patch("api.rcm.claims.RulesEngine") as rules_engine_cls:
            rules_engine_instance = rules_engine_cls.return_value
            rules_engine_instance.validate_claim = AsyncMock(return_value={"passed": True, "errors": [], "rules_matched": 1})

            resp = await batch_validate_claims_alias(
                body={"claim_ids": [1]},
                request=MagicMock(),
                db=mock_db,
                current_user=principal,
            )

        assert resp["success"] is True
        rules_engine_instance.validate_claim.assert_awaited_once_with(1, tenant_id=TENANT_ID, auto_commit=False)
        mock_db.rollback.assert_not_called()

    @pytest.mark.asyncio
    async def test_submit_batch_rejects_already_submitted_claim(self):
        from api.rcm.claims import submit_claim_batch

        mock_db = AsyncMock()
        claim = MagicMock()
        claim.id = 1
        claim.state = "submitted"
        claim.payer_id = 10
        claim.batch_id = None
        claims_result = MagicMock()
        claims_result.scalars.return_value.all.return_value = [claim]
        mock_db.execute = AsyncMock(return_value=claims_result)

        principal = make_principal()
        with pytest.raises(HTTPException) as exc_info:
            await submit_claim_batch(
                batch={"claim_ids": [1], "payer_id": 10},
                request=MagicMock(),
                db=mock_db,
                current_user=principal,
            )
        assert exc_info.value.status_code == 409
        assert "already in state" in str(exc_info.value.detail)

    @pytest.mark.asyncio
    async def test_submit_batch_reuses_transmitted_batch_idempotently(self):
        from api.rcm.claims import submit_claim_batch

        mock_db = AsyncMock()

        claim = MagicMock()
        claim.id = 1
        claim.state = "ready_to_submit"
        claim.payer_id = 10
        claim.batch_id = "batch_existing"
        claims_result = MagicMock()
        claims_result.scalars.return_value.all.return_value = [claim]

        payer_exists_result = MagicMock()
        payer_exists_result.scalar_one_or_none.return_value = 10

        existing_file = MagicMock()
        existing_file.id = 77
        existing_file.status = "transmitted"
        existing_file_result = MagicMock()
        existing_file_result.scalar_one_or_none.return_value = existing_file

        mock_db.execute = AsyncMock(side_effect=[claims_result, payer_exists_result, existing_file_result])

        principal = make_principal()
        with patch("api.rcm.claims.EDIProcessor") as edi_cls:
            resp = await submit_claim_batch(
                batch={"claim_ids": [1], "payer_id": 10},
                request=MagicMock(),
                db=mock_db,
                current_user=principal,
            )
            edi_cls.assert_not_called()

        assert resp["success"] is True
        assert resp["data"]["already_transmitted"] is True


class TestEnrollmentTransitions:
    @pytest.mark.asyncio
    async def test_enrollment_update_rejects_invalid_status_transition(self):
        from api.rcm.payer_enrollment import update_payer_credentialing_case, EnrollmentCaseUpdate

        mock_db = AsyncMock()
        case = MagicMock()
        case.status = "draft"
        result = MagicMock()
        result.scalar_one_or_none.return_value = case
        mock_db.execute = AsyncMock(return_value=result)

        principal = Principal(
            user_id="u1",
            tenant_id=TENANT_ID,
            email="cred@claimflow.io",
            roles=["credentialing"],
        )

        with pytest.raises(HTTPException) as exc_info:
            await update_payer_credentialing_case(
                case_id=1,
                updates=EnrollmentCaseUpdate(status="approved"),
                request=MagicMock(),
                db=mock_db,
                current_user=principal,
            )
        assert exc_info.value.status_code == 409
        assert "Invalid enrollment status transition" in str(exc_info.value.detail)


class TestDenialTransitions:
    @pytest.mark.asyncio
    async def test_denial_update_rejects_invalid_status_transition(self):
        from api.rcm.denials import update_denial_case

        mock_db = AsyncMock()
        denial = MagicMock()
        denial.id = 1
        denial.claim_id = 11
        denial.status = "new"
        denial_result = MagicMock()
        denial_result.scalar_one_or_none.return_value = denial
        # Claim lookup should not be reached on invalid transition
        mock_db.execute = AsyncMock(return_value=denial_result)

        principal = make_principal()
        with pytest.raises(HTTPException) as exc_info:
            await update_denial_case(
                denial_id=1,
                updates={"status": "won"},
                request=MagicMock(),
                db=mock_db,
                current_user=principal,
            )
        assert exc_info.value.status_code == 409
        assert "Invalid denial status transition" in str(exc_info.value.detail)


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

        lines_result = MagicMock()
        lines_result.scalars.return_value.all.return_value = []
        dx_result = MagicMock()
        dx_result.scalars.return_value.all.return_value = []
        patient_result = MagicMock()
        patient_result.scalar_one_or_none.return_value = None
        tenant_result = MagicMock()
        tenant_result.scalar_one_or_none.return_value = None

        mock_db.execute = AsyncMock(side_effect=[payer_result, claims_result, lines_result, dx_result, patient_result, tenant_result])
        mock_db.flush = AsyncMock()
        mock_db.commit = AsyncMock()
        mock_db.add = MagicMock()

        processor = EDIProcessor(mock_db)
        result = await processor.generate_837([1], payer_id=1, tenant_id=TENANT_ID)

        assert result["success"] is True
        assert result["claim_count"] == 1
        assert os.path.exists(result["file_path"])

    @pytest.mark.asyncio
    async def test_generate_837_auto_commit_false_uses_flush(self, tmp_path):
        import os
        os.environ["EDI_STORAGE_PATH"] = str(tmp_path)

        from services.edi_processor import EDIProcessor

        mock_db = AsyncMock()

        payer_mock = MagicMock()
        payer_mock.format_837_type = "837P"
        payer_mock.submitter_id = "CLAIMFLOW001"
        payer_mock.receiver_id = "PAYER001"
        payer_result = MagicMock()
        payer_result.scalar_one_or_none.return_value = payer_mock

        claim_mock = MagicMock()
        claim_mock.id = 1
        claim_mock.tenant_id = TENANT_ID
        claim_mock.claim_number = "CLM002"
        claim_mock.billing_provider_npi = "1234567890"
        claim_mock.patient_id = None
        claim_mock.total_charges = 250.00
        claim_mock.state = "validated"
        claim_mock.claim_frequency_code = "1"
        claims_result = MagicMock()
        claims_result.scalars.return_value.all.return_value = [claim_mock]

        tenant_mock = MagicMock()
        tenant_mock.name = "Tenant"
        tenant_mock.npi = "1234567890"
        tenant_mock.tax_id = "999999999"
        tenant_mock.address_line_1 = "123 Main"
        tenant_mock.address_line_2 = ""
        tenant_mock.city = "Honolulu"
        tenant_mock.state = "HI"
        tenant_mock.zip_code = "96801"
        tenant_mock.phone = "8085551234"
        tenant_result = MagicMock()
        tenant_result.scalar_one_or_none.return_value = tenant_mock

        lines_result = MagicMock()
        lines_result.scalars.return_value.all.return_value = []
        dx_result = MagicMock()
        dx_result.scalars.return_value.all.return_value = []

        empty_originals_result = MagicMock()
        empty_originals_result.all.return_value = []
        mock_db.execute = AsyncMock(side_effect=[payer_result, claims_result, empty_originals_result, lines_result, dx_result, tenant_result])
        mock_db.flush = AsyncMock()
        mock_db.commit = AsyncMock()
        mock_db.add = MagicMock()

        processor = EDIProcessor(mock_db)
        result = await processor.generate_837([1], payer_id=1, tenant_id=TENANT_ID, auto_commit=False)

        assert result["success"] is True
        mock_db.flush.assert_awaited()
        mock_db.commit.assert_not_called()

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

    @pytest.mark.asyncio
    async def test_parse_835_with_record_duplicate_skips_processing(self):
        from services.edi_processor import EDIProcessor

        mock_db = AsyncMock()
        dup_row = MagicMock()
        dup_row.id = 77
        dup_result = MagicMock()
        dup_result.scalars.return_value.first.return_value = dup_row
        mock_db.execute = AsyncMock(return_value=dup_result)
        mock_db.commit = AsyncMock()

        processor = EDIProcessor(mock_db)
        processor._read_file_async = AsyncMock(return_value="ISA*00*...~ST*835*0001~SE*2*0001~")

        edi_file = MagicMock()
        edi_file.id = 99
        edi_file.tenant_id = TENANT_ID
        edi_file.file_hash = None

        result = await processor.parse_835_with_record("/tmp/upload.835", edi_file)

        assert result["success"] is True
        assert result["is_duplicate"] is True
        assert result["edi_file_id"] == 77
        assert result["duplicate_upload_id"] == 99
        assert edi_file.status == "duplicate"
        mock_db.commit.assert_awaited_once()

    @pytest.mark.security
    @pytest.mark.asyncio
    async def test_parse_835_requires_tenant_id(self):
        from services.edi_processor import EDIProcessor

        mock_db = AsyncMock()
        processor = EDIProcessor(mock_db)

        with pytest.raises(ValueError, match="tenant_id is required to parse 835"):
            await processor.parse_835("/tmp/inbound.835", tenant_id=None)

    @pytest.mark.security
    @pytest.mark.asyncio
    async def test_generate_270_requires_tenant_id(self):
        from services.edi_processor import EDIProcessor

        mock_db = AsyncMock()
        processor = EDIProcessor(mock_db)

        with pytest.raises(ValueError, match="tenant_id is required to generate 270"):
            await processor.generate_270(patient_id=1, payer_id=1, tenant_id=None)

    @pytest.mark.security
    @pytest.mark.asyncio
    async def test_get_submission_batch_status_requires_tenant_id(self):
        from services.edi_processor import EDIProcessor

        mock_db = AsyncMock()
        processor = EDIProcessor(mock_db)

        with pytest.raises(ValueError, match="tenant_id is required to get submission batch status"):
            await processor.get_submission_batch_status(batch_id="batch-1", tenant_id=None)

    @pytest.mark.security
    @pytest.mark.asyncio
    async def test_parse_271_requires_tenant_id(self):
        from services.edi_processor import EDIProcessor

        mock_db = AsyncMock()
        processor = EDIProcessor(mock_db)

        with pytest.raises(ValueError, match="tenant_id is required to parse 271"):
            await processor.parse_271("/tmp/inbound.271", tenant_id=None)


class TestClearinghousePolling:
    @pytest.mark.asyncio
    async def test_poll_for_277_files_returns_local_paths(self):
        from services.clearinghouse_transport import ClearinghouseService

        mock_db = AsyncMock()
        conn = MagicMock()
        conn.connection_type = "sftp"
        conn_result = MagicMock()
        conn_result.scalar_one_or_none.return_value = conn
        mock_db.execute = AsyncMock(return_value=conn_result)

        service = ClearinghouseService(mock_db)
        service.sftp.download_files = AsyncMock(
            return_value=[{"local_path": "/tmp/ack1.277"}, {"local_path": "/tmp/ack2.277"}]
        )

        files = await service.poll_for_277_files(payer_id=42, tenant_id=TENANT_ID)

        assert files == ["/tmp/ack1.277", "/tmp/ack2.277"]
        service.sftp.download_files.assert_awaited_once()


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
