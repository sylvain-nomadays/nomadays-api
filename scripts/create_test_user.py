#!/usr/bin/env python3
"""
Script to create a test user in the database linked to a Supabase Auth account.
This creates both a Tenant and a User record.
"""

import asyncio
import uuid
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import engine, async_session_maker
from app.models.tenant import Tenant
from app.models.user import User


# Configuration - User provided data
SUPABASE_USER_UUID = "7dc59612-ded3-40f7-ad9b-d350b5a99654"
SUPABASE_USER_EMAIL = "sylvain@nomadays.com"

# Tenant configuration
TENANT_NAME = "Nomadays Demo"
TENANT_SLUG = "nomadays-demo"
TENANT_CURRENCY = "EUR"
TENANT_COUNTRY = "MA"
TENANT_TYPE = "nomadays_hq"  # Enum: nomadays_hq, dmc, agency_b2b

# User configuration
USER_FIRST_NAME = "Sylvain"
USER_LAST_NAME = "Recouras"
USER_ROLE = "admin_nomadays"


async def create_tenant_if_not_exists(db: AsyncSession) -> Tenant:
    """Create the demo tenant if it doesn't exist."""

    # Check if tenant already exists
    result = await db.execute(
        select(Tenant).where(Tenant.slug == TENANT_SLUG)
    )
    tenant = result.scalar_one_or_none()

    if tenant:
        print(f"✓ Tenant '{TENANT_NAME}' already exists (ID: {tenant.id})")
        return tenant

    # Create new tenant using raw SQL to handle the enum type properly
    tenant_id = uuid.uuid4()
    await db.execute(
        text("""
            INSERT INTO tenants (id, name, slug, currency, country_code, type, is_active)
            VALUES (:id, :name, :slug, :currency, :country_code, CAST(:type AS tenant_type), :is_active)
        """),
        {
            "id": tenant_id,
            "name": TENANT_NAME,
            "slug": TENANT_SLUG,
            "currency": TENANT_CURRENCY,
            "country_code": TENANT_COUNTRY,
            "type": TENANT_TYPE,
            "is_active": True,
        }
    )
    await db.flush()

    # Fetch the created tenant
    result = await db.execute(
        select(Tenant).where(Tenant.id == tenant_id)
    )
    tenant = result.scalar_one()

    print(f"✓ Created tenant '{TENANT_NAME}' (ID: {tenant.id})")
    return tenant


async def create_user_if_not_exists(db: AsyncSession, tenant: Tenant) -> User:
    """Create the user linked to Supabase Auth if it doesn't exist."""

    user_uuid = uuid.UUID(SUPABASE_USER_UUID)

    # Check if user already exists by UUID
    result = await db.execute(
        select(User).where(User.id == user_uuid)
    )
    user = result.scalar_one_or_none()

    if user:
        print(f"✓ User '{SUPABASE_USER_EMAIL}' already exists (ID: {user.id})")
        return user

    # Check if user exists by email (different UUID)
    result = await db.execute(
        select(User).where(User.email == SUPABASE_USER_EMAIL)
    )
    existing_by_email = result.scalar_one_or_none()

    if existing_by_email:
        print(f"⚠ User with email '{SUPABASE_USER_EMAIL}' exists but with different UUID!")
        print(f"  Existing UUID: {existing_by_email.id}")
        print(f"  Supabase UUID: {user_uuid}")
        print(f"  Updating existing user to use Supabase UUID...")

        # Update the existing user's UUID to match Supabase
        existing_by_email.id = user_uuid
        await db.flush()
        print(f"✓ Updated user UUID to {user_uuid}")
        return existing_by_email

    # Create new user
    user = User(
        id=user_uuid,
        tenant_id=tenant.id,
        email=SUPABASE_USER_EMAIL,
        first_name=USER_FIRST_NAME,
        last_name=USER_LAST_NAME,
        role=USER_ROLE,
        is_active=True,
    )

    db.add(user)
    await db.flush()

    print(f"✓ Created user '{SUPABASE_USER_EMAIL}' (ID: {user.id})")
    return user


async def main():
    """Main function to create test user."""

    print("=" * 60)
    print("🚀 Nomadays - Create Test User")
    print("=" * 60)
    print()
    print(f"Supabase UUID: {SUPABASE_USER_UUID}")
    print(f"Email: {SUPABASE_USER_EMAIL}")
    print()

    async with async_session_maker() as db:
        try:
            # Create tenant
            print("📦 Creating tenant...")
            tenant = await create_tenant_if_not_exists(db)

            # Create user
            print()
            print("👤 Creating user...")
            user = await create_user_if_not_exists(db, tenant)

            # Commit all changes
            await db.commit()

            print()
            print("=" * 60)
            print("✅ Success!")
            print("=" * 60)
            print()
            print("Summary:")
            print(f"  Tenant: {tenant.name} ({tenant.slug})")
            print(f"  User: {user.first_name} {user.last_name}")
            print(f"  Email: {user.email}")
            print(f"  Role: {user.role}")
            print(f"  UUID: {user.id}")
            print()
            print("Next steps:")
            print("  1. Login at http://localhost:3000/login")
            print(f"  2. Use email: {SUPABASE_USER_EMAIL}")
            print("  3. Use your Supabase password")
            print()

        except Exception as e:
            await db.rollback()
            print(f"❌ Error: {e}")
            raise


if __name__ == "__main__":
    asyncio.run(main())
