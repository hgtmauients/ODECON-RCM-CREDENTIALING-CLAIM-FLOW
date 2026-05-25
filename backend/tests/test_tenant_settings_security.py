from types import SimpleNamespace

import pytest

from api.auth import Principal
from api.schemas import TestSmtpRequest
from api import tenants


@pytest.mark.asyncio
async def test_smtp_test_endpoint_ignores_arbitrary_to_address(monkeypatch):
    async def fake_get_tenant_setting(_db, _tenant_id, key, default=None):
        values = {
            "smtp_host": "smtp.example.com",
            "smtp_port": "587",
            "smtp_user": "user",
            "smtp_pass": "pass",
            "from_email": "no-reply@example.com",
        }
        return values.get(key, default)

    monkeypatch.setattr("core.tenant_config.get_tenant_setting", fake_get_tenant_setting)
    monkeypatch.setattr(tenants, "assert_safe_smtp_host", lambda _host, field_name=None: None)

    sent = {}

    class FakeSMTP:
        def __init__(self, _host, _port, timeout=15):
            self.timeout = timeout

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def starttls(self):
            return None

        def login(self, _user, _password):
            return None

        def sendmail(self, _from_email, recipients, _msg):
            sent["recipients"] = recipients

    monkeypatch.setattr("smtplib.SMTP", FakeSMTP)

    principal = Principal(
        user_id="u1",
        tenant_id="t1",
        email="operator@example.com",
        roles=["admin"],
        raw_claims={},
        token_tenant_id="t1",
    )

    resp = await tenants.test_smtp_settings(
        tenant_id="t1",
        body=TestSmtpRequest(to="attacker@example.com"),
        db=SimpleNamespace(),
        current_user=principal,
    )

    assert resp["success"] is True
    assert sent["recipients"] == ["operator@example.com"]


@pytest.mark.asyncio
async def test_integration_test_endpoints_mask_internal_errors(monkeypatch):
    async def fake_get_tenant_setting(_db, _tenant_id, key, default=None):
        values = {
            "api_cert_key": "api-key",
            "caqh_org_id": "org-1",
            "caqh_username": "user",
            "caqh_password": "pass",
        }
        return values.get(key, default)

    async def raise_secret(*_args, **_kwargs):
        raise RuntimeError("sensitive stack details")

    monkeypatch.setattr("core.tenant_config.get_tenant_setting", fake_get_tenant_setting)
    monkeypatch.setattr(tenants, "request_with_retry", raise_secret)

    principal = Principal(
        user_id="u1",
        tenant_id="t1",
        email="operator@example.com",
        roles=["admin"],
        raw_claims={},
        token_tenant_id="t1",
    )

    api_cert_resp = await tenants.test_api_cert_settings(
        tenant_id="t1",
        db=SimpleNamespace(),
        current_user=principal,
    )
    caqh_resp = await tenants.test_caqh_settings(
        tenant_id="t1",
        db=SimpleNamespace(),
        current_user=principal,
    )

    assert api_cert_resp == {"success": False, "error": tenants._integration_test_error_message()}
    assert caqh_resp == {"success": False, "error": tenants._integration_test_error_message()}
