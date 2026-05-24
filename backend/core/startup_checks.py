"""
Startup security validation helpers.

Fail fast on unsafe production configuration so deployments don't come up with
silent security drift.
"""

from __future__ import annotations

import base64
import ipaddress
from typing import Mapping
from urllib.parse import urlparse


def _as_bool(value: str, *, default: bool = False) -> bool:
    if value is None:
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "y"}


def _validate_cidrs(raw: str, *, env_key: str) -> list[str]:
    errors: list[str] = []
    for part in (raw or "").split(","):
        token = part.strip()
        if not token:
            continue
        try:
            ipaddress.ip_network(token, strict=False)
        except ValueError:
            errors.append(f"{env_key} contains invalid CIDR entry: {token!r}")
    return errors


def _validate_https_url(url: str, *, env_key: str) -> list[str]:
    if not url:
        return [f"{env_key} is required"]
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.netloc:
        return [f"{env_key} must be a valid https URL"]
    return []


def _validate_encryption_key(raw_key: str) -> list[str]:
    if not raw_key:
        return ["CLAIMFLOW_ENCRYPTION_KEY is required in production"]
    try:
        decoded = base64.b64decode(raw_key)
    except Exception:
        return ["CLAIMFLOW_ENCRYPTION_KEY must be valid base64"]
    if len(decoded) not in {16, 24, 32}:
        return ["CLAIMFLOW_ENCRYPTION_KEY must decode to 16, 24, or 32 bytes"]
    return []


def _validate_cors_origins(raw_origins: str) -> list[str]:
    errors: list[str] = []
    origins = [o.strip() for o in (raw_origins or "").split(",") if o.strip()]
    if not origins:
        return ["CORS_ORIGINS must include at least one explicit origin in production"]
    for origin in origins:
        if "*" in origin:
            errors.append("CORS_ORIGINS cannot contain wildcard entries in production")
            continue
        parsed = urlparse(origin)
        if parsed.scheme != "https" or not parsed.netloc:
            errors.append(f"CORS_ORIGINS contains invalid origin: {origin!r} (https required)")
    return errors


def validate_api_startup_security(env: Mapping[str, str] | None = None) -> None:
    config = env or {}
    if (config.get("ENV") or "development") != "production":
        return

    errors: list[str] = []
    algorithm = (config.get("JWT_ALGORITHM") or "HS256").upper()
    if algorithm not in {"HS256", "RS256"}:
        errors.append("JWT_ALGORITHM must be HS256 or RS256")
    elif algorithm == "HS256":
        secret = config.get("JWT_SECRET") or ""
        if len(secret) < 32:
            errors.append("JWT_SECRET must be at least 32 characters in production HS256 mode")
    else:
        errors.extend(_validate_https_url(config.get("JWT_JWKS_URL") or "", env_key="JWT_JWKS_URL"))

    errors.extend(_validate_encryption_key(config.get("CLAIMFLOW_ENCRYPTION_KEY") or ""))
    errors.extend(_validate_cors_origins(config.get("CORS_ORIGINS") or ""))
    errors.extend(_validate_cidrs(config.get("TRUSTED_PROXY_CIDRS") or "", env_key="TRUSTED_PROXY_CIDRS"))

    if errors:
        raise RuntimeError("Startup security validation failed: " + "; ".join(errors))


def validate_adapter_startup_security(env: Mapping[str, str] | None = None) -> None:
    config = env or {}
    if (config.get("ENV") or "development") != "production":
        return

    errors: list[str] = []

    require_auth = _as_bool(config.get("ADAPTER_REQUIRE_AUTH"), default=True)
    if not require_auth:
        errors.append("ADAPTER_REQUIRE_AUTH=false is not allowed in production")
    api_key = config.get("ADAPTER_API_KEY") or ""
    shared_secret = config.get("ADAPTER_SHARED_SECRET") or ""
    if not api_key and not shared_secret:
        errors.append("Adapter auth is required in production: set ADAPTER_API_KEY or ADAPTER_SHARED_SECRET")

    errors.extend(
        _validate_cidrs(
            config.get("ADAPTER_TRUSTED_PROXY_CIDRS") or "",
            env_key="ADAPTER_TRUSTED_PROXY_CIDRS",
        )
    )

    if errors:
        raise RuntimeError("Adapter startup security validation failed: " + "; ".join(errors))
