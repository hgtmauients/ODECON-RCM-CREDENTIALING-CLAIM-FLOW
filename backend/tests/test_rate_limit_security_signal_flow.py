"""
Integration-style test for rate-limit security signal emission.
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from core.rate_limit import RateLimitMiddleware

pytestmark = pytest.mark.security


def test_rate_limit_exceed_emits_structured_security_signal(caplog):
    app = FastAPI()
    app.add_middleware(RateLimitMiddleware, requests_per_window=1, window_seconds=60)

    @app.get("/ping")
    async def ping():
        return {"ok": True}

    client = TestClient(app)
    first = client.get("/ping")
    second = client.get("/ping")
    assert first.status_code == 200
    assert second.status_code == 429

    signal = None
    for rec in caplog.records:
        if getattr(rec, "security_event", "") == "rate_limit_exceeded":
            signal = rec
    assert signal is not None
    fields = getattr(signal, "security_fields", {})
    assert fields.get("path") == "/ping"
    assert fields.get("method") == "GET"
    assert fields.get("schema_version") == 1
