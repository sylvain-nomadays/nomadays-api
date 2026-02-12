"""Create bookings and payment_schedule tables.

Revision ID: 058_create_bookings_table
Revises: 057_pre_booking_system
Create Date: 2026-02-11
"""
from alembic import op
import sqlalchemy as sa


revision = "058_create_bookings_table"
down_revision = "057_pre_booking_system"


def _table_exists(conn, table: str) -> bool:
    result = conn.execute(sa.text(
        "SELECT EXISTS (SELECT 1 FROM information_schema.tables "
        "WHERE table_name = :table)"
    ), {"table": table})
    return result.scalar()


def _enum_exists(conn, enum_name: str) -> bool:
    result = conn.execute(sa.text(
        "SELECT EXISTS (SELECT 1 FROM pg_type WHERE typname = :name)"
    ), {"name": enum_name})
    return result.scalar()


def _index_exists(conn, index_name: str) -> bool:
    result = conn.execute(sa.text(
        "SELECT EXISTS (SELECT 1 FROM pg_indexes WHERE indexname = :idx)"
    ), {"idx": index_name})
    return result.scalar()


def upgrade() -> None:
    conn = op.get_bind()

    # ── Create enums (idempotent) ─────────────────────────────────────────
    if not _enum_exists(conn, "booking_status_enum"):
        conn.execute(sa.text(
            "CREATE TYPE booking_status_enum AS ENUM "
            "('pending', 'sent', 'confirmed', 'modified', 'cancelled')"
        ))

    if not _enum_exists(conn, "payment_type_enum"):
        conn.execute(sa.text(
            "CREATE TYPE payment_type_enum AS ENUM "
            "('deposit', 'balance', 'full', 'installment')"
        ))

    if not _enum_exists(conn, "payment_status_enum"):
        conn.execute(sa.text(
            "CREATE TYPE payment_status_enum AS ENUM "
            "('pending', 'due_soon', 'overdue', 'paid', 'cancelled')"
        ))

    # ── Create bookings table (raw SQL to avoid SQLAlchemy enum issues) ──
    if not _table_exists(conn, "bookings"):
        conn.execute(sa.text("""
            CREATE TABLE bookings (
                id BIGSERIAL PRIMARY KEY,
                tenant_id UUID NOT NULL,
                trip_id BIGINT NOT NULL REFERENCES trips(id) ON DELETE CASCADE,
                item_id BIGINT REFERENCES items(id) ON DELETE SET NULL,
                supplier_id BIGINT REFERENCES suppliers(id) ON DELETE SET NULL,
                cost_nature_id BIGINT NOT NULL REFERENCES cost_natures(id) ON DELETE RESTRICT,
                description VARCHAR(500) NOT NULL,
                service_date_start DATE NOT NULL,
                service_date_end DATE NOT NULL,
                booked_amount DECIMAL(12,2) NOT NULL,
                currency VARCHAR(3) DEFAULT 'EUR',
                vat_recoverable BOOLEAN DEFAULT false,
                status booking_status_enum DEFAULT 'pending',
                confirmation_ref VARCHAR(255),
                is_pre_booking BOOLEAN DEFAULT false,
                requested_by_id UUID REFERENCES users(id) ON DELETE SET NULL,
                assigned_to_id UUID REFERENCES users(id) ON DELETE SET NULL,
                email_sent_at TIMESTAMPTZ,
                email_sent_to VARCHAR(255),
                supplier_response_note TEXT,
                formula_id BIGINT REFERENCES formulas(id) ON DELETE SET NULL,
                pax_count INTEGER,
                room_config JSONB,
                guest_names TEXT,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                updated_at TIMESTAMPTZ DEFAULT now()
            )
        """))

    # Indexes for bookings
    if not _index_exists(conn, "idx_bookings_trip_id"):
        conn.execute(sa.text(
            "CREATE INDEX idx_bookings_trip_id ON bookings(trip_id)"
        ))

    if not _index_exists(conn, "idx_bookings_pre_booking"):
        conn.execute(sa.text(
            "CREATE INDEX idx_bookings_pre_booking ON bookings(tenant_id, is_pre_booking, status)"
        ))

    # ── Create payment_schedule table ─────────────────────────────────────
    if not _table_exists(conn, "payment_schedule"):
        conn.execute(sa.text("""
            CREATE TABLE payment_schedule (
                id BIGSERIAL PRIMARY KEY,
                tenant_id UUID NOT NULL,
                booking_id BIGINT NOT NULL REFERENCES bookings(id) ON DELETE CASCADE,
                due_date DATE NOT NULL,
                amount DECIMAL(12,2) NOT NULL,
                currency VARCHAR(3) DEFAULT 'EUR',
                type payment_type_enum DEFAULT 'full',
                status payment_status_enum DEFAULT 'pending',
                paid_date DATE,
                paid_amount DECIMAL(12,2),
                payment_ref VARCHAR(255),
                created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                updated_at TIMESTAMPTZ DEFAULT now()
            )
        """))

    if not _index_exists(conn, "idx_payment_schedule_booking_id"):
        conn.execute(sa.text(
            "CREATE INDEX idx_payment_schedule_booking_id ON payment_schedule(booking_id)"
        ))


def downgrade() -> None:
    conn = op.get_bind()

    if _table_exists(conn, "payment_schedule"):
        conn.execute(sa.text("DROP TABLE payment_schedule"))

    if _table_exists(conn, "bookings"):
        conn.execute(sa.text("DROP TABLE bookings"))

    if _enum_exists(conn, "payment_status_enum"):
        conn.execute(sa.text("DROP TYPE payment_status_enum"))

    if _enum_exists(conn, "payment_type_enum"):
        conn.execute(sa.text("DROP TYPE payment_type_enum"))

    if _enum_exists(conn, "booking_status_enum"):
        conn.execute(sa.text("DROP TYPE booking_status_enum"))
