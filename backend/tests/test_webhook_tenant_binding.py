"""
Tests for the webhook signature scheme.

Closes v9-C1: tenant_id is part of the signed message, so an attacker who
learns one tenant's secret cannot replay against another tenant by simply
swapping the X-Tenant-ID header.
"""

import hashlib
import hmac
import time

import pytest


@pytest.fixture
def cred_module():
    import api.credentialing as c
    return c


def _sign(secret: str, body: bytes, timestamp: str, tenant_id: str) -> str:
    body_digest = hashlib.sha256(body).hexdigest()
    msg = f"{tenant_id}.{timestamp}.{body_digest}".encode("ascii")
    return hmac.new(secret.encode(), msg, hashlib.sha256).hexdigest()


@pytest.mark.asyncio
async def test_correct_signature_passes(cred_module):
    body = b'{"npi": "1234567890"}'
    ts = str(int(time.time()))
    secret = "tenant-A-secret"
    sig = _sign(secret, body, ts, "tenant-A")
    ok = await cred_module._verify_webhook_signature(
        payload=body, signature=sig, secret=secret, timestamp=ts, tenant_id="tenant-A",
    )
    assert ok is True


@pytest.mark.asyncio
async def test_swapped_tenant_id_rejects(cred_module):
    """Sign for tenant-A but submit as tenant-B → must fail."""
    body = b'{"npi": "1234567890"}'
    ts = str(int(time.time()))
    secret = "tenant-A-secret"
    sig = _sign(secret, body, ts, "tenant-A")
    # Replay against tenant-B with tenant-A's secret + signature.
    ok = await cred_module._verify_webhook_signature(
        payload=body, signature=sig, secret=secret, timestamp=ts, tenant_id="tenant-B",
    )
    assert ok is False


@pytest.mark.asyncio
async def test_missing_secret_rejects(cred_module):
    body = b"{}"
    ts = str(int(time.time()))
    sig = _sign("anything", body, ts, "tenant-A")
    ok = await cred_module._verify_webhook_signature(
        payload=body, signature=sig, secret="", timestamp=ts, tenant_id="tenant-A",
    )
    assert ok is False


@pytest.mark.asyncio
async def test_stale_timestamp_rejects(cred_module):
    body = b"{}"
    stale_ts = str(int(time.time()) - 10_000)  # ~3 hours ago
    secret = "tenant-A-secret"
    sig = _sign(secret, body, stale_ts, "tenant-A")
    ok = await cred_module._verify_webhook_signature(
        payload=body, signature=sig, secret=secret, timestamp=stale_ts, tenant_id="tenant-A",
    )
    assert ok is False


@pytest.mark.asyncio
async def test_body_tamper_rejects(cred_module):
    body = b'{"npi": "1234567890"}'
    ts = str(int(time.time()))
    secret = "tenant-A-secret"
    sig = _sign(secret, body, ts, "tenant-A")
    ok = await cred_module._verify_webhook_signature(
        payload=b'{"npi": "9999999999"}', signature=sig, secret=secret, timestamp=ts, tenant_id="tenant-A",
    )
    assert ok is False
