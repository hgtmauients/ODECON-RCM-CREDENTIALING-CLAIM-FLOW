"""Add payer profiles and RCM infrastructure

Revision ID: rcm_001
Revises: (depends on your last migration)
Create Date: 2024-01-01 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'rcm_001'
down_revision = None  # Update this to point to your last migration
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create payer_profiles table
    op.create_table(
        'payer_profiles',
        sa.Column('id', sa.Integer(), nullable=False),
        
        # Identity
        sa.Column('name', sa.String(length=200), nullable=False),
        sa.Column('display_name', sa.String(length=200)),
        sa.Column('payer_id', sa.String(length=50)),
        sa.Column('naic_code', sa.String(length=20)),
        sa.Column('plan_ids', postgresql.JSON(astext_type=sa.Text())),
        
        # Connectivity
        sa.Column('clearinghouse', sa.String(length=100)),
        sa.Column('trading_partner_id', sa.String(length=50)),
        sa.Column('submitter_id', sa.String(length=50)),
        sa.Column('receiver_id', sa.String(length=50)),
        sa.Column('connection_method', sa.String(length=50)),
        sa.Column('endpoint_url', sa.String(length=500)),
        
        # Formats & Rules
        sa.Column('format_837_type', sa.String(length=10)),
        sa.Column('loop_segment_overrides', postgresql.JSON(astext_type=sa.Text())),
        sa.Column('supports_pwk_attachments', sa.Boolean(), server_default='false'),
        sa.Column('attachment_method', sa.String(length=50)),
        
        # Telehealth
        sa.Column('supports_telehealth', sa.Boolean(), server_default='false'),
        sa.Column('telehealth_modifiers', postgresql.JSON(astext_type=sa.Text())),
        sa.Column('telehealth_pos_codes', postgresql.JSON(astext_type=sa.Text())),
        sa.Column('telehealth_parity', sa.Boolean(), server_default='false'),
        
        # Requirements
        sa.Column('requires_taxonomy', sa.Boolean(), server_default='true'),
        sa.Column('requires_npi_type_2', sa.Boolean(), server_default='false'),
        sa.Column('requires_tin', sa.Boolean(), server_default='true'),
        sa.Column('requires_clia', sa.Boolean(), server_default='false'),
        sa.Column('facility_professional_split', sa.String(length=50)),
        
        # Eligibility/Status/Auth
        sa.Column('supports_270_271', sa.Boolean(), server_default='true'),
        sa.Column('supports_276_277', sa.Boolean(), server_default='true'),
        sa.Column('supports_278_auth', sa.Boolean(), server_default='false'),
        sa.Column('auth_portal_url', sa.String(length=500)),
        sa.Column('auth_portal_login_required', sa.Boolean(), server_default='false'),
        
        # ERA/EFT
        sa.Column('supports_835_era', sa.Boolean(), server_default='true'),
        sa.Column('era_enrollment_required', sa.Boolean(), server_default='true'),
        sa.Column('era_enrollment_url', sa.String(length=500)),
        sa.Column('era_enrollment_forms', postgresql.JSON(astext_type=sa.Text())),
        sa.Column('eft_enrollment_required', sa.Boolean(), server_default='false'),
        sa.Column('eft_enrollment_url', sa.String(length=500)),
        sa.Column('eft_banking_docs', postgresql.JSON(astext_type=sa.Text())),
        
        # SLAs & Deadlines
        sa.Column('filing_limit_days', sa.Integer(), server_default='365'),
        sa.Column('filing_limit_from', sa.String(length=50), server_default='service_date'),
        sa.Column('auth_response_days', sa.Integer(), server_default='14'),
        sa.Column('appeal_window_days', sa.Integer(), server_default='180'),
        sa.Column('audit_response_days', sa.Integer(), server_default='14'),
        
        # Contract Info
        sa.Column('has_contract', sa.Boolean(), server_default='false'),
        sa.Column('contract_type', sa.String(length=50)),
        sa.Column('contract_effective_date', sa.Date()),
        sa.Column('contract_end_date', sa.Date()),
        sa.Column('contract_notes', sa.Text()),
        
        # Claim Frequency Codes
        sa.Column('supports_corrected_claims', sa.Boolean(), server_default='true'),
        sa.Column('corrected_claim_frequency_code', sa.String(length=5), server_default='7'),
        sa.Column('void_claim_frequency_code', sa.String(length=5), server_default='8'),
        sa.Column('accepts_secondary_claims', sa.Boolean(), server_default='true'),
        sa.Column('secondary_claim_requirements', postgresql.JSON(astext_type=sa.Text())),
        
        # Paper Fallback
        sa.Column('paper_claim_supported', sa.Boolean(), server_default='true'),
        sa.Column('paper_claim_address', sa.Text()),
        sa.Column('paper_claim_fax', sa.String(length=50)),
        
        # Notifications
        sa.Column('notification_rules', postgresql.JSON(astext_type=sa.Text())),
        sa.Column('escalation_rules', postgresql.JSON(astext_type=sa.Text())),
        
        # State-specific
        sa.Column('state_code', sa.String(length=2)),
        sa.Column('state_specific_requirements', postgresql.JSON(astext_type=sa.Text())),
        
        # Metadata
        sa.Column('is_active', sa.Boolean(), server_default='true'),
        sa.Column('version', sa.Integer(), server_default='1'),
        sa.Column('is_draft', sa.Boolean(), server_default='true'),
        sa.Column('published_at', sa.DateTime(timezone=True)),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), onupdate=sa.text('now()')),
        sa.Column('created_by', sa.String(length=100)),
        sa.Column('updated_by', sa.String(length=100)),
        sa.Column('notes', sa.Text()),
        
        sa.PrimaryKeyConstraint('id')
    )
    
    # Create indexes for payer_profiles
    op.create_index('ix_payer_profiles_name', 'payer_profiles', ['name'])
    op.create_index('ix_payer_profiles_payer_id', 'payer_profiles', ['payer_id'])
    op.create_index('ix_payer_profiles_state_code', 'payer_profiles', ['state_code'])
    op.create_index('ix_payer_profiles_is_active', 'payer_profiles', ['is_active'])
    op.create_index('ix_payer_profiles_created_at', 'payer_profiles', ['created_at'])

    # Create payer_rules table
    op.create_table(
        'payer_rules',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('payer_id', sa.Integer(), nullable=False),
        sa.Column('rule_name', sa.String(length=200), nullable=False),
        sa.Column('description', sa.Text()),
        sa.Column('priority', sa.Integer(), server_default='0'),
        sa.Column('conditions', postgresql.JSON(astext_type=sa.Text()), nullable=False),
        sa.Column('actions', postgresql.JSON(astext_type=sa.Text()), nullable=False),
        sa.Column('is_active', sa.Boolean(), server_default='true'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), onupdate=sa.text('now()')),
        sa.Column('created_by', sa.String(length=100)),
        sa.Column('updated_by', sa.String(length=100)),
        
        sa.ForeignKeyConstraint(['payer_id'], ['payer_profiles.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    
    op.create_index('ix_payer_rules_payer_id', 'payer_rules', ['payer_id'])
    op.create_index('ix_payer_rules_is_active', 'payer_rules', ['is_active'])

    # Create trading_partner_connections table
    op.create_table(
        'trading_partner_connections',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('payer_id', sa.Integer(), nullable=False),
        sa.Column('connection_name', sa.String(length=200)),
        sa.Column('clearinghouse_name', sa.String(length=100)),
        sa.Column('connection_type', sa.String(length=50)),
        
        # SFTP
        sa.Column('sftp_host', sa.String(length=200)),
        sa.Column('sftp_port', sa.Integer(), server_default='22'),
        sa.Column('sftp_username', sa.String(length=100)),
        sa.Column('sftp_password_encrypted', sa.Text()),
        sa.Column('sftp_private_key_encrypted', sa.Text()),
        sa.Column('sftp_inbound_path', sa.String(length=500)),
        sa.Column('sftp_outbound_path', sa.String(length=500)),
        
        # API
        sa.Column('api_endpoint', sa.String(length=500)),
        sa.Column('api_version', sa.String(length=50)),
        sa.Column('api_key_encrypted', sa.Text()),
        sa.Column('api_secret_encrypted', sa.Text()),
        sa.Column('api_token_encrypted', sa.Text()),
        sa.Column('api_auth_method', sa.String(length=50)),
        sa.Column('oauth2_client_id', sa.String(length=200)),
        sa.Column('oauth2_client_secret_encrypted', sa.Text()),
        sa.Column('oauth2_token_url', sa.String(length=500)),
        sa.Column('oauth2_scope', sa.String(length=500)),
        
        # Portal
        sa.Column('portal_url', sa.String(length=500)),
        sa.Column('portal_username', sa.String(length=100)),
        sa.Column('portal_password_encrypted', sa.Text()),
        sa.Column('portal_requires_mfa', sa.Boolean(), server_default='false'),
        sa.Column('portal_rpa_script_id', sa.String(length=100)),
        
        # File naming
        sa.Column('file_name_pattern', sa.String(length=200)),
        sa.Column('file_extension', sa.String(length=10), server_default='.x12'),
        sa.Column('use_compression', sa.Boolean(), server_default='false'),
        sa.Column('compression_type', sa.String(length=20)),
        
        # Metadata
        sa.Column('is_active', sa.Boolean(), server_default='true'),
        sa.Column('last_tested', sa.DateTime()),
        sa.Column('last_test_status', sa.String(length=50)),
        sa.Column('last_test_message', sa.Text()),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), onupdate=sa.text('now()')),
        sa.Column('created_by', sa.String(length=100)),
        
        sa.ForeignKeyConstraint(['payer_id'], ['payer_profiles.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    
    op.create_index('ix_trading_partner_connections_payer_id', 'trading_partner_connections', ['payer_id'])

    # Create payer_credentials table
    op.create_table(
        'payer_credentials',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('payer_id', sa.Integer(), nullable=False),
        sa.Column('credential_type', sa.String(length=50)),
        sa.Column('credential_name', sa.String(length=200)),
        sa.Column('encrypted_data', sa.Text(), nullable=False),
        sa.Column('encryption_key_id', sa.String(length=100)),
        sa.Column('encryption_algorithm', sa.String(length=50), server_default='AES-256-GCM'),
        sa.Column('expires_at', sa.DateTime()),
        sa.Column('rotation_required', sa.Boolean(), server_default='false'),
        sa.Column('rotation_frequency_days', sa.Integer()),
        sa.Column('last_rotated', sa.DateTime()),
        sa.Column('is_active', sa.Boolean(), server_default='true'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), onupdate=sa.text('now()')),
        sa.Column('created_by', sa.String(length=100)),
        
        sa.ForeignKeyConstraint(['payer_id'], ['payer_profiles.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    
    op.create_index('ix_payer_credentials_payer_id', 'payer_credentials', ['payer_id'])

    # Create fee_schedules table
    op.create_table(
        'fee_schedules',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('payer_id', sa.Integer(), nullable=False),
        sa.Column('state_code', sa.String(length=2)),
        sa.Column('locality', sa.String(length=20)),
        sa.Column('cpt_code', sa.String(length=10), nullable=False),
        sa.Column('description', sa.Text()),
        sa.Column('allowable_amount', sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column('facility_rate', sa.Numeric(precision=10, scale=2)),
        sa.Column('non_facility_rate', sa.Numeric(precision=10, scale=2)),
        sa.Column('effective_date', sa.Date(), nullable=False),
        sa.Column('end_date', sa.Date()),
        sa.Column('modifier_adjustments', postgresql.JSON(astext_type=sa.Text())),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), onupdate=sa.text('now()')),
        sa.Column('uploaded_by', sa.String(length=100)),
        sa.Column('upload_batch_id', sa.String(length=100)),
        
        sa.ForeignKeyConstraint(['payer_id'], ['payer_profiles.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    
    op.create_index('ix_fee_schedules_payer_id', 'fee_schedules', ['payer_id'])
    op.create_index('ix_fee_schedules_state_code', 'fee_schedules', ['state_code'])
    op.create_index('ix_fee_schedules_cpt_code', 'fee_schedules', ['cpt_code'])
    op.create_index('ix_fee_schedules_effective_date', 'fee_schedules', ['effective_date'])

    # Create payer_profile_versions table
    op.create_table(
        'payer_profile_versions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('payer_id', sa.Integer(), nullable=False),
        sa.Column('version_number', sa.Integer(), nullable=False),
        sa.Column('profile_data', postgresql.JSON(astext_type=sa.Text()), nullable=False),
        sa.Column('change_summary', sa.Text()),
        sa.Column('changed_by', sa.String(length=100)),
        sa.Column('changed_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        sa.Column('is_published', sa.Boolean(), server_default='false'),
        sa.Column('published_at', sa.DateTime()),
        sa.Column('published_by', sa.String(length=100)),
        
        sa.ForeignKeyConstraint(['payer_id'], ['payer_profiles.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    
    op.create_index('ix_payer_profile_versions_payer_id', 'payer_profile_versions', ['payer_id'])
    op.create_index('ix_payer_profile_versions_changed_at', 'payer_profile_versions', ['changed_at'])


def downgrade() -> None:
    # Drop tables in reverse order
    op.drop_table('payer_profile_versions')
    op.drop_table('fee_schedules')
    op.drop_table('payer_credentials')
    op.drop_table('trading_partner_connections')
    op.drop_table('payer_rules')
    op.drop_table('payer_profiles')

