"""
Authentication error response hardening tests.
"""

import pytest
from fastapi.testclient import TestClient

from app.main import app

pytestmark = pytest.mark.security


def test_invalid_jwt_returns_generic_error_detail():
    client = TestClient(app)
    resp = client.get("/api/auth/me", headers={"Authorization": "Bearer not-a-jwt"})
    assert resp.status_code == 401
    assert resp.json()["detail"] == "Invalid token"
