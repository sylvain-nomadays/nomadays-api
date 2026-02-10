"""Add location_id FK to trip_days

Links each trip day to a Location (static destination) for geographic organization.
"""

from alembic import op
import sqlalchemy as sa


revision = "039_trip_days_location_id"
down_revision = "038_items_cost_nature_nullable"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "trip_days",
        sa.Column("location_id", sa.BigInteger(), nullable=True),
    )
    op.create_foreign_key(
        "fk_trip_days_location_id",
        "trip_days",
        "locations",
        ["location_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("idx_trip_days_location_id", "trip_days", ["location_id"])


def downgrade():
    op.drop_index("idx_trip_days_location_id", table_name="trip_days")
    op.drop_constraint("fk_trip_days_location_id", "trip_days", type_="foreignkey")
    op.drop_column("trip_days", "location_id")
