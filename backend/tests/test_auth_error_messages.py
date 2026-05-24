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


def test_invalid_jwt_emits_security_signal(caplog):
    client = TestClient(app)
    resp = client.get("/api/auth/me", headers={"Authorization": "Bearer not-a-jwt"})
    assert resp.status_code == 401
    signal = None
    for rec in caplog.records:
        if getattr(rec, "security_event", "") == "auth_token_invalid":
            signal = rec
    assert signal is not None
    fields = getattr(signal, "security_fields", {})
    assert fields.get("schema_version") == 1
    assert fields.get("path") == "jwt_decode"
