"""Secure tenant RLS bypass using role membership.

Revision ID: rcm_015
Revises: rcm_014
Create Date: 2026-05-26
"""

from alembic import op


revision = "rcm_015"
down_revision = "rcm_014"
branch_labels = None
depends_on = None


TENANT_TABLES = (
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
    "claim_lines",
    "claim_diagnoses",
    "payer_rules",
    "trading_partner_connections",
    "fee_schedules",
    "payer_profile_versions",
)

BYPASS_ROLE = "claimflow_rls_bypass"


def _create_policy(table_name: str, bypass_expr: str) -> None:
    op.execute(f'DROP POLICY IF EXISTS tenant_isolation_policy ON "{table_name}"')
    op.execute(
        f"""
        CREATE POLICY tenant_isolation_policy ON "{table_name}"
        USING (
            {bypass_expr}
            OR tenant_id::text = current_setting('app.tenant_id', true)
        )
        WITH CHECK (
            {bypass_expr}
            OR tenant_id::text = current_setting('app.tenant_id', true)
        )
        """
    )
    op.execute(f'ALTER TABLE "{table_name}" ENABLE ROW LEVEL SECURITY')
    op.execute(f'ALTER TABLE "{table_name}" FORCE ROW LEVEL SECURITY')


def upgrade() -> None:
    op.execute(
        f"""
        DO $$
        BEGIN
          IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{BYPASS_ROLE}') THEN
            CREATE ROLE {BYPASS_ROLE} NOLOGIN;
          END IF;
        END
        $$;
        """
    )
    bypass_expr = f"pg_has_role(current_user, '{BYPASS_ROLE}', 'member')"
    for table_name in TENANT_TABLES:
        _create_policy(table_name, bypass_expr)


def downgrade() -> None:
    bypass_expr = "current_setting('app.bypass_rls', true) = '1'"
    for table_name in TENANT_TABLES:
        _create_policy(table_name, bypass_expr)
    op.execute(f"DROP ROLE IF EXISTS {BYPASS_ROLE}")
