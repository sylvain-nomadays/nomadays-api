"""Add tarification_json to trip_cotations.

Stores the public pricing configuration attached to a cotation:
- mode: range_web, per_person, per_group, service_list, enumeration
- entries: pricing entries specific to the chosen mode

Revision ID: 053_tarification_json
Revises: 052_cotation_mode_and_rooms
Create Date: 2026-02-10
"""
from alembic import op
import sqlalchemy as sa

revision = "053_tarification_json"
down_revision = "052_cotation_mode_and_rooms"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "trip_cotations",
        sa.Column("tarification_json", sa.JSON, nullable=True),
    )


def downgrade() -> None:
    op.drop_column("trip_cotations", "tarification_json")
