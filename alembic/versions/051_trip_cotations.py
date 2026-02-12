"""Add trip_cotations table for named quotation profiles.

Revision ID: 051_trip_cotations
Revises: 050_location_photos
Create Date: 2025-02-10
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


revision = "051_trip_cotations"
down_revision = "050_location_photos"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "trip_cotations",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("tenant_id", UUID(as_uuid=True), nullable=False),
        sa.Column(
            "trip_id",
            sa.BigInteger,
            sa.ForeignKey("trips.id", ondelete="CASCADE"),
            nullable=False,
        ),
        # Identity
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("sort_order", sa.Integer, server_default="0"),
        # Condition overrides: {condition_id: selected_option_id}
        sa.Column("condition_selections_json", sa.JSON, server_default="{}"),
        # Pax range
        sa.Column("min_pax", sa.Integer, server_default="2"),
        sa.Column("max_pax", sa.Integer, server_default="10"),
        # Auto-generated pax configs
        sa.Column("pax_configs_json", sa.JSON, server_default="[]"),
        # Calculation results
        sa.Column("results_json", sa.JSON, nullable=True),
        # Status
        sa.Column("status", sa.String(20), server_default="draft"),
        sa.Column("calculated_at", sa.DateTime(timezone=True), nullable=True),
        # Timestamps
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=True,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
            nullable=True,
        ),
    )

    # Indexes
    op.create_index(
        "ix_trip_cotations_tenant",
        "trip_cotations",
        ["tenant_id"],
    )
    op.create_index(
        "ix_trip_cotations_trip",
        "trip_cotations",
        ["trip_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_trip_cotations_trip", table_name="trip_cotations")
    op.drop_index("ix_trip_cotations_tenant", table_name="trip_cotations")
    op.drop_table("trip_cotations")
