import pytest
from fastapi.testclient import TestClient

from app.main import app

pytestmark = pytest.mark.security


def test_cors_preflight_uses_explicit_methods_not_wildcard():
    client = TestClient(app)
    response = client.options(
        "/api/auth/me",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "Authorization,Content-Type",
        },
    )
    assert response.status_code in (200, 204)
    allowed_methods = response.headers.get("access-control-allow-methods", "")
    assert "*" not in allowed_methods
    assert "GET" in allowed_methods
