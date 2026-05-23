import pytest
from httpx import ASGITransport, AsyncClient

from adapter.main import app


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
