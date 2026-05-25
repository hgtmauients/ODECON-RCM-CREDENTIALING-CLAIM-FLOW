"""
ClaimFlow - Async database session factory and engine configuration.
Provides `get_db` dependency and `get_async_session` generator for background jobs.
"""

import os
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from core.db_rls import set_rls_bypass, set_tenant_context

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://claimflow:claimflow@localhost:5432/claimflow",
)

engine = create_async_engine(
    DATABASE_URL,
    echo=os.getenv("SQL_ECHO", "false").lower() == "true",
    pool_size=int(os.getenv("DB_POOL_SIZE", "10")),
    max_overflow=int(os.getenv("DB_MAX_OVERFLOW", "20")),
    pool_pre_ping=True,
)

async_session_factory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency that yields a scoped async session."""
    async with async_session_factory() as session:
        try:
            # Request sessions get tenant context in auth.get_current_user once
            # token validation succeeds. Avoid forcing a DB connection here so
            # invalid-token requests can fail fast before touching the DB.
            yield session
        finally:
            await session.close()


async def get_async_session() -> AsyncGenerator[AsyncSession, None]:
    """Generator for background jobs (non-FastAPI contexts)."""
    async with async_session_factory() as session:
        try:
            # Background workers iterate across tenants and use explicit app-layer filters.
            await set_rls_bypass(session, enabled=True)
            await set_tenant_context(session, tenant_id=None)
            yield session
        finally:
            await session.close()
