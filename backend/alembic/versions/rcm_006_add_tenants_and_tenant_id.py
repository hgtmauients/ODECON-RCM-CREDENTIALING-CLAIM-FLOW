"""Add tenants table and tenant_id to all domain models

Revision ID: rcm_006
Revises: 017
Create Date: 2026-04-20 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = 'rcm_006'
down_revision = '017'
branch_labels = None
depends_on = None

DEFAULT_TENANT_ID = '00000000-0000-0000-0000-000000000001'


def upgrade() -> None:
    # --- Create tenants table ---
    op.create_table(
        'tenants',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('slug', sa.String(length=128), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('settings', postgresql.JSONB(), server_default=sa.text("'{}'::jsonb")),
        sa.Column('created_by', sa.String(length=255)),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        sa.Column('npi', sa.String(length=10)),
        sa.Column('tax_id', sa.String(length=20)),
        sa.Column('address_line_1', sa.String(length=255)),
        sa.Column('address_line_2', sa.String(length=255)),
        sa.Column('city', sa.String(length=128)),
        sa.Column('state', sa.String(length=2)),
        sa.Column('zip_code', sa.String(length=10)),
        sa.Column('phone', sa.String(length=20)),
        sa.Column('billing_contact_email', sa.String(length=255)),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_tenants_slug', 'tenants', ['slug'], unique=True)

    # Insert default tenant for backfill
    op.execute(
        f"INSERT INTO tenants (id, name, slug) VALUES ('{DEFAULT_TENANT_ID}', 'Default Tenant', 'default')"
    )

    # --- Add tenant_id to claims ---
    op.add_column('claims', sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=True))
    op.execute(f"UPDATE claims SET tenant_id = '{DEFAULT_TENANT_ID}' WHERE tenant_id IS NULL")
    op.alter_column('claims', 'tenant_id', nullable=False)
    op.create_index('ix_claims_tenant_id', 'claims', ['tenant_id'])
    op.create_index('ix_claims_tenant_state', 'claims', ['tenant_id', 'state'])
    op.create_index('ix_claims_tenant_service_date', 'claims', ['tenant_id', 'service_date_from'])
    # Replace global unique on claim_number with tenant-scoped unique
    # Historical schemas may represent this uniqueness as either a constraint
    # or an index depending on creation path; drop both variants defensively.
    op.execute('ALTER TABLE claims DROP CONSTRAINT IF EXISTS claims_claim_number_key')
    op.execute('DROP INDEX IF EXISTS ix_claims_claim_number')
    op.create_index('ix_claims_tenant_claim_number', 'claims', ['tenant_id', 'claim_number'], unique=True)

    # --- Add tenant_id to edi_files ---
    op.add_column('edi_files', sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=True))
    op.execute(f"UPDATE edi_files SET tenant_id = '{DEFAULT_TENANT_ID}' WHERE tenant_id IS NULL")
    op.alter_column('edi_files', 'tenant_id', nullable=False)
    op.create_index('ix_edi_files_tenant_id', 'edi_files', ['tenant_id'])

    # --- Add tenant_id to claim_queues ---
    op.add_column('claim_queues', sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=True))
    op.execute(f"UPDATE claim_queues SET tenant_id = '{DEFAULT_TENANT_ID}' WHERE tenant_id IS NULL")
    op.alter_column('claim_queues', 'tenant_id', nullable=False)
    op.create_index('ix_claim_queues_tenant_id', 'claim_queues', ['tenant_id'])
    op.execute('ALTER TABLE claim_queues DROP CONSTRAINT IF EXISTS claim_queues_name_key')
    op.execute('DROP INDEX IF EXISTS ix_claim_queues_name')
    op.create_index('ix_claim_queues_tenant_name', 'claim_queues', ['tenant_id', 'name'], unique=True)

    # --- Add tenant_id to payer_profiles ---
    op.add_column('payer_profiles', sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=True))
    op.execute(f"UPDATE payer_profiles SET tenant_id = '{DEFAULT_TENANT_ID}' WHERE tenant_id IS NULL")
    op.alter_column('payer_profiles', 'tenant_id', nullable=False)
    op.create_index('ix_payer_profiles_tenant_id', 'payer_profiles', ['tenant_id'])
    op.create_index('ix_payer_profiles_tenant_name', 'payer_profiles', ['tenant_id', 'name'])

    # --- Add tenant_id to denial_cases ---
    op.add_column('denial_cases', sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=True))
    op.execute(f"UPDATE denial_cases SET tenant_id = '{DEFAULT_TENANT_ID}' WHERE tenant_id IS NULL")
    op.alter_column('denial_cases', 'tenant_id', nullable=False)
    op.create_index('ix_denial_cases_tenant_id', 'denial_cases', ['tenant_id'])
    op.create_index('ix_denial_cases_tenant_status', 'denial_cases', ['tenant_id', 'status'])

    # --- Add tenant_id to denial_playbooks ---
    op.add_column('denial_playbooks', sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=True))
    op.execute(f"UPDATE denial_playbooks SET tenant_id = '{DEFAULT_TENANT_ID}' WHERE tenant_id IS NULL")
    op.alter_column('denial_playbooks', 'tenant_id', nullable=False)
    op.create_index('ix_denial_playbooks_tenant_id', 'denial_playbooks', ['tenant_id'])

    # --- Add tenant_id to appeal_templates ---
    op.add_column('appeal_templates', sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=True))
    op.execute(f"UPDATE appeal_templates SET tenant_id = '{DEFAULT_TENANT_ID}' WHERE tenant_id IS NULL")
    op.alter_column('appeal_templates', 'tenant_id', nullable=False)
    op.create_index('ix_appeal_templates_tenant_id', 'appeal_templates', ['tenant_id'])

    # --- Add tenant_id to payer_credentialing_cases ---
    op.add_column('payer_credentialing_cases', sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=True))
    op.execute(f"UPDATE payer_credentialing_cases SET tenant_id = '{DEFAULT_TENANT_ID}' WHERE tenant_id IS NULL")
    op.alter_column('payer_credentialing_cases', 'tenant_id', nullable=False)
    op.create_index('ix_payer_cred_cases_tenant_id', 'payer_credentialing_cases', ['tenant_id'])
    op.create_index('ix_payer_cred_cases_tenant_status', 'payer_credentialing_cases', ['tenant_id', 'status'])

    # --- Add tenant_id to era_enrollment_cases ---
    op.add_column('era_enrollment_cases', sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=True))
    op.execute(f"UPDATE era_enrollment_cases SET tenant_id = '{DEFAULT_TENANT_ID}' WHERE tenant_id IS NULL")
    op.alter_column('era_enrollment_cases', 'tenant_id', nullable=False)
    op.create_index('ix_era_enrollment_cases_tenant_id', 'era_enrollment_cases', ['tenant_id'])

    # --- Add tenant_id to provider_documents ---
    op.add_column('provider_documents', sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=True))
    op.execute(f"UPDATE provider_documents SET tenant_id = '{DEFAULT_TENANT_ID}' WHERE tenant_id IS NULL")
    op.alter_column('provider_documents', 'tenant_id', nullable=False)
    op.create_index('ix_provider_documents_tenant_id', 'provider_documents', ['tenant_id'])

    # --- Add tenant_id to credentialing_renewals ---
    op.add_column('credentialing_renewals', sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=True))
    op.execute(f"UPDATE credentialing_renewals SET tenant_id = '{DEFAULT_TENANT_ID}' WHERE tenant_id IS NULL")
    op.alter_column('credentialing_renewals', 'tenant_id', nullable=False)
    op.create_index('ix_credentialing_renewals_tenant_id', 'credentialing_renewals', ['tenant_id'])

    # --- Add tenant_id to provider_credentialing ---
    op.add_column('provider_credentialing', sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=True))
    op.execute(f"UPDATE provider_credentialing SET tenant_id = '{DEFAULT_TENANT_ID}' WHERE tenant_id IS NULL")
    op.alter_column('provider_credentialing', 'tenant_id', nullable=False)
    op.create_index('ix_provider_credentialing_tenant_id', 'provider_credentialing', ['tenant_id'])
    op.execute('ALTER TABLE provider_credentialing DROP CONSTRAINT IF EXISTS provider_credentialing_provider_id_key')
    op.execute('DROP INDEX IF EXISTS ix_provider_credentialing_provider_id')
    op.create_index('ix_provider_cred_tenant_provider', 'provider_credentialing', ['tenant_id', 'provider_id'], unique=True)

    # --- Add tenant_id to credentialing_verification_log ---
    op.add_column('credentialing_verification_log', sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=True))
    op.execute(f"UPDATE credentialing_verification_log SET tenant_id = '{DEFAULT_TENANT_ID}' WHERE tenant_id IS NULL")
    op.alter_column('credentialing_verification_log', 'tenant_id', nullable=False)
    op.create_index('ix_cred_verification_log_tenant_id', 'credentialing_verification_log', ['tenant_id'])

    # --- Add tenant_id to credential_access_log ---
    op.add_column('credential_access_log', sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=True))
    op.execute(f"UPDATE credential_access_log SET tenant_id = '{DEFAULT_TENANT_ID}' WHERE tenant_id IS NULL")
    op.alter_column('credential_access_log', 'tenant_id', nullable=False)
    op.create_index('ix_credential_access_log_tenant_id', 'credential_access_log', ['tenant_id'])

    # --- Add tenant_id to security_audit_log ---
    op.add_column('security_audit_log', sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=True))
    op.execute(f"UPDATE security_audit_log SET tenant_id = '{DEFAULT_TENANT_ID}' WHERE tenant_id IS NULL")
    op.alter_column('security_audit_log', 'tenant_id', nullable=False)
    op.create_index('ix_security_audit_log_tenant_id', 'security_audit_log', ['tenant_id'])

    # --- Add tenant_id to mfa_attempts ---
    op.add_column('mfa_attempts', sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=True))
    op.execute(f"UPDATE mfa_attempts SET tenant_id = '{DEFAULT_TENANT_ID}' WHERE tenant_id IS NULL")
    op.alter_column('mfa_attempts', 'tenant_id', nullable=False)
    op.create_index('ix_mfa_attempts_tenant_id', 'mfa_attempts', ['tenant_id'])


def downgrade() -> None:
    tables_with_tenant = [
        'mfa_attempts', 'security_audit_log', 'credential_access_log',
        'credentialing_verification_log', 'provider_credentialing',
        'credentialing_renewals', 'provider_documents', 'era_enrollment_cases',
        'payer_credentialing_cases', 'appeal_templates', 'denial_playbooks',
        'denial_cases', 'payer_profiles', 'claim_queues', 'edi_files', 'claims',
    ]
    for table in tables_with_tenant:
        op.drop_column(table, 'tenant_id')

    # Restore original unique indexes as defined in prior revisions.
    op.create_index('ix_claims_claim_number', 'claims', ['claim_number'], unique=True)
    op.create_index('ix_claim_queues_name', 'claim_queues', ['name'], unique=True)
    op.create_index('ix_provider_credentialing_provider_id', 'provider_credentialing', ['provider_id'], unique=True)

    op.drop_table('tenants')
