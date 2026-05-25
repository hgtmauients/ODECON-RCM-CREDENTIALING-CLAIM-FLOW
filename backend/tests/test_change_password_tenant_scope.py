import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from api.auth import Principal
from api.dev_login import ChangePasswordRequest, change_password

pytestmark = pytest.mark.security


@pytest.mark.asyncio
async def test_change_password_rejects_when_user_not_in_principal_tenant():
    principal = Principal(
        user_id=str(uuid.uuid4()),
        tenant_id=str(uuid.uuid4()),
        email="user@example.com",
        roles=["billing"],
    )
    db = MagicMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = None
    db.execute = AsyncMock(return_value=result)

    payload = ChangePasswordRequest(current_password="old-pass-123", new_password="new-pass-123")
    with pytest.raises(HTTPException) as exc:
        await change_password(payload=payload, request=MagicMock(), db=db, current_user=principal)
    assert exc.value.status_code == 401
    assert "Invalid credentials" in exc.value.detail


@pytest.mark.asyncio
async def test_change_password_uses_tenant_scoped_lookup_and_succeeds():
    principal = Principal(
        user_id=str(uuid.uuid4()),
        tenant_id=str(uuid.uuid4()),
        email="user@example.com",
        roles=["billing"],
    )
    user = SimpleNamespace(
        id=principal.user_id,
        is_active=True,
        password_hash="hashed-old",
    )
    result = MagicMock()
    result.scalar_one_or_none.return_value = user
    db = MagicMock()
    db.execute = AsyncMock(return_value=result)
    db.add = MagicMock()
    db.commit = AsyncMock()

    payload = ChangePasswordRequest(current_password="old-pass-123", new_password="new-pass-456")
    with patch("api.dev_login.verify_password", return_value=True), patch("api.dev_login.hash_password", return_value="hashed-new"):
        out = await change_password(payload=payload, request=MagicMock(), db=db, current_user=principal)
    assert out["success"] is True
    assert user.password_hash == "hashed-new"
