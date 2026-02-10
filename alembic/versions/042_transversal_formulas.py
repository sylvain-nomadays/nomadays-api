"""Make formulas support transversal (trip-level) services.

Adds trip_id FK, is_transversal flag, makes trip_day_id nullable,
and makes service_day_start/end nullable for trip-level forfait items.

Revision ID: 042_transversal_formulas
Revises: 041_trip_day_meals
"""
from alembic import op
import sqlalchemy as sa

revision = "042_transversal_formulas"
down_revision = "041_trip_day_meals"
branch_labels = None
depends_on = None


def upgrade():
    # 1. Make trip_day_id nullable (was NOT NULL)
    op.alter_column(
        "formulas",
        "trip_day_id",
        existing_type=sa.BigInteger(),
        nullable=True,
    )

    # 2. Make service_day_start/end nullable for trip-level forfait items
    op.alter_column(
        "formulas",
        "service_day_start",
        existing_type=sa.Integer(),
        nullable=True,
    )
    op.alter_column(
        "formulas",
        "service_day_end",
        existing_type=sa.Integer(),
        nullable=True,
    )

    # 3. Add trip_id FK for transversal formulas
    op.add_column(
        "formulas",
        sa.Column("trip_id", sa.BigInteger(), nullable=True),
    )
    op.create_foreign_key(
        "fk_formulas_trip_id",
        "formulas",
        "trips",
        ["trip_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index("idx_formulas_trip_id", "formulas", ["trip_id"])

    # 4. Add is_transversal flag
    op.add_column(
        "formulas",
        sa.Column("is_transversal", sa.Boolean(), nullable=False, server_default="false"),
    )


def downgrade():
    # Remove is_transversal
    op.drop_column("formulas", "is_transversal")

    # Remove trip_id FK
    op.drop_index("idx_formulas_trip_id", table_name="formulas")
    op.drop_constraint("fk_formulas_trip_id", "formulas", type_="foreignkey")
    op.drop_column("formulas", "trip_id")

    # Restore service_day_start/end as NOT NULL
    op.alter_column(
        "formulas",
        "service_day_end",
        existing_type=sa.Integer(),
        nullable=False,
    )
    op.alter_column(
        "formulas",
        "service_day_start",
        existing_type=sa.Integer(),
        nullable=False,
    )

    # Restore trip_day_id as NOT NULL
    op.alter_column(
        "formulas",
        "trip_day_id",
        existing_type=sa.BigInteger(),
        nullable=False,
    )
