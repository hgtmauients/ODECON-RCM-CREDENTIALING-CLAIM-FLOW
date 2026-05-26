"""
Seed a deterministic tenant/admin identity for CI full-stack browser tests.

Idempotent:
- Creates tenant when missing
- Creates user when missing
- Resets password + roles when present
"""

from __future__ import annotations

import argparse
import asyncio
from uuid import UUID

from sqlalchemy import and_, select

from core.database import async_session_factory
from core.password import hash_password
from models.tenant import Tenant
from models.user import User


async def _seed(*, tenant_id: str, tenant_name: str, tenant_slug: str, email: str, password: str, full_name: str) -> None:
    tenant_uuid = UUID(str(tenant_id))
    async with async_session_factory() as db:
        tenant_result = await db.execute(select(Tenant).where(Tenant.id == tenant_uuid))
        tenant = tenant_result.scalar_one_or_none()
        if tenant is None:
            tenant = Tenant(
                id=tenant_uuid,
                name=tenant_name,
                slug=tenant_slug,
                is_active=True,
            )
            db.add(tenant)
        else:
            tenant.name = tenant_name
            tenant.slug = tenant_slug
            tenant.is_active = True

        user_result = await db.execute(
            select(User).where(and_(User.tenant_id == tenant_uuid, User.email == email.lower()))
        )
        user = user_result.scalar_one_or_none()
        if user is None:
            user = User(
                tenant_id=tenant_uuid,
                email=email.lower(),
                full_name=full_name,
                password_hash=hash_password(password),
                roles=["super_admin", "admin", "billing", "credentialing"],
                is_active=True,
                created_by="ci-e2e-seed",
            )
            db.add(user)
        else:
            user.full_name = full_name
            user.password_hash = hash_password(password)
            user.roles = ["super_admin", "admin", "billing", "credentialing"]
            user.is_active = True

        await db.commit()


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed CI full-stack E2E user")
    parser.add_argument("--tenant-id", default="00000000-0000-0000-0000-000000000001")
    parser.add_argument("--tenant-name", default="CI E2E Tenant")
    parser.add_argument("--tenant-slug", default="ci-e2e-tenant")
    parser.add_argument("--email", default="ci.e2e.fullstack@noodledoc.com")
    parser.add_argument("--password", default="admin")
    parser.add_argument("--full-name", default="CI E2E Admin")
    args = parser.parse_args()
    asyncio.run(
        _seed(
            tenant_id=args.tenant_id,
            tenant_name=args.tenant_name,
            tenant_slug=args.tenant_slug,
            email=args.email,
            password=args.password,
            full_name=args.full_name,
        )
    )
    print("Seeded CI E2E tenant/admin identity.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
