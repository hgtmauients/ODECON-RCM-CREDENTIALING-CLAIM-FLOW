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
            yield session
        finally:
            await session.close()


async def get_async_session() -> AsyncGenerator[AsyncSession, None]:
    """Generator for background jobs (non-FastAPI contexts)."""
    async with async_session_factory() as session:
        try:
            yield session
        finally:
            await session.close()
