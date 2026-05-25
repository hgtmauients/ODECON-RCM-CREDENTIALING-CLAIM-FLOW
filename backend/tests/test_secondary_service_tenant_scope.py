from unittest.mock import AsyncMock, MagicMock

import pytest

from services.denial_manager import DenialManager
from services.smart_payer_enrollment import (
    create_smart_payer_enrollment_cases,
    get_provider_eligible_payers,
)


@pytest.mark.security
@pytest.mark.asyncio
async def test_create_smart_payer_enrollment_cases_requires_tenant_id():
    db = MagicMock()
    db.execute = AsyncMock()

    result = await create_smart_payer_enrollment_cases(
        provider_id="provider-1",
        db=db,
        provider_verification_data={},
        tenant_id="",
    )

    assert result["success"] is False
    assert "tenant_id is required" in result["error"]
    db.execute.assert_not_called()


@pytest.mark.security
@pytest.mark.asyncio
async def test_get_provider_eligible_payers_requires_tenant_id():
    db = MagicMock()
    db.execute = AsyncMock()

    result = await get_provider_eligible_payers(
        provider_id="provider-1",
        db=db,
        tenant_id=None,
    )

    assert result["success"] is False
    assert "tenant_id is required" in result["error"]
    db.execute.assert_not_called()


@pytest.mark.security
@pytest.mark.asyncio
async def test_analyze_denial_trends_requires_tenant_id():
    db = MagicMock()
    db.execute = AsyncMock()
    manager = DenialManager(db)

    with pytest.raises(ValueError, match="tenant_id is required"):
        await manager.analyze_denial_trends(tenant_id="", payer_id=1)
    db.execute.assert_not_called()
