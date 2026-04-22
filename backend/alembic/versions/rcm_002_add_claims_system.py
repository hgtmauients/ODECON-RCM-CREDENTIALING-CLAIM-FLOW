"""Add claims state machine and EDI infrastructure

Revision ID: rcm_002
Revises: rcm_001
Create Date: 2024-01-02 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'rcm_002'
down_revision = 'rcm_001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create claims table
    op.create_table(
        'claims',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('claim_number', sa.String(length=50), nullable=False),
        sa.Column('payer_claim_id', sa.String(length=100)),
        sa.Column('original_claim_id', sa.Integer()),
        
        # Relationships
        sa.Column('patient_id', sa.Integer()),
        sa.Column('provider_id', sa.Integer()),
        sa.Column('payer_id', sa.Integer(), nullable=False),
        sa.Column('facility_id', sa.Integer()),
        
        # State machine
        sa.Column('state', sa.String(length=50), nullable=False, server_default='draft'),
        sa.Column('previous_state', sa.String(length=50)),
        sa.Column('current_queue', sa.String(length=100)),
        
        # Dates
        sa.Column('service_date_from', sa.Date(), nullable=False),
        sa.Column('service_date_to', sa.Date()),
        sa.Column('created_date', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        sa.Column('validated_date', sa.DateTime()),
        sa.Column('submitted_date', sa.DateTime()),
        sa.Column('adjudicated_date', sa.DateTime()),
        sa.Column('paid_date', sa.DateTime()),
        
        # Amounts
        sa.Column('total_charges', sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column('total_allowed', sa.Numeric(precision=10, scale=2)),
        sa.Column('total_paid', sa.Numeric(precision=10, scale=2)),
        sa.Column('patient_responsibility', sa.Numeric(precision=10, scale=2)),
        sa.Column('adjustment_amount', sa.Numeric(precision=10, scale=2)),
        
        # Claim details
        sa.Column('claim_type', sa.String(length=50)),
        sa.Column('claim_frequency_code', sa.String(length=5), server_default='1'),
        sa.Column('billing_provider_npi', sa.String(length=10)),
        sa.Column('rendering_provider_npi', sa.String(length=10)),
        
        # Prior auth
        sa.Column('prior_auth_number', sa.String(length=100)),
        sa.Column('requires_prior_auth', sa.Boolean(), server_default='false'),
        sa.Column('auth_obtained', sa.Boolean(), server_default='false'),
        
        # Timely filing
        sa.Column('filing_deadline', sa.Date()),
        sa.Column('days_until_filing_deadline', sa.Integer()),
        
        # Flags
        sa.Column('flags', postgresql.JSON(astext_type=sa.Text())),
        
        # Submission
        sa.Column('submission_method', sa.String(length=50)),
        sa.Column('clearinghouse_id', sa.String(length=100)),
        sa.Column('interchange_control_number', sa.String(length=50)),
        sa.Column('batch_id', sa.String(length=100)),
        
        # Denial
        sa.Column('denial_reason', sa.Text()),
        sa.Column('denial_category', sa.String(length=100)),
        sa.Column('appeal_due_date', sa.Date()),
        
        # Metadata
        sa.Column('created_by', sa.String(length=100)),
        sa.Column('updated_at', sa.DateTime(timezone=True), onupdate=sa.text('now()')),
        sa.Column('notes', sa.Text()),
        
        sa.ForeignKeyConstraint(['original_claim_id'], ['claims.id']),
        sa.ForeignKeyConstraint(['payer_id'], ['payer_profiles.id']),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Indexes
    op.create_index('ix_claims_claim_number', 'claims', ['claim_number'], unique=True)
    op.create_index('ix_claims_payer_claim_id', 'claims', ['payer_claim_id'])
    op.create_index('ix_claims_patient_id', 'claims', ['patient_id'])
    op.create_index('ix_claims_provider_id', 'claims', ['provider_id'])
    op.create_index('ix_claims_payer_id', 'claims', ['payer_id'])
    op.create_index('ix_claims_state', 'claims', ['state'])
    op.create_index('ix_claims_current_queue', 'claims', ['current_queue'])
    op.create_index('ix_claims_service_date_from', 'claims', ['service_date_from'])
    op.create_index('ix_claims_submitted_date', 'claims', ['submitted_date'])
    op.create_index('ix_claims_created_date', 'claims', ['created_date'])
    op.create_index('ix_claims_batch_id', 'claims', ['batch_id'])
    op.create_index('ix_claims_filing_deadline', 'claims', ['filing_deadline'])

    # Create claim_lines table
    op.create_table(
        'claim_lines',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('claim_id', sa.Integer(), nullable=False),
        sa.Column('line_number', sa.Integer(), nullable=False),
        sa.Column('cpt_code', sa.String(length=10), nullable=False),
        sa.Column('cpt_description', sa.Text()),
        sa.Column('modifiers', postgresql.JSON(astext_type=sa.Text())),
        sa.Column('diagnosis_pointers', postgresql.JSON(astext_type=sa.Text())),
        sa.Column('service_date', sa.Date()),
        sa.Column('units', sa.Integer(), server_default='1'),
        sa.Column('place_of_service', sa.String(length=5)),
        sa.Column('charge_amount', sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column('allowed_amount', sa.Numeric(precision=10, scale=2)),
        sa.Column('paid_amount', sa.Numeric(precision=10, scale=2)),
        sa.Column('patient_responsibility', sa.Numeric(precision=10, scale=2)),
        sa.Column('adjustment_amount', sa.Numeric(precision=10, scale=2)),
        sa.Column('is_denied', sa.Boolean(), server_default='false'),
        sa.Column('carc_code', sa.String(length=20)),
        sa.Column('rarc_code', sa.String(length=20)),
        sa.Column('denial_description', sa.Text()),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), onupdate=sa.text('now()')),
        
        sa.ForeignKeyConstraint(['claim_id'], ['claims.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    
    op.create_index('ix_claim_lines_claim_id', 'claim_lines', ['claim_id'])
    op.create_index('ix_claim_lines_cpt_code', 'claim_lines', ['cpt_code'])

    # Create claim_diagnoses table
    op.create_table(
        'claim_diagnoses',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('claim_id', sa.Integer(), nullable=False),
        sa.Column('diagnosis_pointer', sa.Integer(), nullable=False),
        sa.Column('icd10_code', sa.String(length=10), nullable=False),
        sa.Column('icd10_description', sa.Text()),
        sa.Column('is_primary', sa.Boolean(), server_default='false'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        
        sa.ForeignKeyConstraint(['claim_id'], ['claims.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    
    op.create_index('ix_claim_diagnoses_claim_id', 'claim_diagnoses', ['claim_id'])
    op.create_index('ix_claim_diagnoses_icd10_code', 'claim_diagnoses', ['icd10_code'])

    # Create edi_files table
    op.create_table(
        'edi_files',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('file_type', sa.String(length=10), nullable=False),
        sa.Column('direction', sa.String(length=10), nullable=False),
        sa.Column('filename', sa.String(length=500), nullable=False),
        sa.Column('file_path', sa.String(length=1000), nullable=False),
        sa.Column('file_size', sa.Integer()),
        sa.Column('interchange_control_number', sa.String(length=50)),
        sa.Column('group_control_number', sa.String(length=50)),
        sa.Column('transaction_count', sa.Integer()),
        sa.Column('payer_id', sa.Integer()),
        sa.Column('batch_id', sa.String(length=100)),
        sa.Column('status', sa.String(length=50), nullable=False, server_default='pending'),
        sa.Column('processed_at', sa.DateTime()),
        sa.Column('error_message', sa.Text()),
        sa.Column('validation_errors', postgresql.JSON(astext_type=sa.Text())),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        sa.Column('created_by', sa.String(length=100)),
        
        sa.ForeignKeyConstraint(['payer_id'], ['payer_profiles.id']),
        sa.PrimaryKeyConstraint('id')
    )
    
    op.create_index('ix_edi_files_file_type', 'edi_files', ['file_type'])
    op.create_index('ix_edi_files_direction', 'edi_files', ['direction'])
    op.create_index('ix_edi_files_interchange_control_number', 'edi_files', ['interchange_control_number'])
    op.create_index('ix_edi_files_payer_id', 'edi_files', ['payer_id'])
    op.create_index('ix_edi_files_batch_id', 'edi_files', ['batch_id'])
    op.create_index('ix_edi_files_status', 'edi_files', ['status'])
    op.create_index('ix_edi_files_created_at', 'edi_files', ['created_at'])

    # Create claim_events table
    op.create_table(
        'claim_events',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('claim_id', sa.Integer(), nullable=False),
        sa.Column('event_type', sa.String(length=50), nullable=False),
        sa.Column('timestamp', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        sa.Column('user_id', sa.String(length=100)),
        sa.Column('from_state', sa.String(length=50)),
        sa.Column('to_state', sa.String(length=50)),
        sa.Column('data', postgresql.JSON(astext_type=sa.Text())),
        sa.Column('edi_file_id', sa.Integer()),
        sa.Column('document_id', sa.Integer()),
        sa.Column('message', sa.Text()),
        
        sa.ForeignKeyConstraint(['claim_id'], ['claims.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['edi_file_id'], ['edi_files.id']),
        sa.PrimaryKeyConstraint('id')
    )
    
    op.create_index('ix_claim_events_claim_id', 'claim_events', ['claim_id'])
    op.create_index('ix_claim_events_event_type', 'claim_events', ['event_type'])
    op.create_index('ix_claim_events_timestamp', 'claim_events', ['timestamp'])

    # Create claim_queues table
    op.create_table(
        'claim_queues',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=200), nullable=False),
        sa.Column('display_name', sa.String(length=200)),
        sa.Column('description', sa.Text()),
        sa.Column('queue_type', sa.String(length=100)),
        sa.Column('auto_assign_role', sa.String(length=100)),
        sa.Column('load_balancing', sa.Boolean(), server_default='true'),
        sa.Column('default_sla_hours', sa.Integer()),
        sa.Column('escalation_sla_hours', sa.Integer()),
        sa.Column('notification_rules', postgresql.JSON(astext_type=sa.Text())),
        sa.Column('escalation_rules', postgresql.JSON(astext_type=sa.Text())),
        sa.Column('color', sa.String(length=20)),
        sa.Column('icon', sa.String(length=50)),
        sa.Column('is_active', sa.Boolean(), server_default='true'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        
        sa.PrimaryKeyConstraint('id')
    )
    
    op.create_index('ix_claim_queues_name', 'claim_queues', ['name'], unique=True)

    # Create claim_validations table
    op.create_table(
        'claim_validations',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('claim_id', sa.Integer(), nullable=False),
        sa.Column('validated_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        sa.Column('validation_version', sa.String(length=50)),
        sa.Column('passed', sa.Boolean(), nullable=False),
        sa.Column('errors', postgresql.JSON(astext_type=sa.Text())),
        sa.Column('warnings', postgresql.JSON(astext_type=sa.Text())),
        sa.Column('rules_evaluated', sa.Integer()),
        sa.Column('rules_matched', sa.Integer()),
        sa.Column('actions_executed', postgresql.JSON(astext_type=sa.Text())),
        sa.Column('flags_set', postgresql.JSON(astext_type=sa.Text())),
        sa.Column('modifiers_added', postgresql.JSON(astext_type=sa.Text())),
        
        sa.ForeignKeyConstraint(['claim_id'], ['claims.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    
    op.create_index('ix_claim_validations_claim_id', 'claim_validations', ['claim_id'])


def downgrade() -> None:
    op.drop_table('claim_validations')
    op.drop_table('claim_queues')
    op.drop_table('claim_events')
    op.drop_table('edi_files')
    op.drop_table('claim_diagnoses')
    op.drop_table('claim_lines')
    op.drop_table('claims')

