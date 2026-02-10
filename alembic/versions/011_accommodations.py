"""Add accommodation tables for suppliers

Revision ID: 011_accommodations
Revises: 010_translation_cache
Create Date: 2025-02-07
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, ARRAY


# revision identifiers, used by Alembic.
revision = "011_accommodations"
down_revision = "010_translation_cache"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # =========================================================================
    # 1. Create accommodations table
    # =========================================================================
    op.create_table(
        "accommodations",
        # Primary key and tenant
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", UUID(as_uuid=True), nullable=False),
        sa.Column("supplier_id", sa.BigInteger(), nullable=False),

        # Basic info
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("star_rating", sa.Integer(), nullable=True),

        # Location
        sa.Column("address", sa.String(500), nullable=True),
        sa.Column("lat", sa.Numeric(10, 7), nullable=True),
        sa.Column("lng", sa.Numeric(10, 7), nullable=True),

        # Check-in / Check-out
        sa.Column("check_in_time", sa.String(5), nullable=True),
        sa.Column("check_out_time", sa.String(5), nullable=True),

        # Amenities (stored as array)
        sa.Column("amenities", ARRAY(sa.String()), nullable=True),

        # Contact
        sa.Column("reservation_email", sa.String(255), nullable=True),
        sa.Column("reservation_phone", sa.String(100), nullable=True),
        sa.Column("website_url", sa.String(500), nullable=True),

        # External provider (for availability sync)
        sa.Column("external_provider", sa.String(50), nullable=True),
        sa.Column("external_id", sa.String(255), nullable=True),

        # Status
        sa.Column("status", sa.String(20), server_default="active", nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),

        # Timestamps
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),

        # Constraints
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["supplier_id"], ["suppliers.id"], ondelete="CASCADE"),
    )

    # Indexes for accommodations
    op.create_index("ix_accommodations_tenant_id", "accommodations", ["tenant_id"])
    op.create_index("ix_accommodations_supplier_id", "accommodations", ["supplier_id"])
    op.create_index("ix_accommodations_status", "accommodations", ["status"])

    # =========================================================================
    # 2. Create room_categories table
    # =========================================================================
    op.create_table(
        "room_categories",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("accommodation_id", sa.BigInteger(), nullable=False),

        # Basic info
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("code", sa.String(10), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),

        # Occupancy
        sa.Column("min_occupancy", sa.Integer(), server_default="1", nullable=False),
        sa.Column("max_occupancy", sa.Integer(), server_default="2", nullable=False),
        sa.Column("max_adults", sa.Integer(), server_default="2", nullable=False),
        sa.Column("max_children", sa.Integer(), server_default="1", nullable=False),

        # Bed types available (stored as array)
        sa.Column("available_bed_types", ARRAY(sa.String()), server_default="{DBL}", nullable=False),

        # Size
        sa.Column("size_sqm", sa.Integer(), nullable=True),

        # Amenities
        sa.Column("amenities", ARRAY(sa.String()), nullable=True),

        # Status & ordering
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("sort_order", sa.Integer(), server_default="0", nullable=False),

        # Constraints
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["accommodation_id"], ["accommodations.id"], ondelete="CASCADE"),
    )

    # Indexes for room_categories
    op.create_index("ix_room_categories_accommodation_id", "room_categories", ["accommodation_id"])
    op.create_index("ix_room_categories_code", "room_categories", ["code"])

    # =========================================================================
    # 3. Create accommodation_seasons table
    # =========================================================================
    op.create_table(
        "accommodation_seasons",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("accommodation_id", sa.BigInteger(), nullable=False),

        # Basic info
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("code", sa.String(10), nullable=True),

        # Season type: fixed, recurring, weekday
        sa.Column("season_type", sa.String(20), server_default="fixed", nullable=False),

        # Dates (for fixed and recurring)
        # For fixed: YYYY-MM-DD, for recurring: MM-DD
        sa.Column("start_date", sa.String(10), nullable=True),
        sa.Column("end_date", sa.String(10), nullable=True),

        # Days of week (for weekday type) - stored as array of integers (0=Sun, 6=Sat)
        sa.Column("weekdays", ARRAY(sa.Integer()), nullable=True),

        # Year (null = recurring every year)
        sa.Column("year", sa.Integer(), nullable=True),

        # Priority (higher wins in overlapping)
        sa.Column("priority", sa.Integer(), server_default="1", nullable=False),

        # Status
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),

        # Timestamps
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),

        # Constraints
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["accommodation_id"], ["accommodations.id"], ondelete="CASCADE"),
    )

    # Indexes for accommodation_seasons
    op.create_index("ix_accommodation_seasons_accommodation_id", "accommodation_seasons", ["accommodation_id"])
    op.create_index("ix_accommodation_seasons_code", "accommodation_seasons", ["code"])
    op.create_index("ix_accommodation_seasons_priority", "accommodation_seasons", ["priority"])

    # =========================================================================
    # 4. Create room_rates table
    # =========================================================================
    op.create_table(
        "room_rates",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("accommodation_id", sa.BigInteger(), nullable=False),
        sa.Column("room_category_id", sa.BigInteger(), nullable=False),
        sa.Column("season_id", sa.BigInteger(), nullable=True),  # NULL = default rate

        # Bed type
        sa.Column("bed_type", sa.String(10), server_default="DBL", nullable=False),

        # Occupancy base
        sa.Column("base_occupancy", sa.Integer(), server_default="2", nullable=False),

        # Rate type
        sa.Column("rate_type", sa.String(30), server_default="per_night", nullable=False),

        # Cost
        sa.Column("cost", sa.Numeric(12, 2), nullable=False),
        sa.Column("currency", sa.String(3), server_default="EUR", nullable=False),

        # Supplements
        sa.Column("single_supplement", sa.Numeric(12, 2), nullable=True),
        sa.Column("extra_adult", sa.Numeric(12, 2), nullable=True),
        sa.Column("extra_child", sa.Numeric(12, 2), nullable=True),

        # Meal plan: RO, BB, HB, FB, AI
        sa.Column("meal_plan", sa.String(5), server_default="BB", nullable=False),

        # Validity dates
        sa.Column("valid_from", sa.Date(), nullable=True),
        sa.Column("valid_to", sa.Date(), nullable=True),

        # Notes
        sa.Column("notes", sa.Text(), nullable=True),

        # Status
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),

        # Constraints
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["accommodation_id"], ["accommodations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["room_category_id"], ["room_categories.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["season_id"], ["accommodation_seasons.id"], ondelete="SET NULL"),
    )

    # Indexes for room_rates
    op.create_index("ix_room_rates_accommodation_id", "room_rates", ["accommodation_id"])
    op.create_index("ix_room_rates_room_category_id", "room_rates", ["room_category_id"])
    op.create_index("ix_room_rates_season_id", "room_rates", ["season_id"])
    op.create_index("ix_room_rates_meal_plan", "room_rates", ["meal_plan"])
    op.create_index("ix_room_rates_bed_type", "room_rates", ["bed_type"])

    # Unique constraint for rate combinations
    op.create_index(
        "uq_room_rates_combination",
        "room_rates",
        ["room_category_id", "season_id", "bed_type", "meal_plan"],
        unique=True,
    )


def downgrade() -> None:
    # Drop tables in reverse order (due to foreign keys)
    op.drop_table("room_rates")
    op.drop_table("accommodation_seasons")
    op.drop_table("room_categories")
    op.drop_table("accommodations")
