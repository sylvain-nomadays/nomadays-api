"""Add HTML rich text fields for trip descriptions.

Adds *_html columns alongside existing plain text fields:
- description_html (rich text version of description_short)
- info_general_html, info_formalities_html, info_booking_conditions_html,
  info_cancellation_policy_html, info_additional_html
- slug (URL-friendly identifier for B2C)

Plain text fields remain for backward compatibility — the _html
variant takes priority when populated.

Revision ID: 054_trip_rich_text
Revises: 053_tarification_json
Create Date: 2026-02-11
"""
from alembic import op
import sqlalchemy as sa

revision = "054_trip_rich_text"
down_revision = "053_tarification_json"


def upgrade() -> None:
    # Rich text HTML fields
    op.add_column("trips", sa.Column("description_html", sa.Text(), nullable=True))
    op.add_column("trips", sa.Column("info_general_html", sa.Text(), nullable=True))
    op.add_column("trips", sa.Column("info_formalities_html", sa.Text(), nullable=True))
    op.add_column("trips", sa.Column("info_booking_conditions_html", sa.Text(), nullable=True))
    op.add_column("trips", sa.Column("info_cancellation_policy_html", sa.Text(), nullable=True))
    op.add_column("trips", sa.Column("info_additional_html", sa.Text(), nullable=True))

    # B2C slug
    op.add_column("trips", sa.Column("slug", sa.String(255), nullable=True))
    op.create_index("idx_trips_tenant_slug", "trips", ["tenant_id", "slug"], unique=True)


def downgrade() -> None:
    op.drop_index("idx_trips_tenant_slug", table_name="trips")
    op.drop_column("trips", "slug")
    op.drop_column("trips", "info_additional_html")
    op.drop_column("trips", "info_cancellation_policy_html")
    op.drop_column("trips", "info_booking_conditions_html")
    op.drop_column("trips", "info_formalities_html")
    op.drop_column("trips", "info_general_html")
    op.drop_column("trips", "description_html")
