from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from core.outbound_guard import assert_safe_http_url, assert_safe_sftp_host, assert_safe_smtp_host
from services.clearinghouse_transport import APITransport

pytestmark = pytest.mark.security


@pytest.fixture(autouse=True)
def _mock_dns(monkeypatch):
    def fake_getaddrinfo(host, *_args, **_kwargs):
        mapping = {
            "api.api-cert.com": [("2.2.2.2", 0)],
            "sftp.waystar.com": [("3.3.3.3", 0)],
            "bad.example": [("10.0.0.5", 0)],
        }
        if host in mapping:
            return [(0, 0, 0, "", sockaddr) for sockaddr in mapping[host]]
        raise OSError("dns lookup failed")

    monkeypatch.setattr("core.outbound_guard.socket.getaddrinfo", fake_getaddrinfo)


def test_assert_safe_http_url_rejects_private_ip():
    with pytest.raises(HTTPException) as exc:
        assert_safe_http_url("http://10.0.0.5/ping", field_name="api_endpoint")
    assert exc.value.status_code == 422


def test_assert_safe_http_url_rejects_localhost():
    with pytest.raises(HTTPException):
        assert_safe_http_url("https://localhost/api", field_name="api_endpoint")


def test_assert_safe_http_url_allows_public_hostname():
    assert_safe_http_url("https://api.api-cert.com/v1/usage", field_name="api_endpoint")


def test_assert_safe_smtp_host_rejects_private_ip():
    with pytest.raises(HTTPException):
        assert_safe_smtp_host("127.0.0.1")


def test_assert_safe_sftp_host_rejects_private_ip():
    with pytest.raises(HTTPException):
        assert_safe_sftp_host("10.0.0.5")


def test_assert_safe_sftp_host_allows_public_hostname():
    assert_safe_sftp_host("sftp.waystar.com")


def test_assert_safe_http_url_rejects_hostname_resolving_to_private_ip():
    with pytest.raises(HTTPException) as exc:
        assert_safe_http_url("https://bad.example/path", field_name="api_endpoint")
    assert exc.value.status_code == 422
    assert "resolves to a blocked destination" in exc.value.detail


def test_api_transport_validated_endpoint_rejects_blocked_target():
    connection = SimpleNamespace(api_endpoint="http://169.254.169.254/latest")
    with pytest.raises(HTTPException):
        APITransport._validated_endpoint(connection)
