"""Add icd10_codes + cpt_codes tables (code library for autocomplete)

Revision ID: rcm_012
Revises: rcm_011
Create Date: 2026-04-22 06:30:00.000000

These tables back the ICD-10 / CPT autocomplete on the claim builder. The
SQLAlchemy models existed in models/code_library.py since the original
init_prod.py bootstrap, but no alembic migration ever created the tables —
so newly-provisioned databases (or any rebuild that didn\'t run init_prod)
were missing both tables and the search endpoint silently 200\'d with empty
results (or 500\'d in some setups). The seed script
`backend/scripts/seed_code_library.py` populates ~600 ICD-10 + ~500 CPT
codes; run that AFTER this migration applies.
"""
from alembic import op
import sqlalchemy as sa


revision = "rcm_012"
down_revision = "rcm_011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "icd10_codes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("code", sa.String(10), nullable=False),
        sa.Column("short_description", sa.String(255), nullable=False),
        sa.Column("long_description", sa.Text(), nullable=True),
        sa.Column("category", sa.String(100), nullable=True),
        sa.Column("chapter", sa.String(255), nullable=True),
        sa.Column("is_billable", sa.Boolean(), nullable=True, server_default=sa.true()),
    )
    # Match the indexes declared on the model so the search ILIKE + autocomplete
    # ordering paths stay fast.
    op.create_index("ix_icd10_codes_id", "icd10_codes", ["id"])
    op.create_index("ix_icd10_code", "icd10_codes", ["code"], unique=True)
    op.create_index("ix_icd10_search", "icd10_codes", ["code", "short_description"])

    op.create_table(
        "cpt_codes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("code", sa.String(10), nullable=False),
        sa.Column("short_description", sa.String(255), nullable=False),
        sa.Column("long_description", sa.Text(), nullable=True),
        sa.Column("category", sa.String(100), nullable=True),
        sa.Column("subcategory", sa.String(100), nullable=True),
        sa.Column("rvu_work", sa.String(10), nullable=True),
        sa.Column("rvu_facility", sa.String(10), nullable=True),
        sa.Column("rvu_nonfacility", sa.String(10), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=True, server_default=sa.true()),
    )
    op.create_index("ix_cpt_codes_id", "cpt_codes", ["id"])
    op.create_index("ix_cpt_code", "cpt_codes", ["code"], unique=True)
    op.create_index("ix_cpt_search", "cpt_codes", ["code", "short_description"])


def downgrade() -> None:
    op.drop_index("ix_cpt_search", table_name="cpt_codes")
    op.drop_index("ix_cpt_code", table_name="cpt_codes")
    op.drop_index("ix_cpt_codes_id", table_name="cpt_codes")
    op.drop_table("cpt_codes")

    op.drop_index("ix_icd10_search", table_name="icd10_codes")
    op.drop_index("ix_icd10_code", table_name="icd10_codes")
    op.drop_index("ix_icd10_codes_id", table_name="icd10_codes")
    op.drop_table("icd10_codes")
