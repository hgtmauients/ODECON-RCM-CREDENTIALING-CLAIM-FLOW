from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from api.rcm import payer_profiles

pytestmark = pytest.mark.security


class _DenyPrincipal:
    tenant_id = "00000000-0000-0000-0000-000000000001"

    def require_role(self, role: str) -> None:
        raise HTTPException(status_code=403, detail=f"Role '{role}' required")


@pytest.mark.asyncio
async def test_list_payers_enforces_billing_role():
    db = MagicMock()
    db.execute = AsyncMock()
    with pytest.raises(HTTPException) as exc:
        await payer_profiles.list_payers(db=db, current_user=_DenyPrincipal())
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_get_payer_enforces_billing_role():
    db = MagicMock()
    db.execute = AsyncMock()
    with pytest.raises(HTTPException) as exc:
        await payer_profiles.get_payer(1, db=db, current_user=_DenyPrincipal())
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_get_payer_rules_enforces_billing_role():
    db = MagicMock()
    db.execute = AsyncMock()
    with pytest.raises(HTTPException) as exc:
        await payer_profiles.get_payer_rules(1, db=db, current_user=_DenyPrincipal())
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_list_all_fee_schedules_enforces_billing_role():
    db = MagicMock()
    db.execute = AsyncMock()
    with pytest.raises(HTTPException) as exc:
        await payer_profiles.list_all_fee_schedules(db=db, current_user=_DenyPrincipal())
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_get_payer_versions_enforces_billing_role():
    db = MagicMock()
    db.execute = AsyncMock()
    with pytest.raises(HTTPException) as exc:
        await payer_profiles.get_payer_versions(1, db=db, current_user=_DenyPrincipal())
    assert exc.value.status_code == 403
