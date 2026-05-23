import pytest
from httpx import ASGITransport, AsyncClient
from starlette.requests import Request

import adapter.main as adapter

app = adapter.app


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture(autouse=True)
def reset_adapter_globals(monkeypatch):
    monkeypatch.setattr(adapter, "REQUIRE_AUTH", False)
    monkeypatch.setattr(adapter, "ADAPTER_API_KEY", "")
    monkeypatch.setattr(adapter, "ADAPTER_SHARED_SECRET", "")
    monkeypatch.setattr(adapter, "TRUSTED_PROXY_CIDRS", "")
    monkeypatch.setattr(adapter, "_TRUSTED_PROXY_NETWORKS", [])
    monkeypatch.setattr(adapter, "LICENSE_UPSTREAM_URL", "")
    monkeypatch.setattr(adapter, "BACKGROUND_UPSTREAM_URL", "")
    monkeypatch.setattr(adapter, "MAX_RETRIES", 2)
    monkeypatch.setattr(adapter, "RETRY_BACKOFF_SECONDS", 0)
    monkeypatch.setattr(adapter, "RATE_LIMIT_REQUESTS", 120)
    monkeypatch.setattr(adapter, "RATE_LIMIT_WINDOW_SECONDS", 60)
    adapter._RATE_LIMIT_BUCKETS.clear()


@pytest.mark.asyncio
async def test_health_endpoint_exposes_modes():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["service"] == "provider-verification-adapter"


@pytest.mark.asyncio
async def test_license_verify_starter_response_shape():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get(
            "/license/verify",
            params={"state": "HI", "license_number": "HI-12345", "name": "Jane Doe", "dob": "1980-01-01"},
        )
    assert resp.status_code == 200
    data = resp.json()
    assert "verified" in data
    assert data["state"] == "HI"
    assert data["license_number"] == "HI-12345"
    assert "requires_manual_review" in data
    assert "source" in data


@pytest.mark.asyncio
async def test_background_check_starter_response_shape():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.post(
            "/background/check",
            json={"first_name": "Jane", "last_name": "Doe", "dob": "1980-01-01"},
        )
    assert resp.status_code == 200
    data = resp.json()
    assert "verified" in data
    assert "clear" in data
    assert "findings" in data
    assert data["recommendation"] in {"clear", "requires_review"}


