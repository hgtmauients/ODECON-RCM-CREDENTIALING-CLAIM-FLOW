"""
Helpers for PostgreSQL tenant RLS session context.
"""

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def set_rls_bypass(session: AsyncSession, enabled: bool) -> None:
    value = "1" if enabled else "0"
    stmt = text("SELECT set_config('app.bypass_rls', :value, false)").bindparams(value=value)
    await session.execute(stmt)


async def set_tenant_context(session: AsyncSession, tenant_id: str | None) -> None:
    stmt = text("SELECT set_config('app.tenant_id', :tenant_id, false)").bindparams(tenant_id=tenant_id or "")
    await session.execute(stmt)


async def reset_rls_context(session: AsyncSession) -> None:
    """Reset tenant-scoped PostgreSQL session state before returning pooled connections."""
    await set_rls_bypass(session, enabled=False)
    await set_tenant_context(session, tenant_id=None)
