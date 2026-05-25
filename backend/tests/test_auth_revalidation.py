import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import jwt
import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

import api.auth as auth_module
from api.auth import JWT_ALGORITHM, JWT_SECRET, get_current_user

pytestmark = pytest.mark.security


class _FakeResult:
    def __init__(self, row):
        self._row = row

    def scalar_one_or_none(self):
        return self._row

    def scalars(self):
        class _FakeScalars:
            def __init__(self, row):
                self._row = row

            def all(self):
                if self._row is None:
                    return []
                if isinstance(self._row, list):
                    return self._row
                return [self._row]

        return _FakeScalars(self._row)


class _FakeDB:
    def __init__(self, rows):
        if isinstance(rows, list):
            self._rows = rows
        else:
            self._rows = [rows]
        self._idx = 0

    async def execute(self, _query):
        row = self._rows[min(self._idx, len(self._rows) - 1)]
        self._idx += 1
        return _FakeResult(row)


def _make_token(*, sub: str, tenant_id: str, roles: list[str], iat: datetime | None = None) -> str:
    issued_at = iat or datetime.now(timezone.utc)
    payload = {
        "sub": sub,
        "email": "user@example.com",
        "tenant_id": tenant_id,
        "roles": roles,
        "aud": "claimflow",
        "iat": issued_at,
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


@pytest.mark.asyncio
async def test_get_current_user_rejects_inactive_database_user():
    user_id = str(uuid.uuid4())
    tenant_id = str(uuid.uuid4())
    token = _make_token(sub=user_id, tenant_id=tenant_id, roles=["admin"])

    request = SimpleNamespace(headers={}, client=SimpleNamespace(host="127.0.0.1"))
    creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)
    db = _FakeDB([SimpleNamespace(id=uuid.uuid4()), SimpleNamespace(is_active=False, roles=["admin"])])

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
    db = _FakeDB([SimpleNamespace(id=uuid.uuid4()), SimpleNamespace(is_active=True, roles=["admin"])])
    request = SimpleNamespace(
        headers={"X-Tenant-ID": requested_tenant},
        client=SimpleNamespace(host="127.0.0.1"),
    )
    creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)

    with pytest.raises(HTTPException) as exc:
        await get_current_user(request=request, credentials=creds, db=db)
    assert exc.value.status_code == 403
    assert "super_admin" in exc.value.detail


@pytest.mark.asyncio
async def test_get_current_user_rejects_inactive_tenant():
    user_id = str(uuid.uuid4())
    tenant_id = str(uuid.uuid4())
    token = _make_token(sub=user_id, tenant_id=tenant_id, roles=["admin"])

    request = SimpleNamespace(headers={}, client=SimpleNamespace(host="127.0.0.1"))
    creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)
    db = _FakeDB([None])

    with pytest.raises(HTTPException) as exc:
        await get_current_user(request=request, credentials=creds, db=db)
    assert exc.value.status_code == 403
    assert exc.value.detail == "Tenant is inactive"


@pytest.mark.asyncio
async def test_get_current_user_non_uuid_subject_requires_db_mapping_in_production(monkeypatch):
    tenant_id = str(uuid.uuid4())
    token = _make_token(sub="oidc|abc123", tenant_id=tenant_id, roles=["super_admin"])

    request = SimpleNamespace(headers={}, client=SimpleNamespace(host="127.0.0.1"))
    creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)
    db = _FakeDB([SimpleNamespace(id=uuid.uuid4()), None])
    monkeypatch.setattr(auth_module, "ENV", "production")

    with pytest.raises(HTTPException) as exc:
        await get_current_user(request=request, credentials=creds, db=db)
    assert exc.value.status_code == 401
    assert exc.value.detail == "Invalid token"


@pytest.mark.asyncio
async def test_get_current_user_non_uuid_subject_requires_db_mapping_in_development(monkeypatch):
    tenant_id = str(uuid.uuid4())
    token = _make_token(sub="oidc|abc123", tenant_id=tenant_id, roles=["super_admin"])

    request = SimpleNamespace(headers={}, client=SimpleNamespace(host="127.0.0.1"))
    creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)
    db = _FakeDB([SimpleNamespace(id=uuid.uuid4()), None])
    monkeypatch.setattr(auth_module, "ENV", "development")

    with pytest.raises(HTTPException) as exc:
        await get_current_user(request=request, credentials=creds, db=db)
    assert exc.value.status_code == 401
    assert exc.value.detail == "Invalid token"


@pytest.mark.asyncio
async def test_super_admin_override_rejects_invalid_target_tenant_uuid():
    user_id = str(uuid.uuid4())
    token_tenant = str(uuid.uuid4())
    token = _make_token(sub=user_id, tenant_id=token_tenant, roles=["super_admin"])

    request = SimpleNamespace(
        headers={"X-Tenant-ID": "not-a-uuid"},
        client=SimpleNamespace(host="127.0.0.1"),
    )
    creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)
    db = _FakeDB([
        SimpleNamespace(id=uuid.uuid4()),      # token tenant active check
        SimpleNamespace(is_active=True, roles=["super_admin"]),  # user revalidation
    ])

    with pytest.raises(HTTPException) as exc:
        await get_current_user(request=request, credentials=creds, db=db)
    assert exc.value.status_code == 403
    assert "valid tenant UUID" in exc.value.detail


@pytest.mark.asyncio
async def test_super_admin_override_rejects_inactive_target_tenant():
    user_id = str(uuid.uuid4())
    token_tenant = str(uuid.uuid4())
    requested_tenant = str(uuid.uuid4())
    token = _make_token(sub=user_id, tenant_id=token_tenant, roles=["super_admin"])

    request = SimpleNamespace(
        headers={"X-Tenant-ID": requested_tenant},
        client=SimpleNamespace(host="127.0.0.1"),
    )
    creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)
    db = _FakeDB([
        SimpleNamespace(id=uuid.uuid4()),      # token tenant active check
        SimpleNamespace(is_active=True, roles=["super_admin"]),  # user revalidation
        None,  # requested tenant active check fails
    ])

    with pytest.raises(HTTPException) as exc:
        await get_current_user(request=request, credentials=creds, db=db)
    assert exc.value.status_code == 403
    assert "inactive or missing" in exc.value.detail


