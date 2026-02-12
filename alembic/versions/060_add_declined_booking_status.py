"""Add 'declined' and 'pending_cancellation' values to booking_status_enum.

- declined: supplier refuses the booking (hotel full, dates unavailable)
- pending_cancellation: seller wants to cancel, awaiting cancellation email to supplier

Revision ID: 060_add_declined_booking_status
Revises: 059_align_bookings_schema
Create Date: 2026-02-11
"""
from alembic import op
import sqlalchemy as sa

revision = "060_add_declined_booking_status"
down_revision = "059_align_bookings_schema"


def _enum_value_exists(conn, enum_name: str, value: str) -> bool:
    result = conn.execute(sa.text(
        "SELECT EXISTS ("
        "  SELECT 1 FROM pg_enum "
        "  JOIN pg_type ON pg_enum.enumtypid = pg_type.oid "
        "  WHERE pg_type.typname = :enum_name "
        "  AND pg_enum.enumlabel = :value"
        ")"
    ), {"enum_name": enum_name, "value": value})
    return result.scalar()


def upgrade() -> None:
    conn = op.get_bind()

    for value in ("declined", "pending_cancellation"):
        if not _enum_value_exists(conn, "booking_status_enum", value):
            conn.execute(sa.text(
                f"ALTER TYPE booking_status_enum ADD VALUE '{value}'"
            ))


def downgrade() -> None:
    # PostgreSQL does not support removing enum values.
    pass
