from types import SimpleNamespace

import pytest

import core.tenant_config as tenant_config
import services.clearinghouse_transport as clearinghouse_transport


class _FakeResult:
    def __init__(self, row):
        self._row = row

    def scalar_one_or_none(self):
        return self._row


class _FakeDB:
    def __init__(self, rows):
        self._rows = list(rows)
        self.calls = 0

    async def execute(self, _query):
        row = self._rows[min(self.calls, len(self._rows) - 1)]
        self.calls += 1
        return _FakeResult(row)


@pytest.mark.asyncio
async def test_clearinghouse_audit_resolves_tenant_from_payer_id(monkeypatch):
    fake_db = _FakeDB(rows=["00000000-0000-0000-0000-000000000111"])
    connection = SimpleNamespace(payer_id=42)
    logged = []

    async def _fake_decrypt(_encrypted):
        return "plain-secret"

    async def _fake_log(_db, **kwargs):
        logged.append(kwargs)

    monkeypatch.setattr(clearinghouse_transport, "decrypt_credential", _fake_decrypt)
    monkeypatch.setattr(clearinghouse_transport, "log_credential_access", _fake_log)

    transport = clearinghouse_transport.SFTPTransport(fake_db)
    value_one = await transport._decrypt_with_audit(
        encrypted_value="cipher-1",
        connection=connection,
        credential_type="sftp_password",
        reason="unit_test",
    )
    value_two = await transport._decrypt_with_audit(
        encrypted_value="cipher-2",
        connection=connection,
        credential_type="sftp_password",
        reason="unit_test_cached",
    )

    assert value_one == "plain-secret"
    assert value_two == "plain-secret"
    assert logged[0]["tenant_id"] == "00000000-0000-0000-0000-000000000111"
    assert logged[0]["payer_id"] == 42
    # Second decrypt call reuses cached tenant_id on connection.
    assert fake_db.calls == 1


@pytest.mark.asyncio
async def test_sensitive_tenant_settings_do_not_fallback_to_env_by_default(monkeypatch):
    monkeypatch.setenv("SMTP_PASS", "shared-env-secret")
    fake_db = _FakeDB(rows=[SimpleNamespace(settings={})])

    value = await tenant_config.get_tenant_setting(
        fake_db,
        tenant_id="00000000-0000-0000-0000-000000000999",
        key="smtp_pass",
        default="",
    )
    override_value = await tenant_config.get_tenant_setting(
        fake_db,
        tenant_id="00000000-0000-0000-0000-000000000999",
        key="smtp_pass",
        default="",
        allow_env_fallback=True,
    )

    assert value == ""
    assert override_value == "shared-env-secret"
