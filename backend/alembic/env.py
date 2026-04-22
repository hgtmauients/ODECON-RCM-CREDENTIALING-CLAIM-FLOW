"""
Alembic env.py for ClaimFlow.
Supports async PostgreSQL via asyncpg.
"""

import asyncio
import os
import sys
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models.base import Base
from models.tenant import Tenant
from models.patient import Patient
from models.claims import Claim, ClaimLine, ClaimDiagnosis, ClaimEvent, EDIFile, ClaimQueue, ClaimValidation
from models.rcm import PayerProfile, PayerRule, TradingPartnerConnection, PayerCredential, FeeSchedule, PayerProfileVersion
from models.denials import DenialCase, DenialPlaybook, AppealTemplate, CARCCode, RARCCode
from models.payer_credentialing import PayerCredentialingCase, ERAEnrollmentCase, ProviderDocument, CredentialingRenewal
from models.credentialing import ProviderCredentialing, CredentialingVerificationLog
from models.audit import CredentialAccessLog, SecurityAuditLog, MFAAttempt
from models.code_library import ICD10Code, CPTCode

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

db_url = os.getenv("DATABASE_URL", config.get_main_option("sqlalchemy.url"))
if db_url:
    config.set_main_option("sqlalchemy.url", db_url)


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Run migrations in 'online' mode with async engine."""
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
