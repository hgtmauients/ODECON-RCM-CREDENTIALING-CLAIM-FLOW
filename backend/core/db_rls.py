"""
Helpers for PostgreSQL tenant RLS session context.
"""

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def set_rls_bypass(session: AsyncSession, enabled: bool) -> None:
    value = "1" if enabled else "0"
    await session.execute(
        text("SELECT set_config('app.bypass_rls', :value, false)"),
        {"value": value},
    )


async def set_tenant_context(session: AsyncSession, tenant_id: str | None) -> None:
    await session.execute(
        text("SELECT set_config('app.tenant_id', :tenant_id, false)"),
        {"tenant_id": tenant_id or ""},
    )
