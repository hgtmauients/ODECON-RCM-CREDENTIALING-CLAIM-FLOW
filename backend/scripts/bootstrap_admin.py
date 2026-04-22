"""
Seed the first super_admin user for a tenant.

Idempotent: if the email already exists in the tenant, no-op (or update
the password if BOOTSTRAP_OVERWRITE=1 is set).

Usage:
    docker exec noodledoc-backend-1 \
        python -m scripts.bootstrap_admin \
        --tenant 00000000-0000-0000-0000-000000000001 \
        --email admin@yourcompany.com \
        --password $(openssl rand -base64 18)
"""

import argparse
import asyncio
import os
import sys

from sqlalchemy import select, and_

from core.database import async_session_factory
from core.password import hash_password
from models.user import User


async def _bootstrap(tenant_id: str, email: str, password: str, full_name: str | None) -> int:
    overwrite = os.getenv("BOOTSTRAP_OVERWRITE", "").lower() in ("1", "true", "yes")
    async with async_session_factory() as db:
        existing = await db.execute(
            select(User).where(and_(
                User.email == email.lower(),
                User.tenant_id == tenant_id,
            ))
        )
        user = existing.scalar_one_or_none()
        if user and not overwrite:
            print(f"User {email} already exists in tenant {tenant_id}; skipping (set BOOTSTRAP_OVERWRITE=1 to update).")
            return 0
        if user:
            user.password_hash = hash_password(password)
            user.is_active = True
            roles = list(user.roles or [])
            if "super_admin" not in roles:
                roles.append("super_admin")
            user.roles = roles
            print(f"Updated existing user {email} (super_admin granted, password reset)")
        else:
            user = User(
                tenant_id=tenant_id,
                email=email.lower(),
                full_name=full_name,
                password_hash=hash_password(password),
                roles=["super_admin", "admin", "billing", "credentialing"],
                is_active=True,
                created_by="bootstrap",
            )
            db.add(user)
            print(f"Created super_admin {email} in tenant {tenant_id}")
        await db.commit()
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Bootstrap the first super_admin user")
    parser.add_argument("--tenant", required=True, help="Tenant UUID")
    parser.add_argument("--email", required=True)
    parser.add_argument("--password", required=True)
    parser.add_argument("--full-name", default=None)
    args = parser.parse_args()
    return asyncio.run(_bootstrap(args.tenant, args.email, args.password, args.full_name))


if __name__ == "__main__":
    sys.exit(main())
