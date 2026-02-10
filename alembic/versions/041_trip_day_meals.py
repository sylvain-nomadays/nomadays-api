"""Add meal inclusion toggles to trip_days.

Three booleans to track whether breakfast, lunch, and dinner
are included for each day of the trip.

Revision ID: 041_trip_day_meals
Revises: 040_item_payment_flow
"""
from alembic import op
import sqlalchemy as sa

revision = "041_trip_day_meals"
down_revision = "040_item_payment_flow"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "trip_days",
        sa.Column("breakfast_included", sa.Boolean(), nullable=False, server_default="false"),
    )
    op.add_column(
        "trip_days",
        sa.Column("lunch_included", sa.Boolean(), nullable=False, server_default="false"),
    )
    op.add_column(
        "trip_days",
        sa.Column("dinner_included", sa.Boolean(), nullable=False, server_default="false"),
    )


def downgrade():
    op.drop_column("trip_days", "dinner_included")
    op.drop_column("trip_days", "lunch_included")
    op.drop_column("trip_days", "breakfast_included")
