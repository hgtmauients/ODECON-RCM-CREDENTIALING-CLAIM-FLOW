"""Make edi_files (tenant_id, file_hash) unique for true idempotency

Revision ID: rcm_010
Revises: rcm_009
Create Date: 2026-04-22 02:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'rcm_010'
down_revision = 'rcm_009'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # First, deduplicate any existing rows that share the same (tenant_id, file_hash, file_type)
    # to allow the unique index to be created. We keep the row with the lowest id.
    op.execute("""
        DELETE FROM edi_files a
        USING edi_files b
        WHERE a.id > b.id
          AND a.tenant_id = b.tenant_id
          AND a.file_hash IS NOT NULL
          AND a.file_hash = b.file_hash
          AND a.file_type = b.file_type
    """)

    # Drop the old non-unique index (created in rcm_009)
    op.drop_index('ix_edi_files_tenant_hash', table_name='edi_files')

    # Create a UNIQUE partial index. We exclude rows where file_hash IS NULL
    # so historical files without a hash do not collide with each other.
    op.create_index(
        'ix_edi_files_tenant_hash_type_unique',
        'edi_files',
        ['tenant_id', 'file_hash', 'file_type'],
        unique=True,
        postgresql_where=sa.text('file_hash IS NOT NULL'),
    )


def downgrade() -> None:
    op.drop_index('ix_edi_files_tenant_hash_type_unique', table_name='edi_files')
    op.create_index('ix_edi_files_tenant_hash', 'edi_files', ['tenant_id', 'file_hash'])
