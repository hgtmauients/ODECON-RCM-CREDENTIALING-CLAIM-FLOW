"""add provider credentialing tables

Revision ID: 017_add_provider_credentialing_tables
Revises: 016
Create Date: 2025-10-28 11:50:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '017'
down_revision = 'rcm_005'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create provider_credentialing table
    op.create_table(
        'provider_credentialing',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('provider_id', sa.String(length=100), nullable=False),
        sa.Column('signup_data', postgresql.JSON(astext_type=sa.Text()), nullable=False),
        sa.Column('license_url', sa.String(length=255)),
        sa.Column('signup_date', sa.DateTime(), nullable=True),
        sa.Column('npi_verification', postgresql.JSON(astext_type=sa.Text())),
        sa.Column('state_license_verification', postgresql.JSON(astext_type=sa.Text())),
        sa.Column('specialty_board_verification', postgresql.JSON(astext_type=sa.Text())),
        sa.Column('background_check', postgresql.JSON(astext_type=sa.Text())),
        sa.Column('oig_check', postgresql.JSON(astext_type=sa.Text())),
        sa.Column('sam_check', postgresql.JSON(astext_type=sa.Text())),
        sa.Column('credentialing_status', sa.String(length=50), nullable=True),
        sa.Column('overall_score', sa.Integer(), nullable=True),
        sa.Column('started_at', sa.DateTime(), nullable=True),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
        sa.Column('verified_by', sa.String(length=100)),
        sa.Column('verified_at', sa.DateTime(), nullable=True),
        sa.Column('admin_notes', sa.Text()),
        sa.Column('rejection_reason', sa.Text()),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_provider_credentialing_provider_id', 'provider_credentialing', ['provider_id'], unique=True)
    
    # Create credentialing_verification_log table
    op.create_table(
        'credentialing_verification_log',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('provider_id', sa.String(length=100), nullable=False),
        sa.Column('verification_type', sa.String(length=50), nullable=False),
        sa.Column('status', sa.String(length=50), nullable=False),
        sa.Column('result', postgresql.JSON(astext_type=sa.Text())),
        sa.Column('api_response', postgresql.JSON(astext_type=sa.Text())),
        sa.Column('error_message', sa.Text()),
        sa.Column('verified_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_credentialing_verification_log_provider_id', 'credentialing_verification_log', ['provider_id'])


def downgrade() -> None:
    op.drop_index('ix_credentialing_verification_log_provider_id', table_name='credentialing_verification_log')
    op.drop_table('credentialing_verification_log')
    op.drop_index('ix_provider_credentialing_provider_id', table_name='provider_credentialing')
    op.drop_table('provider_credentialing')

