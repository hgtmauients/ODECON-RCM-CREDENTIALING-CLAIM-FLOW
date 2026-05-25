"""
Fail CI when tenant-table RLS coverage drifts.

Checks every table in the current schema that has a tenant_id column and
requires:
  1) relrowsecurity = true
  2) relforcerowsecurity = true
  3) at least one policy in pg_policies
"""

from __future__ import annotations

import asyncio
import os
import sys

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine


async def _main() -> int:
    database_url = os.getenv("DATABASE_URL", "").strip()
    if not database_url:
        print("DATABASE_URL is required", file=sys.stderr)
        return 2

    engine = create_async_engine(database_url, pool_pre_ping=True)
    try:
        async with engine.connect() as conn:
            tenant_tables_result = await conn.execute(
                text(
                    """
                    SELECT table_name
                    FROM information_schema.columns
                    WHERE table_schema = current_schema()
                      AND column_name = 'tenant_id'
                    ORDER BY table_name
                    """
                )
            )
            tenant_tables = [row[0] for row in tenant_tables_result.all()]

            coverage_rows = await conn.execute(
                text(
                    """
                    SELECT c.relname AS table_name, c.relrowsecurity, c.relforcerowsecurity
                    FROM pg_class c
                    JOIN pg_namespace n ON n.oid = c.relnamespace
                    WHERE n.nspname = current_schema()
                      AND c.relkind = 'r'
                    ORDER BY c.relname
                    """
                )
            )
            class_state = {
                row[0]: {"rowsecurity": bool(row[1]), "forcerowsecurity": bool(row[2])}
                for row in coverage_rows.all()
            }

            policy_rows = await conn.execute(
                text(
                    """
                    SELECT tablename
                    FROM pg_policies
                    WHERE schemaname = current_schema()
                    GROUP BY tablename
                    """
                )
            )
            policy_tables = {row[0] for row in policy_rows.all()}

        missing_row_security: list[str] = []
        missing_force_rls: list[str] = []
        missing_policy: list[str] = []
        for table_name in tenant_tables:
            state = class_state.get(table_name, {"rowsecurity": False, "forcerowsecurity": False})
            if not state["rowsecurity"]:
                missing_row_security.append(table_name)
            if not state["forcerowsecurity"]:
                missing_force_rls.append(table_name)
            if table_name not in policy_tables:
                missing_policy.append(table_name)

        if missing_row_security or missing_force_rls or missing_policy:
            print("RLS assurance gate failed.", file=sys.stderr)
            if missing_row_security:
                print(f" - Missing row security: {', '.join(missing_row_security)}", file=sys.stderr)
            if missing_force_rls:
                print(f" - Missing force RLS: {', '.join(missing_force_rls)}", file=sys.stderr)
            if missing_policy:
                print(f" - Missing policies: {', '.join(missing_policy)}", file=sys.stderr)
            return 1

        print(f"RLS assurance gate passed for {len(tenant_tables)} tenant table(s).")
        return 0
    finally:
        await engine.dispose()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_main()))
