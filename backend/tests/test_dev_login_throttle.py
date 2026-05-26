import pytest
from fastapi import HTTPException
from fastapi import Response
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import api.dev_login as dev_login

pytestmark = pytest.mark.security


@pytest.mark.asyncio
async def test_login_throttle_blocks_after_limit(monkeypatch):
    monkeypatch.setattr(dev_login, "LOGIN_ATTEMPT_LIMIT", 3)
    monkeypatch.setattr(dev_login, "LOGIN_ATTEMPT_WINDOW_SECONDS", 900)
    monkeypatch.setattr(dev_login, "REDIS_URL", "")
    monkeypatch.setattr(dev_login, "_redis_client", None)
    dev_login._failed_login_attempts.clear()

    for _ in range(3):
        await dev_login._record_failed_login(email="user@example.com", client_ip="1.2.3.4")

    with pytest.raises(HTTPException) as exc:
        await dev_login._enforce_login_throttle(email="user@example.com", client_ip="1.2.3.4")
    assert exc.value.status_code == 429


@pytest.mark.asyncio
async def test_login_throttle_clears_after_success(monkeypatch):
    monkeypatch.setattr(dev_login, "LOGIN_ATTEMPT_LIMIT", 3)
    monkeypatch.setattr(dev_login, "REDIS_URL", "")
    monkeypatch.setattr(dev_login, "_redis_client", None)
    dev_login._failed_login_attempts.clear()
    await dev_login._record_failed_login(email="user@example.com", client_ip="1.2.3.4")
    await dev_login._clear_failed_login(email="user@example.com", client_ip="1.2.3.4")

    # Should not raise once attempts are cleared.
    await dev_login._enforce_login_throttle(email="user@example.com", client_ip="1.2.3.4")


def test_login_body_token_is_opt_in(monkeypatch):
    monkeypatch.delenv("AUTH_LOGIN_INCLUDE_TOKEN", raising=False)
    assert dev_login._include_token_in_login_response() is False

    monkeypatch.setenv("AUTH_LOGIN_INCLUDE_TOKEN", "true")
    assert dev_login._include_token_in_login_response() is True


@pytest.mark.asyncio
async def test_login_response_omits_access_token_by_default(monkeypatch):
    monkeypatch.delenv("AUTH_LOGIN_INCLUDE_TOKEN", raising=False)
    monkeypatch.setattr(dev_login, "REDIS_URL", "")
    monkeypatch.setattr(dev_login, "_redis_client", None)
    monkeypatch.setattr(dev_login, "verify_password", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(dev_login, "needs_rehash", lambda *_args, **_kwargs: False)

    mock_db = AsyncMock()
    db_result = MagicMock()
    user = SimpleNamespace(
        id="00000000-0000-0000-0000-000000000111",
        email="user@example.com",
        tenant_id="00000000-0000-0000-0000-000000000222",
        roles=["admin"],
        full_name="Test User",
        password_hash="hash",
        last_login_at=None,
    )
    db_result.scalars.return_value.all.return_value = [user]
    mock_db.execute.return_value = db_result
    mock_db.commit = AsyncMock()

    req = dev_login.LoginRequest(email="user@example.com", password="pw")
    request = SimpleNamespace(client=SimpleNamespace(host="1.2.3.4"))
    response = Response()

    payload = await dev_login.login(req=req, request=request, response=response, db=mock_db)

    assert "access_token" not in payload
    assert payload["user"]["email"] == "user@example.com"
