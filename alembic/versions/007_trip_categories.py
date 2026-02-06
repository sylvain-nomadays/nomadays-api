"""Trip categories: online, gir, template, custom

Revision ID: 007_trip_categories
Revises: 006_partner_agencies
Create Date: 2024-02-06

Updates trip types to new categories:
- online: Published circuits on website (masters)
- gir: Group departures with fixed dates
- template: Internal templates (library)
- custom: Custom circuits for clients

Also adds:
- master_trip_id: Links GIR to their master online circuit
- is_published: Publication status for online circuits
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "007_trip_categories"
down_revision = "006_partner_agencies"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add new columns
    op.add_column(
        "trips",
        sa.Column("master_trip_id", sa.BigInteger(), nullable=True),
    )
    op.add_column(
        "trips",
        sa.Column("is_published", sa.Boolean(), nullable=False, server_default="false"),
    )

    # Add foreign key for master_trip_id
    op.create_foreign_key(
        "fk_trips_master_trip",
        "trips",
        "trips",
        ["master_trip_id"],
        ["id"],
        ondelete="SET NULL",
    )

    # Create index for master_trip_id
    op.create_index("ix_trips_master_trip_id", "trips", ["master_trip_id"])

    # Migrate existing data (type is VARCHAR, not enum)
    # - 'website' -> 'online'
    # - 'client' -> 'custom'
    # - 'template' stays as 'template'
    op.execute("""
        UPDATE trips SET type = 'online' WHERE type = 'website';
        UPDATE trips SET type = 'custom' WHERE type = 'client';
    """)


def downgrade() -> None:
    # Revert data migration
    op.execute("""
        UPDATE trips SET type = 'website' WHERE type = 'online';
        UPDATE trips SET type = 'client' WHERE type = 'custom';
        UPDATE trips SET type = 'template' WHERE type = 'gir';
    """)

    # Drop index and foreign key
    op.drop_index("ix_trips_master_trip_id", table_name="trips")
    op.drop_constraint("fk_trips_master_trip", "trips", type_="foreignkey")

    # Drop columns
    op.drop_column("trips", "is_published")
    op.drop_column("trips", "master_trip_id")
