"""Create contract_status_enum type.

Revision ID: 027_contract_status_enum
Revises: 026_season_level
Create Date: 2025-02-07

Creates the PostgreSQL ENUM type for contract status.
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "027_contract_status_enum"
down_revision = "026_season_level"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create the enum type
    contract_status_enum = sa.Enum(
        'draft', 'active', 'expiring_soon', 'expired', 'renewed', 'archived',
        name='contract_status_enum'
    )
    contract_status_enum.create(op.get_bind(), checkfirst=True)

    # Update status column to use the enum type
    # First check if the column exists and what type it is
    # If it's already VARCHAR, we need to convert it
    op.execute("""
        DO $$
        BEGIN
            -- Try to alter the column type if it exists as varchar
            IF EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'contracts' AND column_name = 'status'
                AND data_type = 'character varying'
            ) THEN
                ALTER TABLE contracts
                ALTER COLUMN status TYPE contract_status_enum
                USING status::contract_status_enum;
            END IF;
        EXCEPTION
            WHEN others THEN
                -- Column might not exist or already be the correct type
                NULL;
        END $$;
    """)


def downgrade() -> None:
    # Convert back to varchar
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'contracts' AND column_name = 'status'
            ) THEN
                ALTER TABLE contracts
                ALTER COLUMN status TYPE varchar(20)
                USING status::varchar(20);
            END IF;
        EXCEPTION
            WHEN others THEN
                NULL;
        END $$;
    """)

    # Drop the enum type
    op.execute("DROP TYPE IF EXISTS contract_status_enum")
