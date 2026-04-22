"""Add security audit and credential tracking

Revision ID: rcm_005
Revises: rcm_004
Create Date: 2024-01-05 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = 'rcm_005'
down_revision = 'rcm_004'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create credential_access_log table
    op.create_table(
        'credential_access_log',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.String(length=100), nullable=False),
        sa.Column('user_email', sa.String(length=200)),
        sa.Column('user_role', sa.String(length=50)),
        sa.Column('payer_id', sa.Integer()),
        sa.Column('credential_type', sa.String(length=50), nullable=False),
        sa.Column('action', sa.String(length=50), nullable=False),
        sa.Column('accessed_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        sa.Column('ip_address', sa.String(length=50)),
        sa.Column('user_agent', sa.String(length=500)),
        sa.Column('reason', sa.Text()),
        
        sa.ForeignKeyConstraint(['payer_id'], ['payer_profiles.id']),
        sa.PrimaryKeyConstraint('id')
    )
    
    op.create_index('ix_credential_access_log_user_id', 'credential_access_log', ['user_id'])
    op.create_index('ix_credential_access_log_payer_id', 'credential_access_log', ['payer_id'])
    op.create_index('ix_credential_access_log_action', 'credential_access_log', ['action'])
    op.create_index('ix_credential_access_log_accessed_at', 'credential_access_log', ['accessed_at'])

    # Create security_audit_log table
    op.create_table(
        'security_audit_log',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.String(length=100), nullable=False),
        sa.Column('user_email', sa.String(length=200)),
        sa.Column('user_role', sa.String(length=50)),
        sa.Column('action', sa.String(length=100), nullable=False),
        sa.Column('resource_type', sa.String(length=50)),
        sa.Column('resource_id', sa.String(length=100)),
        sa.Column('timestamp', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        sa.Column('ip_address', sa.String(length=50)),
        sa.Column('user_agent', sa.String(length=500)),
        sa.Column('changes', postgresql.JSON(astext_type=sa.Text())),
        sa.Column('metadata', postgresql.JSON(astext_type=sa.Text())),
        sa.Column('success', sa.Boolean(), server_default='true'),
        sa.Column('error_message', sa.Text()),
        
        sa.PrimaryKeyConstraint('id')
    )
    
    op.create_index('ix_security_audit_log_user_id', 'security_audit_log', ['user_id'])
    op.create_index('ix_security_audit_log_action', 'security_audit_log', ['action'])
    op.create_index('ix_security_audit_log_resource_type', 'security_audit_log', ['resource_type'])
    op.create_index('ix_security_audit_log_resource_id', 'security_audit_log', ['resource_id'])
    op.create_index('ix_security_audit_log_timestamp', 'security_audit_log', ['timestamp'])

    # Create mfa_attempts table
    op.create_table(
        'mfa_attempts',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.String(length=100), nullable=False),
        sa.Column('operation', sa.String(length=100), nullable=False),
        sa.Column('mfa_method', sa.String(length=50)),
        sa.Column('attempt_time', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        sa.Column('success', sa.Boolean(), nullable=False),
        sa.Column('ip_address', sa.String(length=50)),
        
        sa.PrimaryKeyConstraint('id')
    )
    
    op.create_index('ix_mfa_attempts_user_id', 'mfa_attempts', ['user_id'])

    # Add composite indexes for performance
    op.create_index('ix_claims_payer_state', 'claims', ['payer_id', 'state'])
    op.create_index('ix_claims_service_date_state', 'claims', ['service_date_from', 'state'])
    op.create_index('ix_denial_cases_category_priority', 'denial_cases', ['denial_category', 'priority'])


def downgrade() -> None:
    op.drop_index('ix_denial_cases_category_priority', table_name='denial_cases')
    op.drop_index('ix_claims_service_date_state', table_name='claims')
    op.drop_index('ix_claims_payer_state', table_name='claims')
    op.drop_table('mfa_attempts')
    op.drop_table('security_audit_log')
    op.drop_table('credential_access_log')

