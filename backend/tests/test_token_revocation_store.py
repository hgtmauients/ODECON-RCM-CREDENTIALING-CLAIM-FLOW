import pytest

import core.token_revocation as token_revocation

pytestmark = pytest.mark.security


@pytest.mark.asyncio
async def test_revoke_and_check_jti_in_memory(monkeypatch):
    monkeypatch.setattr(token_revocation, "_store", None)
    monkeypatch.setattr(token_revocation, "REDIS_URL", "")
    monkeypatch.setattr(token_revocation, "ENV", "development")

    payload = {"jti": "abc123", "iat": 1000, "exp": 2000}
    assert await token_revocation.is_token_revoked(tenant_id="t1", user_id="u1", payload=payload) is False
    await token_revocation.revoke_token_jti("abc123", exp=2000)
    assert await token_revocation.is_token_revoked(tenant_id="t1", user_id="u1", payload=payload) is True


@pytest.mark.asyncio
async def test_revoke_user_tokens_blocks_older_iat(monkeypatch):
    monkeypatch.setattr(token_revocation, "_store", None)
    monkeypatch.setattr(token_revocation, "REDIS_URL", "")
    monkeypatch.setattr(token_revocation, "ENV", "development")

    await token_revocation.revoke_user_tokens(tenant_id="t1", user_id="u1", issued_before_ts=1500)
    assert await token_revocation.is_token_revoked(
        tenant_id="t1",
        user_id="u1",
        payload={"iat": 1400, "jti": "not-revoked"},
    ) is True
    assert await token_revocation.is_token_revoked(
        tenant_id="t1",
        user_id="u1",
        payload={"iat": 1600, "jti": "not-revoked"},
    ) is False
