"""
Tests for core.rate_limit middleware bucket keying.

Closes v10 NEW-C1: rate-limit must NOT bucket on caller-supplied X-Tenant-ID.
The bucket key must depend only on the client IP so an unauthenticated caller
cannot mint a fresh quota by rotating headers.
"""

import importlib

import pytest


@pytest.fixture
def rl_module(monkeypatch):
    monkeypatch.delenv("REDIS_URL", raising=False)  # use in-memory store
    import core.rate_limit as rl
    importlib.reload(rl)
    return rl


def _make_request(rl, ip="1.2.3.4", x_tenant=None, x_forwarded=None):
    """Build the smallest object the middleware\'s key fn needs."""
    headers: dict = {}
    if x_tenant is not None:
        headers["X-Tenant-ID"] = x_tenant
    if x_forwarded is not None:
        headers["X-Forwarded-For"] = x_forwarded

    class _Req:
        def __init__(self) -> None:
            self.headers = headers

            class _Client:
                host = ip

            self.client = _Client()
    return _Req()


def test_bucket_key_ignores_x_tenant_id(rl_module):
    mw = rl_module.RateLimitMiddleware(app=lambda *a, **k: None)
    same_ip_req_a = _make_request(rl_module, ip="9.9.9.9", x_tenant="aaaa")
    same_ip_req_b = _make_request(rl_module, ip="9.9.9.9", x_tenant="bbbb")
    # Different X-Tenant-ID, same IP → must hash to the same bucket key.
    assert mw._bucket_key(same_ip_req_a) == mw._bucket_key(same_ip_req_b)


def test_bucket_key_uses_x_forwarded_for_first_hop(rl_module):
    mw = rl_module.RateLimitMiddleware(app=lambda *a, **k: None)
    req = _make_request(rl_module, ip="10.0.0.1", x_forwarded="203.0.113.5, 10.0.0.1")
    assert mw._bucket_key(req) == "rl:ip:203.0.113.5"


def test_in_memory_store_enforces_limit(rl_module):
    store = rl_module._InMemoryStore()
    for _ in range(3):
        allowed, _ = store.hit("test", window=60, limit=3)
        assert allowed
    # 4th call within the window must be rejected.
    allowed, remaining = store.hit("test", window=60, limit=3)
    assert allowed is False
    assert remaining == 0
