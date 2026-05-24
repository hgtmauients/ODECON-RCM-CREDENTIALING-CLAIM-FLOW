"""
Outbound destination guardrails for admin-configured integrations.

Blocks obvious SSRF targets (localhost/private/link-local/multicast/reserved IPs)
while still allowing public internet hostnames.
"""

from __future__ import annotations

import ipaddress
import os
from urllib.parse import urlparse

from fastapi import HTTPException


def _allow_private_destinations() -> bool:
    return os.getenv("ALLOW_PRIVATE_OUTBOUND_DESTINATIONS", "").strip().lower() in {"1", "true", "yes", "y"}


def _is_blocked_ip(value: str) -> bool:
    try:
        addr = ipaddress.ip_address(value)
    except ValueError:
        return False
    return any(
        (
            addr.is_private,
            addr.is_loopback,
            addr.is_link_local,
            addr.is_multicast,
            addr.is_reserved,
            addr.is_unspecified,
        )
    )


def _is_blocked_hostname(hostname: str) -> bool:
    lowered = (hostname or "").strip().lower().rstrip(".")
    if not lowered:
        return True
    if lowered in {"localhost", "localhost.localdomain"}:
        return True
    if lowered.endswith(".local"):
        return True
    return False


def assert_safe_http_url(url: str, *, field_name: str) -> None:
    if _allow_private_destinations():
        return
    parsed = urlparse((url or "").strip())
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise HTTPException(status_code=422, detail=f"{field_name} must be a valid http(s) URL")
    host = parsed.hostname
    if _is_blocked_hostname(host) or _is_blocked_ip(host):
        raise HTTPException(status_code=422, detail=f"{field_name} points to a blocked destination")


def assert_safe_smtp_host(host: str, *, field_name: str = "smtp_host") -> None:
    if _allow_private_destinations():
        return
    value = (host or "").strip()
    if not value:
        raise HTTPException(status_code=422, detail=f"{field_name} is required")
    if _is_blocked_hostname(value) or _is_blocked_ip(value):
        raise HTTPException(status_code=422, detail=f"{field_name} points to a blocked destination")
