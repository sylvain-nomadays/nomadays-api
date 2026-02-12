"""Add trip selection fields to dossiers table.

Stores which trip/cotation was selected by the client,
along with final pax count and selection timestamp.

Revision ID: 062_dossier_selection_fields
Revises: 061_add_trip_sent_at
Create Date: 2026-02-12
"""
from alembic import op
import sqlalchemy as sa

revision = "062_dossier_selection_fields"
down_revision = "061_add_trip_sent_at"


def upgrade() -> None:
    op.add_column(
        "dossiers",
        sa.Column("selected_trip_id", sa.BigInteger(), nullable=True),
    )
    op.add_column(
        "dossiers",
        sa.Column("selected_cotation_id", sa.BigInteger(), nullable=True),
    )
    op.add_column(
        "dossiers",
        sa.Column("selected_cotation_name", sa.String(100), nullable=True),
    )
    op.add_column(
        "dossiers",
        sa.Column("final_pax_count", sa.Integer(), nullable=True),
    )
    op.add_column(
        "dossiers",
        sa.Column("selected_at", sa.DateTime(timezone=True), nullable=True),
    )
    # Foreign key to trips
    op.create_foreign_key(
        "fk_dossiers_selected_trip",
        "dossiers",
        "trips",
        ["selected_trip_id"],
        ["id"],
        ondelete="SET NULL",
    )
    # Index for quick lookup
    op.create_index(
        "idx_dossiers_selected_trip_id",
        "dossiers",
        ["selected_trip_id"],
    )


def downgrade() -> None:
    op.drop_index("idx_dossiers_selected_trip_id", table_name="dossiers")
    op.drop_constraint("fk_dossiers_selected_trip", "dossiers", type_="foreignkey")
    op.drop_column("dossiers", "selected_at")
    op.drop_column("dossiers", "final_pax_count")
    op.drop_column("dossiers", "selected_cotation_name")
    op.drop_column("dossiers", "selected_cotation_id")
    op.drop_column("dossiers", "selected_trip_id")
