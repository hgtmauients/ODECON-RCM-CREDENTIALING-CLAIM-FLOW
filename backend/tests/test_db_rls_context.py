import pytest

from core.db_rls import set_rls_bypass, set_tenant_context


class _FakeSession:
    def __init__(self):
        self.calls = []

    async def execute(self, statement, params=None):
        self.calls.append((str(statement), params or {}))


@pytest.mark.asyncio
async def test_set_rls_bypass_sets_expected_config():
    session = _FakeSession()
    await set_rls_bypass(session, enabled=True)
    await set_rls_bypass(session, enabled=False)

    assert session.calls[0][1]["value"] == "1"
    assert session.calls[1][1]["value"] == "0"


@pytest.mark.asyncio
async def test_set_tenant_context_sets_tenant_id_or_empty():
    session = _FakeSession()
    await set_tenant_context(session, tenant_id="00000000-0000-0000-0000-000000000123")
    await set_tenant_context(session, tenant_id=None)

    assert session.calls[0][1]["tenant_id"] == "00000000-0000-0000-0000-000000000123"
    assert session.calls[1][1]["tenant_id"] == ""
