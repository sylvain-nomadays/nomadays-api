"""Add roadbook fields for client-facing enriched itinerary.

Adds HTML fields for roadbook content:
- roadbook_intro_html on trips (circuit-level intro: SIM card, formalities, tips)
- roadbook_html on trip_days (per-day annotations: meeting points, advice, tips)

Revision ID: 055_roadbook_fields
Revises: 054_trip_rich_text
Create Date: 2026-02-11
"""
from alembic import op
import sqlalchemy as sa

revision = "055_roadbook_fields"
down_revision = "054_trip_rich_text"


def upgrade() -> None:
    # Trip-level roadbook intro (practical info before departure)
    op.add_column("trips", sa.Column("roadbook_intro_html", sa.Text(), nullable=True))

    # Per-day roadbook annotation (meeting points, advice, restaurant tips)
    op.add_column("trip_days", sa.Column("roadbook_html", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("trip_days", "roadbook_html")
    op.drop_column("trips", "roadbook_intro_html")
