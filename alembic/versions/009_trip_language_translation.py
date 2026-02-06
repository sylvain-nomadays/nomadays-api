"""Add language and translation fields to trips

Revision ID: 009_trip_language_translation
Revises: 008_distribution_fields
Create Date: 2025-02-06
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "009_trip_language_translation"
down_revision = "008_distribution_fields"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add language field with default 'fr'
    op.add_column(
        "trips",
        sa.Column("language", sa.String(5), nullable=False, server_default="fr"),
    )

    # Add source_trip_id for translations
    op.add_column(
        "trips",
        sa.Column("source_trip_id", sa.BigInteger(), nullable=True),
    )

    # Add foreign key constraint
    op.create_foreign_key(
        "fk_trips_source_trip_id",
        "trips",
        "trips",
        ["source_trip_id"],
        ["id"],
        ondelete="SET NULL",
    )

    # Add index for source_trip_id
    op.create_index(
        "ix_trips_source_trip_id",
        "trips",
        ["source_trip_id"],
    )

    # Add index for language
    op.create_index(
        "ix_trips_language",
        "trips",
        ["language"],
    )


def downgrade() -> None:
    op.drop_index("ix_trips_language", table_name="trips")
    op.drop_index("ix_trips_source_trip_id", table_name="trips")
    op.drop_constraint("fk_trips_source_trip_id", "trips", type_="foreignkey")
    op.drop_column("trips", "source_trip_id")
    op.drop_column("trips", "language")
