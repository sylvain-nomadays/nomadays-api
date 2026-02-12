"""Add sent_at timestamp to trips table.

Tracks when a trip proposal was published/sent to the client.

Revision ID: 061_add_trip_sent_at
Revises: 060_add_declined_booking_status
Create Date: 2026-02-11
"""
from alembic import op
import sqlalchemy as sa

revision = "061_add_trip_sent_at"
down_revision = "060_add_declined_booking_status"


def upgrade() -> None:
    op.add_column(
        "trips",
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("trips", "sent_at")
