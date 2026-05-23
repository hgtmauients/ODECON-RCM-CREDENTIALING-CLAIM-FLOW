import pytest
from httpx import ASGITransport, AsyncClient

import adapter.main as adapter

app = adapter.app


@pytest.fixture
def anyio_backend():
    return "asyncio"


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

        async def post(self, _url, json):
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
