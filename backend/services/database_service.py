"""
ClaimFlow - Database service abstraction.
Provides helper operations previously provided by the host platform.
In ClaimFlow standalone mode this is a thin wrapper; the credentialing
API no longer depends on a host "create_provider" call.
"""

import logging
from typing import Dict, Any, Optional
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession
from core.database import get_db

logger = logging.getLogger(__name__)


class DatabaseService:
    """Lightweight service for provider/entity management."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_provider(self, org_id: str, provider_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Create or update a provider entity.
        In standalone ClaimFlow this is a no-op placeholder; provider management
        happens through the credentialing models directly.
        """
        logger.info(f"Provider creation requested: {provider_data.get('provider_id')} for org {org_id}")
        return {"success": True, "provider_id": provider_data.get("provider_id")}


async def get_database_service(db: AsyncSession = Depends(get_db)) -> DatabaseService:
    return DatabaseService(db)
