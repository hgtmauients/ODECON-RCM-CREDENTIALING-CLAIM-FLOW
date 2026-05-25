"""Harden tenant isolation on child tables.

Revision ID: rcm_014
Revises: rcm_013
Create Date: 2026-05-25
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "rcm_014"
down_revision = "rcm_013"
branch_labels = None
depends_on = None


CHILD_TABLES = (
    "claim_lines",
    "claim_diagnoses",
    "payer_rules",
    "trading_partner_connections",
    "fee_schedules",
    "payer_profile_versions",
)


def _enable_rls(table_name: str) -> None:
    op.execute(f'ALTER TABLE "{table_name}" ENABLE ROW LEVEL SECURITY')
    op.execute(f'DROP POLICY IF EXISTS tenant_isolation_policy ON "{table_name}"')
    op.execute(
        f"""
        CREATE POLICY tenant_isolation_policy ON "{table_name}"
        USING (
            current_setting('app.bypass_rls', true) = '1'
            OR tenant_id::text = current_setting('app.tenant_id', true)
        )
        WITH CHECK (
            current_setting('app.bypass_rls', true) = '1'
            OR tenant_id::text = current_setting('app.tenant_id', true)
        )
        """
    )
    op.execute(f'ALTER TABLE "{table_name}" FORCE ROW LEVEL SECURITY')


def _disable_rls(table_name: str) -> None:
    op.execute(f'DROP POLICY IF EXISTS tenant_isolation_policy ON "{table_name}"')
    op.execute(f'ALTER TABLE "{table_name}" NO FORCE ROW LEVEL SECURITY')
    op.execute(f'ALTER TABLE "{table_name}" DISABLE ROW LEVEL SECURITY')


def upgrade() -> None:
    # Add tenant_id columns
    for table_name in CHILD_TABLES:
        op.add_column(table_name, sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=True))
        op.create_index(f"ix_{table_name}_tenant_id", table_name, ["tenant_id"])

    # Backfill tenant_id from parent records
    op.execute(
        """
        UPDATE claim_lines cl
        SET tenant_id = c.tenant_id
        FROM claims c
        WHERE c.id = cl.claim_id
          AND cl.tenant_id IS NULL
        """
    )
    op.execute(
        """
        UPDATE claim_diagnoses cd
        SET tenant_id = c.tenant_id
        FROM claims c
        WHERE c.id = cd.claim_id
          AND cd.tenant_id IS NULL
        """
    )
    op.execute(
        """
        UPDATE payer_rules pr
        SET tenant_id = pp.tenant_id
        FROM payer_profiles pp
        WHERE pp.id = pr.payer_id
          AND pr.tenant_id IS NULL
        """
    )
    op.execute(
        """
        UPDATE trading_partner_connections tpc
        SET tenant_id = pp.tenant_id
        FROM payer_profiles pp
        WHERE pp.id = tpc.payer_id
          AND tpc.tenant_id IS NULL
        """
    )
    op.execute(
        """
        UPDATE fee_schedules fs
        SET tenant_id = pp.tenant_id
        FROM payer_profiles pp
        WHERE pp.id = fs.payer_id
          AND fs.tenant_id IS NULL
        """
    )
    op.execute(
        """
        UPDATE payer_profile_versions ppv
        SET tenant_id = pp.tenant_id
        FROM payer_profiles pp
        WHERE pp.id = ppv.payer_id
          AND ppv.tenant_id IS NULL
        """
    )

    # Keep child table tenant_id synchronized with parent linkage.
    op.execute(
        """
        CREATE OR REPLACE FUNCTION sync_tenant_from_claim()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        DECLARE parent_tid uuid;
        BEGIN
            SELECT tenant_id INTO parent_tid
            FROM claims
            WHERE id = NEW.claim_id;
            IF parent_tid IS NULL THEN
                RAISE EXCEPTION 'Invalid claim_id for tenant sync';
            END IF;
            IF NEW.tenant_id IS NULL THEN
                NEW.tenant_id := parent_tid;
            ELSIF NEW.tenant_id <> parent_tid THEN
                RAISE EXCEPTION 'tenant_id must match claim tenant';
            END IF;
            RETURN NEW;
        END;
        $$;
        """
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION sync_tenant_from_payer_profile()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        DECLARE parent_tid uuid;
        BEGIN
            SELECT tenant_id INTO parent_tid
            FROM payer_profiles
            WHERE id = NEW.payer_id;
            IF parent_tid IS NULL THEN
                RAISE EXCEPTION 'Invalid payer_id for tenant sync';
            END IF;
            IF NEW.tenant_id IS NULL THEN
                NEW.tenant_id := parent_tid;
            ELSIF NEW.tenant_id <> parent_tid THEN
                RAISE EXCEPTION 'tenant_id must match payer profile tenant';
            END IF;
            RETURN NEW;
        END;
        $$;
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_claim_lines_sync_tenant
        BEFORE INSERT OR UPDATE OF claim_id, tenant_id ON claim_lines
        FOR EACH ROW EXECUTE FUNCTION sync_tenant_from_claim();
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_claim_diagnoses_sync_tenant
        BEFORE INSERT OR UPDATE OF claim_id, tenant_id ON claim_diagnoses
        FOR EACH ROW EXECUTE FUNCTION sync_tenant_from_claim();
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_payer_rules_sync_tenant
        BEFORE INSERT OR UPDATE OF payer_id, tenant_id ON payer_rules
        FOR EACH ROW EXECUTE FUNCTION sync_tenant_from_payer_profile();
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_trading_partner_connections_sync_tenant
        BEFORE INSERT OR UPDATE OF payer_id, tenant_id ON trading_partner_connections
        FOR EACH ROW EXECUTE FUNCTION sync_tenant_from_payer_profile();
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_fee_schedules_sync_tenant
        BEFORE INSERT OR UPDATE OF payer_id, tenant_id ON fee_schedules
        FOR EACH ROW EXECUTE FUNCTION sync_tenant_from_payer_profile();
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_payer_profile_versions_sync_tenant
        BEFORE INSERT OR UPDATE OF payer_id, tenant_id ON payer_profile_versions
        FOR EACH ROW EXECUTE FUNCTION sync_tenant_from_payer_profile();
        """
    )

    # Add FK and non-null constraints after backfill + sync hooks are in place.
    for table_name in CHILD_TABLES:
        op.alter_column(table_name, "tenant_id", nullable=False)
        op.create_foreign_key(
            f"fk_{table_name}_tenant_id",
            table_name,
            "tenants",
            ["tenant_id"],
            ["id"],
            ondelete="CASCADE",
        )
        _enable_rls(table_name)


