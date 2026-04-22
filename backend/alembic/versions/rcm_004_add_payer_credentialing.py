"""Add payer credentialing and document vault

Revision ID: rcm_004
Revises: rcm_003
Create Date: 2024-01-04 00:00:00.000000

Integrates existing provider credentialing with payer-specific enrollment
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = 'rcm_004'
down_revision = 'rcm_003'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create payer_credentialing_cases table
    op.create_table(
        'payer_credentialing_cases',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('provider_id', sa.String(length=100), nullable=False),
        sa.Column('payer_id', sa.Integer(), nullable=False),
        sa.Column('status', sa.String(length=50), server_default='draft'),
        sa.Column('submitted_date', sa.Date()),
        sa.Column('submission_method', sa.String(length=50)),
        sa.Column('submission_tracking_number', sa.String(length=100)),
        sa.Column('effective_date', sa.Date()),
        sa.Column('expiration_date', sa.Date()),
        sa.Column('payer_rep_name', sa.String(length=200)),
        sa.Column('payer_rep_email', sa.String(length=200)),
        sa.Column('payer_rep_phone', sa.String(length=50)),
        sa.Column('payer_rep_extension', sa.String(length=20)),
        sa.Column('ticket_number', sa.String(length=100)),
        sa.Column('checklist', postgresql.JSON(astext_type=sa.Text())),
        sa.Column('total_items', sa.Integer(), server_default='0'),
        sa.Column('completed_items', sa.Integer(), server_default='0'),
        sa.Column('completion_percentage', sa.Integer(), server_default='0'),
        sa.Column('payer_response_date', sa.Date()),
        sa.Column('payer_response', sa.Text()),
        sa.Column('additional_info_requested', postgresql.JSON(astext_type=sa.Text())),
        sa.Column('rejection_reason', sa.Text()),
        sa.Column('requires_recredentialing', sa.Boolean(), server_default='false'),
        sa.Column('recredentialing_frequency_months', sa.Integer()),
        sa.Column('next_recredentialing_date', sa.Date()),
        sa.Column('recredentialing_reminder_sent', sa.Boolean(), server_default='false'),
        sa.Column('communication_log', postgresql.JSON(astext_type=sa.Text())),
        sa.Column('notes', sa.Text()),
        sa.Column('internal_status_notes', sa.Text()),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), onupdate=sa.text('now()')),
        sa.Column('created_by', sa.String(length=100)),
        sa.Column('updated_by', sa.String(length=100)),
        sa.Column('assigned_to', sa.String(length=100)),
        
        sa.ForeignKeyConstraint(['payer_id'], ['payer_profiles.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    
    op.create_index('ix_payer_credentialing_cases_provider_id', 'payer_credentialing_cases', ['provider_id'])
    op.create_index('ix_payer_credentialing_cases_payer_id', 'payer_credentialing_cases', ['payer_id'])
    op.create_index('ix_payer_credentialing_cases_status', 'payer_credentialing_cases', ['status'])
    op.create_index('ix_payer_credentialing_cases_submitted_date', 'payer_credentialing_cases', ['submitted_date'])
    op.create_index('ix_payer_credentialing_cases_effective_date', 'payer_credentialing_cases', ['effective_date'])
    op.create_index('ix_payer_credentialing_cases_expiration_date', 'payer_credentialing_cases', ['expiration_date'])
    op.create_index('ix_payer_credentialing_cases_assigned_to', 'payer_credentialing_cases', ['assigned_to'])
    op.create_index('ix_payer_credentialing_cases_next_recredentialing_date', 'payer_credentialing_cases', ['next_recredentialing_date'])
    op.create_index('ix_payer_credentialing_cases_created_at', 'payer_credentialing_cases', ['created_at'])

    # Create era_enrollment_cases table
    op.create_table(
        'era_enrollment_cases',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('provider_id', sa.String(length=100), nullable=False),
        sa.Column('payer_id', sa.Integer(), nullable=False),
        sa.Column('clearinghouse', sa.String(length=100)),
        sa.Column('status', sa.String(length=50), server_default='pending'),
        sa.Column('enrollment_date', sa.Date()),
        sa.Column('effective_date', sa.Date()),
        sa.Column('tested_date', sa.Date()),
        sa.Column('bank_name', sa.String(length=200)),
        sa.Column('routing_number_encrypted', sa.Text()),
        sa.Column('account_number_encrypted', sa.Text()),
        sa.Column('account_type', sa.String(length=50)),
        sa.Column('submitter_id', sa.String(length=50)),
        sa.Column('receiver_id', sa.String(length=50)),
        sa.Column('checklist', postgresql.JSON(astext_type=sa.Text())),
        sa.Column('test_835_file_id', sa.Integer()),
        sa.Column('test_835_received', sa.Boolean(), server_default='false'),
        sa.Column('test_835_date', sa.Date()),
        sa.Column('test_835_amount', sa.String(length=20)),
        sa.Column('first_production_835_date', sa.Date()),
        sa.Column('last_835_received_date', sa.Date()),
        sa.Column('total_835_files_received', sa.Integer(), server_default='0'),
        sa.Column('notes', sa.Text()),
        sa.Column('submission_notes', sa.Text()),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), onupdate=sa.text('now()')),
        sa.Column('created_by', sa.String(length=100)),
        sa.Column('assigned_to', sa.String(length=100)),
        
        sa.ForeignKeyConstraint(['payer_id'], ['payer_profiles.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['test_835_file_id'], ['edi_files.id']),
        sa.PrimaryKeyConstraint('id')
    )
    
    op.create_index('ix_era_enrollment_cases_provider_id', 'era_enrollment_cases', ['provider_id'])
    op.create_index('ix_era_enrollment_cases_payer_id', 'era_enrollment_cases', ['payer_id'])
    op.create_index('ix_era_enrollment_cases_status', 'era_enrollment_cases', ['status'])
    op.create_index('ix_era_enrollment_cases_effective_date', 'era_enrollment_cases', ['effective_date'])

    # Create provider_documents table
    op.create_table(
        'provider_documents',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('provider_id', sa.String(length=100), nullable=False),
        sa.Column('document_type', sa.String(length=100), nullable=False),
        sa.Column('document_name', sa.String(length=500), nullable=False),
        sa.Column('description', sa.Text()),
        sa.Column('file_path', sa.String(length=1000), nullable=False),
        sa.Column('file_size', sa.Integer()),
        sa.Column('mime_type', sa.String(length=100)),
        sa.Column('original_filename', sa.String(length=500)),
        sa.Column('version', sa.Integer(), server_default='1'),
        sa.Column('parent_document_id', sa.Integer()),
        sa.Column('is_latest_version', sa.Boolean(), server_default='true'),
        sa.Column('issue_date', sa.Date()),
        sa.Column('expiration_date', sa.Date()),
        sa.Column('days_until_expiration', sa.Integer()),
        sa.Column('renewal_reminder_sent', sa.Boolean(), server_default='false'),
        sa.Column('is_verified', sa.Boolean(), server_default='false'),
        sa.Column('verified_by', sa.String(length=100)),
        sa.Column('verified_at', sa.DateTime()),
        sa.Column('credentialing_case_id', sa.Integer()),
        sa.Column('era_enrollment_case_id', sa.Integer()),
        sa.Column('is_encrypted', sa.Boolean(), server_default='true'),
        sa.Column('encryption_key_id', sa.String(length=100)),
        sa.Column('state_code', sa.String(length=2)),
        sa.Column('uploaded_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        sa.Column('uploaded_by', sa.String(length=100)),
        sa.Column('updated_at', sa.DateTime(timezone=True), onupdate=sa.text('now()')),
        sa.Column('tags', postgresql.JSON(astext_type=sa.Text())),
        
        sa.ForeignKeyConstraint(['parent_document_id'], ['provider_documents.id']),
        sa.ForeignKeyConstraint(['credentialing_case_id'], ['payer_credentialing_cases.id']),
        sa.ForeignKeyConstraint(['era_enrollment_case_id'], ['era_enrollment_cases.id']),
        sa.PrimaryKeyConstraint('id')
    )
    
    op.create_index('ix_provider_documents_provider_id', 'provider_documents', ['provider_id'])
    op.create_index('ix_provider_documents_document_type', 'provider_documents', ['document_type'])
    op.create_index('ix_provider_documents_is_latest_version', 'provider_documents', ['is_latest_version'])
    op.create_index('ix_provider_documents_expiration_date', 'provider_documents', ['expiration_date'])
    op.create_index('ix_provider_documents_state_code', 'provider_documents', ['state_code'])
    op.create_index('ix_provider_documents_uploaded_at', 'provider_documents', ['uploaded_at'])

    # Create credentialing_renewals table
    op.create_table(
        'credentialing_renewals',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('credentialing_case_id', sa.Integer(), nullable=False),
        sa.Column('provider_id', sa.String(length=100), nullable=False),
        sa.Column('payer_id', sa.Integer(), nullable=False),
        sa.Column('renewal_type', sa.String(length=50)),
        sa.Column('renewal_frequency_months', sa.Integer()),
        sa.Column('current_expiration_date', sa.Date(), nullable=False),
        sa.Column('next_renewal_start_date', sa.Date()),
        sa.Column('reminder_1_sent', sa.Boolean(), server_default='false'),
        sa.Column('reminder_1_date', sa.Date()),
        sa.Column('reminder_2_sent', sa.Boolean(), server_default='false'),
        sa.Column('reminder_2_date', sa.Date()),
        sa.Column('reminder_3_sent', sa.Boolean(), server_default='false'),
        sa.Column('reminder_3_date', sa.Date()),
        sa.Column('urgent_alert_sent', sa.Boolean(), server_default='false'),
        sa.Column('renewal_initiated', sa.Boolean(), server_default='false'),
        sa.Column('renewal_completed', sa.Boolean(), server_default='false'),
        sa.Column('renewal_completed_date', sa.Date()),
        sa.Column('new_expiration_date', sa.Date()),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), onupdate=sa.text('now()')),
        
        sa.ForeignKeyConstraint(['credentialing_case_id'], ['payer_credentialing_cases.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['payer_id'], ['payer_profiles.id']),
        sa.PrimaryKeyConstraint('id')
    )
    
    op.create_index('ix_credentialing_renewals_credentialing_case_id', 'credentialing_renewals', ['credentialing_case_id'])
    op.create_index('ix_credentialing_renewals_provider_id', 'credentialing_renewals', ['provider_id'])
    op.create_index('ix_credentialing_renewals_current_expiration_date', 'credentialing_renewals', ['current_expiration_date'])
    op.create_index('ix_credentialing_renewals_next_renewal_start_date', 'credentialing_renewals', ['next_renewal_start_date'])


def downgrade() -> None:
    op.drop_table('credentialing_renewals')
    op.drop_table('provider_documents')
    op.drop_table('era_enrollment_cases')
    op.drop_table('payer_credentialing_cases')

