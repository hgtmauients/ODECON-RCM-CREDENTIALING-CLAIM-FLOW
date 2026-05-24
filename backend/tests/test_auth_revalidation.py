import uuid
from types import SimpleNamespace

import jwt
import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

from api.auth import JWT_ALGORITHM, JWT_SECRET, get_current_user

pytestmark = pytest.mark.security


class _FakeResult:
    def __init__(self, row):
        self._row = row

    def scalar_one_or_none(self):
        return self._row


class _FakeDB:
    def __init__(self, row):
        self._row = row

    async def execute(self, _query):
        return _FakeResult(self._row)


def _make_token(*, sub: str, tenant_id: str, roles: list[str]) -> str:
    payload = {
        "sub": sub,
        "email": "user@example.com",
        "tenant_id": tenant_id,
        "roles": roles,
        "aud": "claimflow",
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


@pytest.mark.asyncio
async def test_get_current_user_rejects_inactive_database_user():
    user_id = str(uuid.uuid4())
    tenant_id = str(uuid.uuid4())
    token = _make_token(sub=user_id, tenant_id=tenant_id, roles=["admin"])

    request = SimpleNamespace(headers={}, client=SimpleNamespace(host="127.0.0.1"))
    creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)
    db = _FakeDB(SimpleNamespace(is_active=False, roles=["admin"]))

    with pytest.raises(HTTPException) as exc:
        await get_current_user(request=request, credentials=creds, db=db)
    assert exc.value.status_code == 401
    assert exc.value.detail == "Invalid token"


@pytest.mark.asyncio
async def test_get_current_user_applies_database_roles_for_tenant_override():
    user_id = str(uuid.uuid4())
    token_tenant = str(uuid.uuid4())
    requested_tenant = str(uuid.uuid4())
    token = _make_token(sub=user_id, tenant_id=token_tenant, roles=["super_admin"])

    # JWT has super_admin, but DB row now only has admin.
    db = _FakeDB(SimpleNamespace(is_active=True, roles=["admin"]))
    request = SimpleNamespace(
        headers={"X-Tenant-ID": requested_tenant},
        client=SimpleNamespace(host="127.0.0.1"),
    )
    creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)

    with pytest.raises(HTTPException) as exc:
        await get_current_user(request=request, credentials=creds, db=db)
    assert exc.value.status_code == 403
    assert "super_admin" in exc.value.detail
