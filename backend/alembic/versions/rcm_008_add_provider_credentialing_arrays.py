"""Add provider_credentialing license/specialty/dea/cned columns

Adds the license, specialty, DEA, and CNED JSON columns that are present
on the ProviderCredentialing model but were missing from the original
017 migration.

Revision ID: rcm_008
Revises: rcm_007
Create Date: 2026-04-21 16:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = 'rcm_008'
down_revision = 'rcm_007'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add the JSON list columns. Use server_default='[]' so existing rows
    # get an empty list rather than NULL.
    op.add_column(
        'provider_credentialing',
        sa.Column(
            'licenses',
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )
    op.add_column(
        'provider_credentialing',
        sa.Column(
            'specialties',
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )
    op.add_column(
        'provider_credentialing',
        sa.Column(
            'dea_certificates',
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )
    op.add_column(
        'provider_credentialing',
        sa.Column(
            'cned_certificates',
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )


def downgrade() -> None:
    op.drop_column('provider_credentialing', 'cned_certificates')
    op.drop_column('provider_credentialing', 'dea_certificates')
    op.drop_column('provider_credentialing', 'specialties')
    op.drop_column('provider_credentialing', 'licenses')
