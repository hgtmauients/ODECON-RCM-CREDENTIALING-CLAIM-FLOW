from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from services.rules_engine import RulesEngine


def _claim_result(claim):
    r = MagicMock()
    r.scalar_one_or_none.return_value = claim
    return r


def _scalars_result(items):
    r = MagicMock()
    scalars = MagicMock()
    scalars.all.return_value = items
    r.scalars.return_value = scalars
    return r


@pytest.mark.asyncio
async def test_validate_claim_scopes_rules_query_to_tenant():
    db = MagicMock()
    db.commit = AsyncMock()
    db.add = MagicMock()

    claim = SimpleNamespace(
        id=42,
        payer_id=7,
        flags={},
        requires_prior_auth=False,
        auth_obtained=False,
        current_queue=None,
    )
    db.execute = AsyncMock(
        side_effect=[
            _claim_result(claim),      # claim lookup
            _scalars_result([]),       # rules lookup
            _scalars_result([]),       # claim lines lookup
            _scalars_result([]),       # claim diagnoses lookup
        ]
    )

    engine = RulesEngine(db)
    result = await engine.validate_claim(42, tenant_id="00000000-0000-0000-0000-0000000000a1")

    assert result["passed"] is True
    # Execute order: claim query, rules query, lines query, diagnoses query.
    rules_stmt = db.execute.call_args_list[1].args[0]
    sql = str(rules_stmt)
    assert "JOIN payer_profiles" in sql
    assert "payer_profiles.tenant_id" in sql


@pytest.mark.asyncio
async def test_get_rules_summary_scopes_to_tenant_when_provided():
    db = MagicMock()
    db.execute = AsyncMock(side_effect=[_scalars_result([])])

    engine = RulesEngine(db)
    result = await engine.get_applicable_rules_summary(7, tenant_id="00000000-0000-0000-0000-0000000000a1")

    assert result["total_rules"] == 0
    summary_stmt = db.execute.call_args_list[0].args[0]
    sql = str(summary_stmt)
    assert "JOIN payer_profiles" in sql
    assert "payer_profiles.tenant_id" in sql
