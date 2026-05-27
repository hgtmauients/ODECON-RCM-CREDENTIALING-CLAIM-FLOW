"""
Helpers for PostgreSQL tenant RLS session context.
"""

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def set_rls_bypass(session: AsyncSession, enabled: bool) -> None:
    value = "1" if enabled else "0"
    stmt = text("SELECT set_config('app.bypass_rls', :value, false)")
    try:
        await session.execute(stmt, {"value": value})
    except TypeError:
        # Some test doubles only support execute(statement).
        await session.execute(stmt.bindparams(value=value))


async def set_tenant_context(session: AsyncSession, tenant_id: str | None) -> None:
    stmt = text("SELECT set_config('app.tenant_id', :tenant_id, false)")
    value = tenant_id or ""
    try:
        await session.execute(stmt, {"tenant_id": value})
    except TypeError:
        # Some test doubles only support execute(statement).
        await session.execute(stmt.bindparams(tenant_id=value))


async def reset_rls_context(session: AsyncSession) -> None:
    """Reset tenant-scoped PostgreSQL session state before returning pooled connections."""
    await set_rls_bypass(session, enabled=False)
    await set_tenant_context(session, tenant_id=None)
