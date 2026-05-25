from unittest.mock import AsyncMock, MagicMock

import pytest

from services.denial_manager import AutoPostingEngine, DenialManager


@pytest.mark.asyncio
async def test_process_835_denials_requires_tenant_id():
    db = MagicMock()
    db.rollback = AsyncMock()
    db.commit = AsyncMock()
    db.execute = AsyncMock()
    manager = DenialManager(db)

    with pytest.raises(ValueError, match="tenant_id is required"):
        await manager.process_835_denials(edi_file_id=1, denials_data=[], tenant_id="")
    db.rollback.assert_called_once()
    db.execute.assert_not_called()


@pytest.mark.asyncio
async def test_auto_post_835_requires_tenant_id():
    db = MagicMock()
    db.rollback = AsyncMock()
    db.commit = AsyncMock()
    db.execute = AsyncMock()
    poster = AutoPostingEngine(db)

    with pytest.raises(ValueError, match="tenant_id is required"):
        await poster.auto_post_835(edi_file_id=1, payments_data=[], tenant_id="")
    db.rollback.assert_called_once()
    db.execute.assert_not_called()


@pytest.mark.asyncio
async def test_generate_appeal_requires_tenant_id():
    db = MagicMock()
    db.execute = AsyncMock()
    manager = DenialManager(db)

    with pytest.raises(ValueError, match="tenant_id is required"):
        await manager.generate_appeal(denial_case_id=1, tenant_id="")
    db.execute.assert_not_called()
