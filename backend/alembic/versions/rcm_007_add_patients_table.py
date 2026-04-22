"""Add patients table

Revision ID: rcm_007
Revises: rcm_006
Create Date: 2026-04-20 01:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = 'rcm_007'
down_revision = 'rcm_006'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'patients',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('first_name', sa.String(length=100), nullable=False),
        sa.Column('last_name', sa.String(length=100), nullable=False),
        sa.Column('middle_name', sa.String(length=50)),
        sa.Column('suffix', sa.String(length=10)),
        sa.Column('date_of_birth', sa.Date(), nullable=False),
        sa.Column('gender', sa.String(length=1), nullable=False),
        sa.Column('address_line_1', sa.String(length=255), nullable=False),
        sa.Column('address_line_2', sa.String(length=255)),
        sa.Column('city', sa.String(length=128), nullable=False),
        sa.Column('state', sa.String(length=2), nullable=False),
        sa.Column('zip_code', sa.String(length=10), nullable=False),
        sa.Column('phone', sa.String(length=20)),
        sa.Column('email', sa.String(length=255)),
        sa.Column('member_id', sa.String(length=80), nullable=False),
        sa.Column('group_number', sa.String(length=50)),
        sa.Column('payer_id', sa.Integer()),
        sa.Column('relationship_to_subscriber', sa.String(length=2), server_default='18'),
        sa.Column('subscriber_id', sa.Integer()),
        sa.Column('is_active', sa.Boolean(), server_default=sa.text('true')),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True)),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_patients_tenant_id', 'patients', ['tenant_id'])
    op.create_index('ix_patients_tenant_last_name', 'patients', ['tenant_id', 'last_name'])
    op.create_index('ix_patients_tenant_member_id', 'patients', ['tenant_id', 'member_id'])
    op.create_index('ix_patients_payer_id', 'patients', ['payer_id'])


def downgrade() -> None:
    op.drop_table('patients')
