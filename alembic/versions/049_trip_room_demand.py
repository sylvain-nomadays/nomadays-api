"""Add room_demand_json to trips.

Revision ID: 049_trip_room_demand
Revises: 048_category_prices
Create Date: 2025-02-10
"""
from alembic import op
import sqlalchemy as sa


revision = "049_trip_room_demand"
down_revision = "048_category_prices"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "trips",
        sa.Column("room_demand_json", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("trips", "room_demand_json")
