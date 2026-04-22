"""Add users + notifications tables and audit-log indexes

Revision ID: rcm_011
Revises: rcm_010
Create Date: 2026-04-22 04:00:00.000000

Adds:
- `users` table for tenant-scoped DB-backed authentication (B5 dev_login refactor).
- `notifications` table for in-app notification feed (B5 scheduler/denial wiring).
- Indexes on `security_audit_log` for the new viewer endpoint
  (tenant_id+timestamp DESC for the default sort, plus action and resource_type
  for the FE filter dropdowns).
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID


revision = "rcm_011"
down_revision = "rcm_010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ---- users ----
    op.create_table(
        "users",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("full_name", sa.String(255), nullable=True),
        sa.Column("password_hash", sa.String(255), nullable=True),
        sa.Column("roles", ARRAY(sa.String()), nullable=False, server_default="{}"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("tenant_id", "email", name="uq_users_tenant_email"),
    )
    op.create_index("ix_users_tenant_id", "users", ["tenant_id"])
    op.create_index("ix_users_email_active", "users", ["email", "is_active"])

    # ---- notifications ----
    op.create_table(
        "notifications",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("user_id", UUID(as_uuid=True), nullable=True),
        sa.Column("type", sa.String(64), nullable=False),
        sa.Column("severity", sa.String(16), nullable=False, server_default="info"),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("link_url", sa.String(512), nullable=True),
        sa.Column("metadata", JSONB(), nullable=True),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_notifications_tenant_id", "notifications", ["tenant_id"])
    op.create_index("ix_notifications_user_id", "notifications", ["user_id"])
    op.create_index("ix_notifications_type", "notifications", ["type"])
    op.create_index("ix_notifications_created_at", "notifications", ["created_at"])
    op.create_index(
        "ix_notifications_tenant_user_unread",
        "notifications",
        ["tenant_id", "user_id", "read_at"],
    )

    # ---- security_audit_log indexes for the viewer endpoint ----
    # Single-column indexes on action / resource_type / resource_id / tenant_id /
    # timestamp already exist (auto-created from `index=True` on the model in
    # rcm_005). Here we ONLY add the compound indexes the new viewer needs:
    #   1. (tenant_id, timestamp DESC) — default list query.
    #   2. (resource_type, resource_id) — "what happened to claim 42" lookups.
    # We use IF NOT EXISTS so re-runs against partially-migrated databases
    # are safe.
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_security_audit_log_tenant_timestamp "
        "ON security_audit_log (tenant_id, timestamp DESC)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_security_audit_log_resource_type_id "
        "ON security_audit_log (resource_type, resource_id)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_security_audit_log_resource_type_id")
    op.execute("DROP INDEX IF EXISTS ix_security_audit_log_tenant_timestamp")

    op.drop_index("ix_notifications_tenant_user_unread", table_name="notifications")
    op.drop_index("ix_notifications_created_at", table_name="notifications")
    op.drop_index("ix_notifications_type", table_name="notifications")
    op.drop_index("ix_notifications_user_id", table_name="notifications")
    op.drop_index("ix_notifications_tenant_id", table_name="notifications")
    op.drop_table("notifications")

    op.drop_index("ix_users_email_active", table_name="users")
    op.drop_index("ix_users_tenant_id", table_name="users")
    op.drop_table("users")
