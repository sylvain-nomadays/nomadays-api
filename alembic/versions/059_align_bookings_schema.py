"""Align bookings table with Booking model — add missing columns, convert status to enum.

The bookings table was pre-existing with a different schema.
This migration adds the columns expected by the Booking model.

Revision ID: 059_align_bookings_schema
Revises: 058_create_bookings_table
Create Date: 2026-02-11
"""
from alembic import op
import sqlalchemy as sa

revision = "059_align_bookings_schema"
down_revision = "058_create_bookings_table"


def _col_exists(conn, table: str, column: str) -> bool:
    result = conn.execute(sa.text(
        "SELECT EXISTS (SELECT 1 FROM information_schema.columns "
        "WHERE table_name = :table AND column_name = :column)"
    ), {"table": table, "column": column})
    return result.scalar()


def _enum_exists(conn, enum_name: str) -> bool:
    result = conn.execute(sa.text(
        "SELECT EXISTS (SELECT 1 FROM pg_type WHERE typname = :name)"
    ), {"name": enum_name})
    return result.scalar()


def upgrade() -> None:
    conn = op.get_bind()

    # ── Ensure booking_status_enum exists ───────────────────────────────
    if not _enum_exists(conn, "booking_status_enum"):
        conn.execute(sa.text(
            "CREATE TYPE booking_status_enum AS ENUM "
            "('pending', 'sent', 'confirmed', 'modified', 'cancelled')"
        ))

    # ── Add missing columns ────────────────────────────────────────────

    # cost_nature_id — nullable first (existing rows don't have it),
    # we'll set a default then make it NOT NULL if needed
    if not _col_exists(conn, "bookings", "cost_nature_id"):
        conn.execute(sa.text(
            "ALTER TABLE bookings ADD COLUMN cost_nature_id BIGINT"
        ))
        # Set default for existing rows (use first cost_nature if available)
        conn.execute(sa.text(
            "UPDATE bookings SET cost_nature_id = ("
            "SELECT id FROM cost_natures LIMIT 1"
            ") WHERE cost_nature_id IS NULL"
        ))
        # Add FK constraint
        conn.execute(sa.text(
            "ALTER TABLE bookings ADD CONSTRAINT fk_bookings_cost_nature "
            "FOREIGN KEY (cost_nature_id) REFERENCES cost_natures(id) ON DELETE RESTRICT"
        ))

    # description
    if not _col_exists(conn, "bookings", "description"):
        conn.execute(sa.text(
            "ALTER TABLE bookings ADD COLUMN description VARCHAR(500) NOT NULL DEFAULT ''"
        ))
        # Fill from notes for existing rows
        conn.execute(sa.text(
            "UPDATE bookings SET description = COALESCE(notes, 'Réservation') "
            "WHERE description = ''"
        ))

    # service_date_start
    if not _col_exists(conn, "bookings", "service_date_start"):
        conn.execute(sa.text(
            "ALTER TABLE bookings ADD COLUMN service_date_start DATE"
        ))
        # Copy from service_date
        conn.execute(sa.text(
            "UPDATE bookings SET service_date_start = COALESCE(service_date, CURRENT_DATE) "
            "WHERE service_date_start IS NULL"
        ))
        # Make NOT NULL
        conn.execute(sa.text(
            "ALTER TABLE bookings ALTER COLUMN service_date_start SET NOT NULL"
        ))

    # service_date_end
    if not _col_exists(conn, "bookings", "service_date_end"):
        conn.execute(sa.text(
            "ALTER TABLE bookings ADD COLUMN service_date_end DATE"
        ))
        conn.execute(sa.text(
            "UPDATE bookings SET service_date_end = COALESCE(service_date, CURRENT_DATE) "
            "WHERE service_date_end IS NULL"
        ))
        conn.execute(sa.text(
            "ALTER TABLE bookings ALTER COLUMN service_date_end SET NOT NULL"
        ))

    # booked_amount
    if not _col_exists(conn, "bookings", "booked_amount"):
        conn.execute(sa.text(
            "ALTER TABLE bookings ADD COLUMN booked_amount DECIMAL(12,2) NOT NULL DEFAULT 0"
        ))
        # Copy from total_cost for existing rows
        conn.execute(sa.text(
            "UPDATE bookings SET booked_amount = COALESCE(total_cost, 0) "
            "WHERE booked_amount = 0 AND total_cost IS NOT NULL"
        ))

    # vat_recoverable
    if not _col_exists(conn, "bookings", "vat_recoverable"):
        conn.execute(sa.text(
            "ALTER TABLE bookings ADD COLUMN vat_recoverable BOOLEAN DEFAULT false"
        ))

    # ── Convert status from VARCHAR to booking_status_enum ─────────────
    # Check if status is currently varchar (not already enum)
    result = conn.execute(sa.text(
        "SELECT data_type FROM information_schema.columns "
        "WHERE table_name = 'bookings' AND column_name = 'status'"
    ))
    row = result.fetchone()
    if row and row[0] == 'character varying':
        # Ensure existing values are valid enum values
        conn.execute(sa.text(
            "UPDATE bookings SET status = 'pending' "
            "WHERE status IS NULL OR status NOT IN "
            "('pending', 'sent', 'confirmed', 'modified', 'cancelled')"
        ))
        # Drop existing default (it's a varchar default that can't auto-cast)
        conn.execute(sa.text(
            "ALTER TABLE bookings ALTER COLUMN status DROP DEFAULT"
        ))
        # Convert column to enum type
        conn.execute(sa.text(
            "ALTER TABLE bookings "
            "ALTER COLUMN status TYPE booking_status_enum "
            "USING status::booking_status_enum"
        ))
        # Set new default as enum value
        conn.execute(sa.text(
            "ALTER TABLE bookings ALTER COLUMN status SET DEFAULT 'pending'::booking_status_enum"
        ))


def downgrade() -> None:
    conn = op.get_bind()

    # Convert status back to varchar
    result = conn.execute(sa.text(
        "SELECT data_type, udt_name FROM information_schema.columns "
        "WHERE table_name = 'bookings' AND column_name = 'status'"
    ))
    row = result.fetchone()
    if row and row[1] == 'booking_status_enum':
        conn.execute(sa.text(
            "ALTER TABLE bookings ALTER COLUMN status TYPE VARCHAR(50) "
            "USING status::text"
        ))

    # Drop added columns (only the ones we added)
    for col in ["vat_recoverable", "booked_amount", "service_date_end",
                "service_date_start", "description", "cost_nature_id"]:
        if _col_exists(conn, "bookings", col):
            conn.execute(sa.text(f"ALTER TABLE bookings DROP COLUMN {col}"))
