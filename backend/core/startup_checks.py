"""
Startup security validation helpers.

Fail fast on unsafe production configuration so deployments don't come up with
silent security drift.
"""

from __future__ import annotations

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

    errors.extend(_validate_cidrs(config.get("TRUSTED_PROXY_CIDRS") or "", env_key="TRUSTED_PROXY_CIDRS"))

    if errors:
        raise RuntimeError("Startup security validation failed: " + "; ".join(errors))


def validate_adapter_startup_security(env: Mapping[str, str] | None = None) -> None:
    config = env or {}
    if (config.get("ENV") or "development") != "production":
        return

    errors: list[str] = []

    require_auth = _as_bool(config.get("ADAPTER_REQUIRE_AUTH"), default=True)
    api_key = config.get("ADAPTER_API_KEY") or ""
    shared_secret = config.get("ADAPTER_SHARED_SECRET") or ""
    if require_auth and not api_key and not shared_secret:
        errors.append("Adapter auth is required in production: set ADAPTER_API_KEY or ADAPTER_SHARED_SECRET")

    errors.extend(
        _validate_cidrs(
            config.get("ADAPTER_TRUSTED_PROXY_CIDRS") or "",
            env_key="ADAPTER_TRUSTED_PROXY_CIDRS",
        )
    )

    if errors:
        raise RuntimeError("Adapter startup security validation failed: " + "; ".join(errors))
