"""
Provider verification adapter service.

This is a drop-in integration layer between ClaimFlow and external verification
vendors. It provides a stable contract for:
  - GET /license/verify
  - POST /background/check

Modes:
  1) Starter/mock mode (default): deterministic local decisions for immediate use.
  2) Upstream mode: when *_UPSTREAM_URL env vars are set, proxy to vendors and
     normalize responses to ClaimFlow's expected schema.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import ipaddress
import json
import os
import time
from datetime import datetime, UTC
from typing import Any, Union
from urllib.parse import urlparse

import httpx
from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel

from core.startup_checks import validate_adapter_startup_security

app = FastAPI(title="ClaimFlow Provider Verification Adapter", version="0.1.0")


LICENSE_UPSTREAM_URL = os.getenv("LICENSE_UPSTREAM_URL", "").strip()
BACKGROUND_UPSTREAM_URL = os.getenv("BACKGROUND_UPSTREAM_URL", "").strip()
HTTP_TIMEOUT_SECONDS = float(os.getenv("ADAPTER_HTTP_TIMEOUT_SECONDS", "10"))
MAX_RETRIES = max(0, int(os.getenv("ADAPTER_MAX_RETRIES", "2")))
RETRY_BACKOFF_SECONDS = float(os.getenv("ADAPTER_RETRY_BACKOFF_SECONDS", "0.2"))
ENV = os.getenv("ENV", "development")
REQUIRE_AUTH = os.getenv("ADAPTER_REQUIRE_AUTH", "true").strip().lower() in {"1", "true", "yes", "y"}
if ENV == "production":
    REQUIRE_AUTH = True
ADAPTER_API_KEY = os.getenv("ADAPTER_API_KEY", "").strip()
ADAPTER_SHARED_SECRET = os.getenv("ADAPTER_SHARED_SECRET", "").strip()
AUTH_WINDOW_SECONDS = max(30, int(os.getenv("ADAPTER_AUTH_WINDOW_SECONDS", "300")))
RATE_LIMIT_REQUESTS = max(1, int(os.getenv("ADAPTER_RATE_LIMIT_REQUESTS", "120")))
RATE_LIMIT_WINDOW_SECONDS = max(1, int(os.getenv("ADAPTER_RATE_LIMIT_WINDOW_SECONDS", "60")))
TRUSTED_PROXY_CIDRS = os.getenv("ADAPTER_TRUSTED_PROXY_CIDRS", "").strip()
_RATE_LIMIT_BUCKETS: dict[str, list[float]] = {}
_RATE_LIMIT_LOCK = asyncio.Lock()
IPNetwork = Union[ipaddress.IPv4Network, ipaddress.IPv6Network]

validate_adapter_startup_security(os.environ)


class BackgroundCheckRequest(BaseModel):
    first_name: str
    last_name: str
    dob: str
    ssn: str | None = None


def _iso_now() -> str:
    return datetime.now(UTC).isoformat()


def _to_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "y"}


def _requires_auth() -> bool:
    return REQUIRE_AUTH


def _parse_trusted_proxy_cidrs(raw: str) -> list[IPNetwork]:
    trusted: list[IPNetwork] = []
    for part in (raw or "").split(","):
        token = part.strip()
        if not token:
            continue
        try:
            trusted.append(ipaddress.ip_network(token, strict=False))
        except ValueError:
            continue
    return trusted


_TRUSTED_PROXY_NETWORKS = _parse_trusted_proxy_cidrs(TRUSTED_PROXY_CIDRS)


def _is_trusted_proxy(peer_ip: str) -> bool:
    if not _TRUSTED_PROXY_NETWORKS:
        return False
    try:
        addr = ipaddress.ip_address(peer_ip)
    except ValueError:
        return False
    return any(addr in net for net in _TRUSTED_PROXY_NETWORKS)


def _signature_payload(*, timestamp: str, method: str, path: str, body: bytes) -> str:
    body_hash = hashlib.sha256(body).hexdigest()
    return f"{timestamp}.{method.upper()}.{path}.{body_hash}"


async def _enforce_adapter_auth(request: Request, body: bytes) -> None:
    if not _requires_auth():
        return
    if not ADAPTER_API_KEY and not ADAPTER_SHARED_SECRET:
        # Fail closed: if auth is required but no mechanism is configured,
        # deny requests rather than silently running open.
        raise HTTPException(status_code=503, detail="adapter_auth_not_configured")

    if ADAPTER_API_KEY:
        presented_key = request.headers.get("X-Adapter-Key", "")
        if not hmac.compare_digest(presented_key, ADAPTER_API_KEY):
            raise HTTPException(status_code=401, detail="adapter_auth_failed")

    if ADAPTER_SHARED_SECRET:
        timestamp = request.headers.get("X-Adapter-Timestamp", "").strip()
        signature = request.headers.get("X-Adapter-Signature", "").strip()
        if not timestamp or not signature:
            raise HTTPException(status_code=401, detail="adapter_signature_missing")
        try:
            ts = int(timestamp)
        except ValueError as exc:
            raise HTTPException(status_code=401, detail="adapter_signature_invalid_timestamp") from exc
        if abs(int(time.time()) - ts) > AUTH_WINDOW_SECONDS:
            raise HTTPException(status_code=401, detail="adapter_signature_expired")

        expected = hmac.new(
            ADAPTER_SHARED_SECRET.encode(),
            _signature_payload(
                timestamp=timestamp,
                method=request.method,
                path=request.url.path,
                body=body,
            ).encode(),
            hashlib.sha256,
        ).hexdigest()
        if not hmac.compare_digest(signature, expected):
            raise HTTPException(status_code=401, detail="adapter_signature_invalid")


def _client_bucket_key(request: Request) -> str:
    peer_ip = request.client.host if request.client and request.client.host else "unknown"
    if _is_trusted_proxy(peer_ip):
        fwd = request.headers.get("x-forwarded-for", "").strip()
        if fwd:
            first_hop = fwd.split(",")[0].strip()
            if first_hop:
                return first_hop
    if peer_ip:
        return peer_ip
    return "unknown"


async def _enforce_rate_limit(request: Request) -> None:
    now = time.monotonic()
    cutoff = now - RATE_LIMIT_WINDOW_SECONDS
    key = _client_bucket_key(request)
    async with _RATE_LIMIT_LOCK:
        bucket = _RATE_LIMIT_BUCKETS.setdefault(key, [])
        while bucket and bucket[0] < cutoff:
            bucket.pop(0)
        if len(bucket) >= RATE_LIMIT_REQUESTS:
            raise HTTPException(status_code=429, detail="adapter_rate_limit_exceeded")
        bucket.append(now)


async def _upstream_request_with_retry(
    *,
    method: str,
    url: str,
    params: dict[str, Any] | None = None,
    json_body: dict[str, Any] | None = None,
) -> httpx.Response:
    attempt = 0
    last_exc: Exception | None = None
    while attempt <= MAX_RETRIES:
        try:
            async with httpx.AsyncClient(timeout=HTTP_TIMEOUT_SECONDS) as client:
                response = await client.request(method, url, params=params, json=json_body)
            if response.status_code >= 500 and attempt < MAX_RETRIES:
                await asyncio.sleep(RETRY_BACKOFF_SECONDS * (2**attempt))
                attempt += 1
                continue
            return response
        except (httpx.TimeoutException, httpx.TransportError) as exc:
            last_exc = exc
            if attempt >= MAX_RETRIES:
                raise
            await asyncio.sleep(RETRY_BACKOFF_SECONDS * (2**attempt))
            attempt += 1
    if last_exc:
        raise last_exc
    raise RuntimeError("unreachable retry state")


def _normalize_license_response(raw: dict[str, Any], *, state: str, license_number: str) -> dict[str, Any]:
    status = str(raw.get("status", "")).upper()
    verified = _to_bool(raw.get("verified"), default=(status in {"ACTIVE", "CURRENT", "VALID"}))
    return {
        "verified": verified,
        "state": state,
        "license_number": license_number,
        "status": status or "UNKNOWN",
        "issue_date": raw.get("issue_date"),
        "expiration_date": raw.get("expiration_date"),
        "discipline_history": raw.get("discipline_history", []),
        "requires_manual_review": not verified,
        "source": "provider_adapter",
        "verified_at": _iso_now(),
    }


def _normalize_background_response(raw: dict[str, Any]) -> dict[str, Any]:
    clear = _to_bool(raw.get("clear"), default=False)
    verified = _to_bool(raw.get("verified"), default=True)
    return {
        "verified": verified,
        "clear": clear,
        "findings": raw.get("findings", []),
        "recommendation": raw.get("recommendation", "clear" if clear else "requires_review"),
        "checked_at": _iso_now(),
        "source": "provider_adapter",
    }


def _starter_license_decision(*, state: str, license_number: str) -> dict[str, Any]:
    upper_license = (license_number or "").upper()
    suspicious = any(token in upper_license for token in ("BAD", "REVOKE", "EXPIRE", "SUSPEND"))
    status = "ACTIVE" if not suspicious else "SUSPENDED"
    verified = not suspicious and bool(state.strip()) and bool(license_number.strip())
    return {
        "verified": verified,
        "state": state,
        "license_number": license_number,
        "status": status,
        "issue_date": None,
        "expiration_date": None,
        "discipline_history": [],
        "requires_manual_review": not verified,
        "source": "provider_adapter_starter",
        "verified_at": _iso_now(),
    }


def _starter_background_decision(*, first_name: str, last_name: str) -> dict[str, Any]:
    full = f"{first_name} {last_name}".strip().upper()
    flagged = any(token in full for token in ("REJECT", "FRAUD", "SANCTION", "EXCLUDE"))
    clear = not flagged
    findings = [] if clear else [{"type": "manual_flag", "message": "Starter adapter flagged record for review"}]
    return {
        "verified": True,
        "clear": clear,
        "findings": findings,
        "recommendation": "clear" if clear else "requires_review",
        "checked_at": _iso_now(),
        "source": "provider_adapter_starter",
    }


@app.get("/health")
async def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "service": "provider-verification-adapter",
        "license_mode": "upstream" if LICENSE_UPSTREAM_URL else "starter",
        "background_mode": "upstream" if BACKGROUND_UPSTREAM_URL else "starter",
        "auth_enabled": _requires_auth(),
        "rate_limit": {"requests": RATE_LIMIT_REQUESTS, "window_seconds": RATE_LIMIT_WINDOW_SECONDS},
    }


@app.get("/license/verify")
async def verify_license(
    request: Request,
    state: str,
    license_number: str,
    name: str = "",
    dob: str = "",
) -> dict[str, Any]:
    await _enforce_rate_limit(request)
    await _enforce_adapter_auth(request, b"")
    if not state or not license_number:
        raise HTTPException(status_code=422, detail="state and license_number are required")

    if not LICENSE_UPSTREAM_URL:
        return _starter_license_decision(state=state, license_number=license_number)

    try:
        resp = await _upstream_request_with_retry(
            method="GET",
            url=LICENSE_UPSTREAM_URL,
            params={
                "state": state,
                "license_number": license_number,
                "name": name,
                "dob": dob,
            },
        )
        if resp.status_code != 200:
            return {
                "verified": False,
                "state": state,
                "license_number": license_number,
                "error": f"license_upstream_http_{resp.status_code}",
                "requires_manual_review": True,
                "source": "provider_adapter",
                "checked_at": _iso_now(),
            }
        payload = resp.json()
        if not isinstance(payload, dict):
            raise ValueError("license upstream returned non-object JSON")
        return _normalize_license_response(payload, state=state, license_number=license_number)
    except Exception as exc:
        return {
            "verified": False,
            "state": state,
            "license_number": license_number,
            "error": f"license_upstream_error:{exc}",
            "requires_manual_review": True,
            "source": "provider_adapter",
            "checked_at": _iso_now(),
        }


@app.post("/background/check")
async def run_background_check(request: Request, body: BackgroundCheckRequest) -> dict[str, Any]:
    raw_body = await request.body()
    await _enforce_rate_limit(request)
    await _enforce_adapter_auth(request, raw_body)
    if not BACKGROUND_UPSTREAM_URL:
        return _starter_background_decision(first_name=body.first_name, last_name=body.last_name)

    try:
        resp = await _upstream_request_with_retry(
            method="POST",
            url=BACKGROUND_UPSTREAM_URL,
            json_body=body.model_dump(),
        )
        if resp.status_code != 200:
            return {
                "verified": False,
                "clear": False,
                "findings": [],
                "recommendation": "requires_review",
                "checked_at": _iso_now(),
                "source": "provider_adapter",
                "error": f"background_upstream_http_{resp.status_code}",
            }
        payload = resp.json()
        if not isinstance(payload, dict):
            raise ValueError("background upstream returned non-object JSON")
        return _normalize_background_response(payload)
    except Exception as exc:
        return {
            "verified": False,
            "clear": False,
            "findings": [],
            "recommendation": "requires_review",
            "checked_at": _iso_now(),
            "source": "provider_adapter",
            "error": f"background_upstream_error:{exc}",
        }
