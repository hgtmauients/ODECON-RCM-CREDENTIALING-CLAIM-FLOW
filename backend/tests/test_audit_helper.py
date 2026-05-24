"""
Tests for core.audit logging helper.

Closes v10 NEW-C3 — the helper is wired throughout v11; here we just verify
the helper writes a SecurityAuditLog row to the supplied session and that
context-manager mode logs success vs. failure correctly.
"""

import pytest
from unittest.mock import MagicMock
from contextlib import asynccontextmanager

from api.auth import Principal


@pytest.fixture
def principal() -> Principal:
    return Principal(
        user_id="u1", tenant_id="11111111-1111-1111-1111-111111111111",
        email="t@example.com", roles=["admin"],
    )


@pytest.fixture
def fake_request():
    class _Hdrs(dict):
        def get(self, key, default=None):
            return dict.get(self, key, default)

    class _Req:
        def __init__(self) -> None:
            self.headers = _Hdrs({"User-Agent": "pytest"})

            class _Client:
                host = "127.0.0.1"

            self.client = _Client()
    return _Req()


@pytest.mark.asyncio
async def test_log_audit_event_adds_row(principal, fake_request):
    """log_audit_event must call session.add() with a SecurityAuditLog."""
    from core import audit
    from models.audit import SecurityAuditLog

    db = MagicMock()
    db.add = MagicMock()
    await audit.log_audit_event(
        db, principal, action="patient_viewed", resource_type="patient",
        resource_id="42", request=fake_request,
    )
    assert db.add.called
    row = db.add.call_args.args[0]
    assert isinstance(row, SecurityAuditLog)
    assert row.action == "patient_viewed"
    assert row.resource_type == "patient"
    assert row.resource_id == "42"
    assert row.tenant_id == principal.tenant_id
    assert row.user_email == principal.email
    assert row.success is True
    assert row.ip_address == "127.0.0.1"
    assert row.user_agent == "pytest"


@pytest.mark.asyncio
async def test_log_audit_event_records_impersonation_context(fake_request):
    """When super-admin acts on another tenant, audit metadata records both tenants."""
    from core import audit
    from models.audit import SecurityAuditLog

    acting_principal = Principal(
        user_id="sa1",
        tenant_id="22222222-2222-2222-2222-222222222222",
        email="sa@example.com",
        roles=["super_admin"],
        token_tenant_id="11111111-1111-1111-1111-111111111111",
    )

    db = MagicMock()
    db.add = MagicMock()
    await audit.log_audit_event(
        db,
        acting_principal,
        action="tenant_support_action",
        resource_type="claim",
        resource_id="99",
        request=fake_request,
    )
    row = db.add.call_args.args[0]
    assert isinstance(row, SecurityAuditLog)
    assert row.extra_data["is_impersonating"] is True
    assert row.extra_data["token_tenant_id"] == "11111111-1111-1111-1111-111111111111"
    assert row.extra_data["effective_tenant_id"] == "22222222-2222-2222-2222-222222222222"


@pytest.mark.asyncio
async def test_audit_context_logs_success(principal, fake_request):
    from core import audit

    db = MagicMock()
    db.add = MagicMock()
    async with audit.audit(db, principal, "x_action", "x_type", "1", request=fake_request):
        pass
    assert db.add.called
    assert db.add.call_args.args[0].success is True


@pytest.mark.asyncio
async def test_log_credential_access_adds_row():
    from core import audit
    from models.audit import CredentialAccessLog

    db = MagicMock()
    db.add = MagicMock()
    await audit.log_credential_access(
        db,
        tenant_id="11111111-1111-1111-1111-111111111111",
        payer_id=123,
        credential_type="sftp_password",
        action="viewed",
        reason="unit-test",
    )

    assert db.add.called
    row = db.add.call_args.args[0]
    assert isinstance(row, CredentialAccessLog)
    assert row.credential_type == "sftp_password"
    assert row.action == "viewed"
    assert row.payer_id == 123


@pytest.mark.asyncio
async def test_audit_failure_fallback_preserves_impersonation_metadata(fake_request, monkeypatch):
    """
    Failure-path control:
    when an impersonated super_admin action raises, fallback audit logging must
    preserve token/effective tenant context on the error row.
    """
    from core import audit
    from core import database as core_database
    from models.audit import SecurityAuditLog

    acting_principal = Principal(
        user_id="sa1",
        tenant_id="22222222-2222-2222-2222-222222222222",
        email="sa@example.com",
        roles=["super_admin"],
        token_tenant_id="11111111-1111-1111-1111-111111111111",
    )

    class _FallbackSession:
        def __init__(self):
            self.rows = []
            self.committed = False

        def add(self, row):
            self.rows.append(row)

        async def commit(self):
            self.committed = True

    fallback = _FallbackSession()

    @asynccontextmanager
    async def _fake_async_session_factory():
        yield fallback

    monkeypatch.setattr(core_database, "async_session_factory", _fake_async_session_factory)

    # Simulate a business transaction failure inside the audit context.
    db = MagicMock()
    db.add = MagicMock()
    with pytest.raises(RuntimeError, match="forced failure"):
        async with audit.audit(
            db,
            acting_principal,
            action="claim_submit",
            resource_type="claim",
            resource_id="999",
            request=fake_request,
        ):
            raise RuntimeError("forced failure")

    assert fallback.committed is True
    assert len(fallback.rows) == 1
    row = fallback.rows[0]
    assert isinstance(row, SecurityAuditLog)
    assert row.success is False
    assert row.error_message == "forced failure"
    assert row.extra_data["is_impersonating"] is True
    assert row.extra_data["token_tenant_id"] == "11111111-1111-1111-1111-111111111111"
    assert row.extra_data["effective_tenant_id"] == "22222222-2222-2222-2222-222222222222"


@pytest.mark.asyncio
async def test_log_audit_event_ignores_xff_without_trusted_proxy(principal, monkeypatch):
    from core import audit

    class _Req:
        headers = {"User-Agent": "pytest", "X-Forwarded-For": "203.0.113.9, 10.0.0.5"}
        client = type("Client", (), {"host": "10.0.0.5"})()

    monkeypatch.delenv("TRUSTED_PROXY_CIDRS", raising=False)
    db = MagicMock()
    db.add = MagicMock()
    await audit.log_audit_event(
        db, principal, action="patient_viewed", resource_type="patient",
        resource_id="42", request=_Req(),
    )
    row = db.add.call_args.args[0]
    assert row.ip_address == "10.0.0.5"


@pytest.mark.asyncio
async def test_log_audit_event_uses_xff_when_peer_is_trusted_proxy(principal, monkeypatch):
    from core import audit

    class _Req:
        headers = {"User-Agent": "pytest", "X-Forwarded-For": "203.0.113.9, 10.0.0.5"}
        client = type("Client", (), {"host": "10.0.0.5"})()

    monkeypatch.setenv("TRUSTED_PROXY_CIDRS", "10.0.0.0/8")
    db = MagicMock()
    db.add = MagicMock()
    await audit.log_audit_event(
        db, principal, action="patient_viewed", resource_type="patient",
        resource_id="42", request=_Req(),
    )
    row = db.add.call_args.args[0]
    assert row.ip_address == "203.0.113.9"
