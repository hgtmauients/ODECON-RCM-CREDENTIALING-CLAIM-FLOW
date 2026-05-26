import pytest

from core.client_ip import get_client_ip, parse_trusted_proxy_cidrs

pytestmark = pytest.mark.security


def _make_request(*, peer_ip: str, xff: str | None = None):
    class _Client:
        host = peer_ip

    class _Request:
        client = _Client()
        headers = {}

    req = _Request()
    if xff is not None:
        req.headers["X-Forwarded-For"] = xff
    return req


def test_get_client_ip_ignores_xff_without_trusted_proxy():
    req = _make_request(peer_ip="198.51.100.7", xff="203.0.113.4, 198.51.100.7")
    assert get_client_ip(req, set()) == "198.51.100.7"


def test_get_client_ip_uses_xff_when_proxy_is_trusted():
    req = _make_request(peer_ip="10.10.10.10", xff="203.0.113.4, 10.10.10.10")
    trusted = parse_trusted_proxy_cidrs("10.0.0.0/8")
    assert get_client_ip(req, trusted) == "203.0.113.4"


def test_parse_trusted_proxy_cidrs_ignores_invalid_entries():
    trusted = parse_trusted_proxy_cidrs("10.0.0.0/8,not-a-cidr,127.0.0.1/32")
    assert len(trusted) == 2
