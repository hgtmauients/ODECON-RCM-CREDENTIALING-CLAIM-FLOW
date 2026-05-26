"""
Shared client IP resolution with trusted proxy support.
"""

from __future__ import annotations

import ipaddress
import logging
import os
from typing import Set, Union

from fastapi import Request

logger = logging.getLogger(__name__)

IPNetwork = Union[ipaddress.IPv4Network, ipaddress.IPv6Network]


def parse_trusted_proxy_cidrs(raw: str) -> Set[IPNetwork]:
    """Parse comma-delimited CIDRs used to trust forwarding headers."""
    cidrs: Set[IPNetwork] = set()
    for part in (raw or "").split(","):
        token = part.strip()
        if not token:
            continue
        try:
            cidrs.add(ipaddress.ip_network(token, strict=False))
        except ValueError:
            logger.warning("Ignoring invalid TRUSTED_PROXY_CIDRS entry: %r", token)
    return cidrs


def _is_trusted_proxy(peer_ip: str, trusted_proxy_cidrs: Set[IPNetwork]) -> bool:
    if not trusted_proxy_cidrs:
        return False
    try:
        addr = ipaddress.ip_address(peer_ip)
    except ValueError:
        return False
    return any(addr in net for net in trusted_proxy_cidrs)


def get_client_ip(request: Request, trusted_proxy_cidrs: Set[IPNetwork] | None = None) -> str:
    """
    Best-effort client IP extraction.

    Uses X-Forwarded-For (first hop) only when the immediate socket peer is in
    TRUSTED_PROXY_CIDRS. Otherwise ignores forwarding headers and uses socket
    peer address.
    """
    if trusted_proxy_cidrs is None:
        trusted_proxy_cidrs = parse_trusted_proxy_cidrs(os.getenv("TRUSTED_PROXY_CIDRS", ""))

    peer_ip = request.client.host if request.client else "unknown"
    if _is_trusted_proxy(peer_ip, trusted_proxy_cidrs):
        xff = request.headers.get("X-Forwarded-For", "")
        if xff:
            first_hop = xff.split(",")[0].strip()
            if first_hop:
                return first_hop
    return peer_ip
