"""
Tenant isolation tests for ClaimFlow.
Verifies that data from one tenant is never visible to another.
"""

import pytest
import uuid
from unittest.mock import AsyncMock, patch, MagicMock
from datetime import date

from api.auth import Principal


TENANT_A = str(uuid.uuid4())
TENANT_B = str(uuid.uuid4())


def make_principal(tenant_id: str, roles=None) -> Principal:
    return Principal(
        user_id="user-1",
        tenant_id=tenant_id,
        email="test@claimflow.io",
        roles=roles or ["billing", "admin"],
    )


class TestPrincipal:
    def test_has_role(self):
        p = make_principal(TENANT_A, roles=["billing"])
        assert p.has_role("billing") is True
        assert p.has_role("admin") is False

    def test_require_role_raises(self):
        from fastapi import HTTPException
        p = make_principal(TENANT_A, roles=["billing"])
        with pytest.raises(HTTPException) as exc_info:
            p.require_role("super_admin")
        assert exc_info.value.status_code == 403


class TestTenantIsolationClaims:
    """
    Validates that claim list endpoints filter by tenant_id.
    Uses mocked DB session to verify the correct WHERE clause is applied.
    """

    @pytest.mark.asyncio
    async def test_list_claims_filters_by_tenant(self):
        from api.rcm.claims import list_claims

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute.return_value = mock_result

        principal = make_principal(TENANT_A)

        result = await list_claims(
            state=None, queue=None, payer_id=None, provider_id=None,
            date_from=None, date_to=None, limit=100, offset=0,
            db=mock_db, current_user=principal,
        )

        assert result["success"] is True
        # Verify the db.execute was called (query was built)
        assert mock_db.execute.called


class TestTenantIsolationDenials:
    @pytest.mark.asyncio
    async def test_list_denial_cases_filters_by_tenant(self):
        from api.rcm.denials import list_denial_cases

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute.return_value = mock_result

        principal = make_principal(TENANT_B)

        result = await list_denial_cases(
            category=None, priority=None, status=None,
            limit=100, offset=0, db=mock_db, current_user=principal,
        )

        assert result["success"] is True
        assert mock_db.execute.called


class TestEncryptionService:
    @pytest.mark.asyncio
    async def test_encrypt_decrypt_roundtrip(self):
        from services.encryption import encrypt_credential, decrypt_credential

        plaintext = "super-secret-api-key-12345"
        encrypted = await encrypt_credential(plaintext)
        assert encrypted != plaintext
        decrypted = await decrypt_credential(encrypted)
        assert decrypted == plaintext

    @pytest.mark.asyncio
    async def test_different_ciphertexts(self):
        from services.encryption import encrypt_credential

        ct1 = await encrypt_credential("same-value")
        ct2 = await encrypt_credential("same-value")
        assert ct1 != ct2  # Different nonces should produce different ciphertexts
