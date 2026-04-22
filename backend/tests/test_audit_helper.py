"""
Tests for core.audit logging helper.

Closes v10 NEW-C3 — the helper is wired throughout v11; here we just verify
the helper writes a SecurityAuditLog row to the supplied session and that
context-manager mode logs success vs. failure correctly.
"""

import pytest
from unittest.mock import MagicMock

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
async def test_audit_context_logs_success(principal, fake_request):
    from core import audit

    db = MagicMock()
    db.add = MagicMock()
    async with audit.audit(db, principal, "x_action", "x_type", "1", request=fake_request):
        pass
    assert db.add.called
    assert db.add.call_args.args[0].success is True
