"""Enable tenant RLS policies on tenant-owned tables.

Revision ID: rcm_013
Revises: rcm_012
Create Date: 2026-05-25
"""

from alembic import op
from sqlalchemy import text

# revision identifiers, used by Alembic.
revision = "rcm_013"
down_revision = "rcm_012"
branch_labels = None
depends_on = None


TENANT_TABLES = [
    "users",
    "notifications",
    "patients",
    "claims",
    "edi_files",
    "claim_queues",
    "claim_validations",
    "denial_cases",
    "denial_playbooks",
    "appeal_templates",
    "payer_profiles",
    "payer_credentialing_cases",
    "era_enrollment_cases",
    "provider_documents",
    "credentialing_renewals",
    "provider_credentialing",
    "credentialing_verification_log",
    "credential_access_log",
    "security_audit_log",
    "mfa_attempts",
]


def _table_has_tenant_id(table_name: str) -> bool:
    bind = op.get_bind()
    result = bind.execute(
        text(
            """
            SELECT 1
            FROM information_schema.columns
            WHERE table_schema = current_schema()
              AND table_name = :table_name
              AND column_name = 'tenant_id'
            """
        ),
        {"table_name": table_name},
    ).scalar()
    return bool(result)


def _enable_rls_for_table(table_name: str) -> None:
    if not _table_has_tenant_id(table_name):
        return
    op.execute(f'ALTER TABLE "{table_name}" ENABLE ROW LEVEL SECURITY')
    op.execute(f'DROP POLICY IF EXISTS tenant_isolation_policy ON "{table_name}"')
    op.execute(
        f"""
        CREATE POLICY tenant_isolation_policy ON "{table_name}"
        USING (
            current_setting('app.bypass_rls', true) = '1'
            OR tenant_id::text = current_setting('app.tenant_id', true)
        )
        WITH CHECK (
            current_setting('app.bypass_rls', true) = '1'
            OR tenant_id::text = current_setting('app.tenant_id', true)
        )
        """
    )
    op.execute(f'ALTER TABLE "{table_name}" FORCE ROW LEVEL SECURITY')


def _disable_rls_for_table(table_name: str) -> None:
    if not _table_has_tenant_id(table_name):
        return
    op.execute(f'DROP POLICY IF EXISTS tenant_isolation_policy ON "{table_name}"')
    op.execute(f'ALTER TABLE "{table_name}" NO FORCE ROW LEVEL SECURITY')
    op.execute(f'ALTER TABLE "{table_name}" DISABLE ROW LEVEL SECURITY')


def upgrade() -> None:
    for table_name in TENANT_TABLES:
        _enable_rls_for_table(table_name)


def downgrade() -> None:
    for table_name in TENANT_TABLES:
        _disable_rls_for_table(table_name)