@pytest.mark.asyncio
async def test_license_verify_rejects_missing_required_params():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get("/license/verify", params={"state": "HI"})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_license_verify_starter_flags_suspicious_license():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get(
            "/license/verify",
            params={"state": "HI", "license_number": "HI-BAD-123", "name": "Jane Doe", "dob": "1980-01-01"},
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["verified"] is False
    assert data["requires_manual_review"] is True
    assert data["status"] == "SUSPENDED"


@pytest.mark.asyncio
async def test_background_check_normalizes_upstream_clear_false(monkeypatch):
    class _FakeResp:
        status_code = 200

        @staticmethod
        def json():
            return {"verified": True, "clear": False, "findings": [{"code": "X"}]}

    class _FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def request(self, method, _url, params=None, json=None):
            assert method == "POST"
            _ = params
            assert json["first_name"] == "Jane"
            return _FakeResp()

    monkeypatch.setattr(adapter, "BACKGROUND_UPSTREAM_URL", "https://upstream.example/background")
    monkeypatch.setattr(adapter.httpx, "AsyncClient", lambda timeout: _FakeClient())

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.post(
            "/background/check",
            json={"first_name": "Jane", "last_name": "Doe", "dob": "1980-01-01"},
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["verified"] is True
    assert data["clear"] is False
    assert data["recommendation"] == "requires_review"


@pytest.mark.asyncio
async def test_adapter_auth_rejects_missing_signature(monkeypatch):
    monkeypatch.setattr(adapter, "REQUIRE_AUTH", True)
    monkeypatch.setattr(adapter, "ADAPTER_API_KEY", "k_test")
    monkeypatch.setattr(adapter, "ADAPTER_SHARED_SECRET", "s_test")

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get("/license/verify", params={"state": "HI", "license_number": "HI-12345"})
    assert resp.status_code == 401
    assert resp.json()["detail"] in {"adapter_auth_failed", "adapter_signature_missing"}


@pytest.mark.asyncio
async def test_adapter_auth_accepts_valid_hmac(monkeypatch):
    monkeypatch.setattr(adapter, "REQUIRE_AUTH", True)
    monkeypatch.setattr(adapter, "ADAPTER_API_KEY", "k_test")
    monkeypatch.setattr(adapter, "ADAPTER_SHARED_SECRET", "s_test")

    timestamp = "1700000000"
    monkeypatch.setattr(adapter.time, "time", lambda: int(timestamp))
    message = adapter._signature_payload(
        timestamp=timestamp,
        method="GET",
        path="/license/verify",
        body=b"",
    )
    signature = adapter.hmac.new(b"s_test", message.encode(), adapter.hashlib.sha256).hexdigest()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get(
            "/license/verify",
            params={"state": "HI", "license_number": "HI-12345"},
            headers={
                "X-Adapter-Key": "k_test",
                "X-Adapter-Timestamp": timestamp,
                "X-Adapter-Signature": signature,
            },
        )
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_adapter_rate_limit_blocks_excess_requests(monkeypatch):
    monkeypatch.setattr(adapter, "RATE_LIMIT_REQUESTS", 1)
    monkeypatch.setattr(adapter, "RATE_LIMIT_WINDOW_SECONDS", 60)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        first = await ac.get("/license/verify", params={"state": "HI", "license_number": "HI-1"})
        second = await ac.get("/license/verify", params={"state": "HI", "license_number": "HI-2"})
    assert first.status_code == 200
    assert second.status_code == 429
    assert second.json()["detail"] == "adapter_rate_limit_exceeded"


def test_client_bucket_key_ignores_xff_without_trusted_proxy():
    req = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/license/verify",
            "headers": [(b"x-forwarded-for", b"203.0.113.9, 10.0.0.5")],
            "client": ("10.0.0.5", 1234),
        }
    )
    assert adapter._client_bucket_key(req) == "10.0.0.5"


def test_client_bucket_key_uses_xff_with_trusted_proxy(monkeypatch):
    monkeypatch.setattr(adapter, "_TRUSTED_PROXY_NETWORKS", adapter._parse_trusted_proxy_cidrs("10.0.0.0/8"))
    req = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/license/verify",
            "headers": [(b"x-forwarded-for", b"203.0.113.9, 10.0.0.5")],
            "client": ("10.0.0.5", 1234),
        }
    )
    assert adapter._client_bucket_key(req) == "203.0.113.9"


@pytest.mark.asyncio
async def test_adapter_requires_configured_auth_when_enforced(monkeypatch):
    monkeypatch.setattr(adapter, "REQUIRE_AUTH", True)
    monkeypatch.setattr(adapter, "ADAPTER_API_KEY", "")
    monkeypatch.setattr(adapter, "ADAPTER_SHARED_SECRET", "")

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get("/license/verify", params={"state": "HI", "license_number": "HI-12345"})
    assert resp.status_code == 503
    assert resp.json()["detail"] == "adapter_auth_not_configured"


@pytest.mark.asyncio
async def test_license_upstream_retries_on_timeout_then_succeeds(monkeypatch):
    class _FakeResp:
        status_code = 200

        @staticmethod
        def json():
            return {"status": "ACTIVE", "verified": True}

    class _FakeClient:
        calls = 0

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def request(self, method, url, params=None, json=None):
            assert method == "GET"
            _ = url, params, json
            self.calls += 1
            if self.calls < 3:
                raise adapter.httpx.TimeoutException("timeout")
            return _FakeResp()

    fake = _FakeClient()
    monkeypatch.setattr(adapter, "LICENSE_UPSTREAM_URL", "https://upstream.example/license")
    monkeypatch.setattr(adapter.httpx, "AsyncClient", lambda timeout: fake)
    monkeypatch.setattr(adapter, "MAX_RETRIES", 2)
    monkeypatch.setattr(adapter, "RETRY_BACKOFF_SECONDS", 0)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get("/license/verify", params={"state": "HI", "license_number": "HI-12345"})
    assert resp.status_code == 200
    assert fake.calls == 3
