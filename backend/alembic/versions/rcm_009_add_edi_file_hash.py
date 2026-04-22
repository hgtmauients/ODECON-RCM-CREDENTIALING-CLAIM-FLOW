"""Add file_hash to edi_files for idempotent ingest

Revision ID: rcm_009
Revises: rcm_008
Create Date: 2026-04-22 01:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'rcm_009'
down_revision = 'rcm_008'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'edi_files',
        sa.Column('file_hash', sa.String(length=64), nullable=True),
    )
    op.create_index(
        'ix_edi_files_tenant_hash',
        'edi_files',
        ['tenant_id', 'file_hash'],
    )


def downgrade() -> None:
    op.drop_index('ix_edi_files_tenant_hash', table_name='edi_files')
    op.drop_column('edi_files', 'file_hash')