def downgrade() -> None:
    for table_name in CHILD_TABLES:
        _disable_rls(table_name)

    op.execute("DROP TRIGGER IF EXISTS trg_claim_lines_sync_tenant ON claim_lines")
    op.execute("DROP TRIGGER IF EXISTS trg_claim_diagnoses_sync_tenant ON claim_diagnoses")
    op.execute("DROP TRIGGER IF EXISTS trg_payer_rules_sync_tenant ON payer_rules")
    op.execute("DROP TRIGGER IF EXISTS trg_trading_partner_connections_sync_tenant ON trading_partner_connections")
    op.execute("DROP TRIGGER IF EXISTS trg_fee_schedules_sync_tenant ON fee_schedules")
    op.execute("DROP TRIGGER IF EXISTS trg_payer_profile_versions_sync_tenant ON payer_profile_versions")
    op.execute("DROP FUNCTION IF EXISTS sync_tenant_from_claim()")
    op.execute("DROP FUNCTION IF EXISTS sync_tenant_from_payer_profile()")

    for table_name in CHILD_TABLES:
        op.drop_constraint(f"fk_{table_name}_tenant_id", table_name, type_="foreignkey")
        op.drop_index(f"ix_{table_name}_tenant_id", table_name=table_name)
        op.drop_column(table_name, "tenant_id")
