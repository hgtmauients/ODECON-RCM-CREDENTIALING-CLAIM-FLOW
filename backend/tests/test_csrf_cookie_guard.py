"""
CSRF protections for cookie-backed auth sessions.
"""

import pytest
from fastapi.testclient import TestClient

from app.main import app
from api.auth import AUTH_COOKIE_NAME, CSRF_COOKIE_NAME, CSRF_HEADER_NAME

pytestmark = pytest.mark.security


def test_cookie_auth_mutation_requires_csrf_token():
    client = TestClient(app)
    client.cookies.set(AUTH_COOKIE_NAME, "fake-token")
    resp = client.post("/api/auth/logout")
    assert resp.status_code == 403
    assert resp.json()["detail"] == "CSRF token missing or invalid"


def test_cookie_auth_mutation_rejects_mismatched_csrf_token():
    client = TestClient(app)
    client.cookies.set(AUTH_COOKIE_NAME, "fake-token")
    client.cookies.set(CSRF_COOKIE_NAME, "csrf-cookie")
    resp = client.post("/api/auth/logout", headers={CSRF_HEADER_NAME: "csrf-header"})
    assert resp.status_code == 403
    assert resp.json()["detail"] == "CSRF token missing or invalid"


def test_cookie_auth_mutation_allows_matching_csrf_token():
    client = TestClient(app)
    client.cookies.set(AUTH_COOKIE_NAME, "fake-token")
    client.cookies.set(CSRF_COOKIE_NAME, "csrf-token")
    resp = client.post("/api/auth/logout", headers={CSRF_HEADER_NAME: "csrf-token"})
    # Middleware should pass; auth dependency can still reject fake token.
    assert resp.status_code != 403


def test_bearer_requests_bypass_csrf_cookie_guard():
    client = TestClient(app)
    client.cookies.set(AUTH_COOKIE_NAME, "fake-cookie-token")
    resp = client.post("/api/auth/logout", headers={"Authorization": "Bearer fake-bearer-token"})
    assert resp.status_code != 403


def test_csrf_origin_denied_for_mutation_even_without_cookie():
    client = TestClient(app)
    resp = client.post(
        "/api/auth/login",
        json={"email": "u@example.com", "password": "x"},
        headers={"Origin": "https://evil.example"},
    )
    assert resp.status_code == 403
    assert resp.json()["detail"] == "CSRF origin denied"
