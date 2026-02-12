"""Add mode and room_demand_override_json to trip_cotations.

Supports two cotation modes:
- "range": grid from min_pax to max_pax (existing behavior, default)
- "custom": fixed composition (e.g. 2 adults + 1 child)

Also adds room_demand_override_json for per-cotation room allocation override.

Revision ID: 052_cotation_mode_and_rooms
Revises: 051_trip_cotations
Create Date: 2025-02-10
"""
from alembic import op
import sqlalchemy as sa


revision = "052_cotation_mode_and_rooms"
down_revision = "051_trip_cotations"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Mode column: "range" (default) or "custom"
    op.add_column(
        "trip_cotations",
        sa.Column("mode", sa.String(20), server_default="range", nullable=False),
    )
    # Room demand override (optional JSON array)
    op.add_column(
        "trip_cotations",
        sa.Column("room_demand_override_json", sa.JSON, nullable=True),
    )


def downgrade() -> None:
    op.drop_column("trip_cotations", "room_demand_override_json")
    op.drop_column("trip_cotations", "mode")
