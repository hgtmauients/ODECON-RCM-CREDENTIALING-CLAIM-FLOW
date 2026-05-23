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

import os
from datetime import datetime, UTC
from typing import Any

import httpx
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

app = FastAPI(title="ClaimFlow Provider Verification Adapter", version="0.1.0")


LICENSE_UPSTREAM_URL = os.getenv("LICENSE_UPSTREAM_URL", "").strip()
BACKGROUND_UPSTREAM_URL = os.getenv("BACKGROUND_UPSTREAM_URL", "").strip()
HTTP_TIMEOUT_SECONDS = float(os.getenv("ADAPTER_HTTP_TIMEOUT_SECONDS", "10"))


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
    }


@app.get("/license/verify")
async def verify_license(
    state: str,
    license_number: str,
    name: str = "",
    dob: str = "",
) -> dict[str, Any]:
    if not state or not license_number:
        raise HTTPException(status_code=422, detail="state and license_number are required")

    if not LICENSE_UPSTREAM_URL:
        return _starter_license_decision(state=state, license_number=license_number)

    try:
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT_SECONDS) as client:
            resp = await client.get(
                LICENSE_UPSTREAM_URL,
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
async def run_background_check(body: BackgroundCheckRequest) -> dict[str, Any]:
    if not BACKGROUND_UPSTREAM_URL:
        return _starter_background_decision(first_name=body.first_name, last_name=body.last_name)

    try:
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT_SECONDS) as client:
            resp = await client.post(BACKGROUND_UPSTREAM_URL, json=body.model_dump())
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
