"""Add pre-booking system: supplier flag, booking extensions, notifications table.

Revision ID: 057_pre_booking_system
Revises: 056_template_system
Create Date: 2026-02-11
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision = "057_pre_booking_system"
down_revision = "056_template_system"


def _col_exists(conn, table: str, column: str) -> bool:
    result = conn.execute(sa.text(
        "SELECT EXISTS (SELECT 1 FROM information_schema.columns "
        "WHERE table_name = :table AND column_name = :column)"
    ), {"table": table, "column": column})
    return result.scalar()


def _table_exists(conn, table: str) -> bool:
    result = conn.execute(sa.text(
        "SELECT EXISTS (SELECT 1 FROM information_schema.tables "
        "WHERE table_name = :table)"
    ), {"table": table})
    return result.scalar()


def _index_exists(conn, index_name: str) -> bool:
    result = conn.execute(sa.text(
        "SELECT EXISTS (SELECT 1 FROM pg_indexes WHERE indexname = :idx)"
    ), {"idx": index_name})
    return result.scalar()


def _fk_exists(conn, fk_name: str) -> bool:
    result = conn.execute(sa.text(
        "SELECT EXISTS (SELECT 1 FROM information_schema.table_constraints "
        "WHERE constraint_name = :fk AND constraint_type = 'FOREIGN KEY')"
    ), {"fk": fk_name})
    return result.scalar()


def upgrade() -> None:
    conn = op.get_bind()

    # ── Suppliers: requires_pre_booking flag ──────────────────────────────
    if not _col_exists(conn, "suppliers", "requires_pre_booking"):
        op.add_column("suppliers", sa.Column(
            "requires_pre_booking", sa.Boolean(), nullable=False, server_default="false",
        ))

    # ── Bookings: pre-booking extensions ─────────────────────────────────
    booking_columns = {
        "is_pre_booking": sa.Column("is_pre_booking", sa.Boolean(), nullable=False, server_default="false"),
        "requested_by_id": sa.Column("requested_by_id", UUID(as_uuid=True), nullable=True),
        "assigned_to_id": sa.Column("assigned_to_id", UUID(as_uuid=True), nullable=True),
        "email_sent_at": sa.Column("email_sent_at", sa.DateTime(timezone=True), nullable=True),
        "email_sent_to": sa.Column("email_sent_to", sa.String(255), nullable=True),
        "supplier_response_note": sa.Column("supplier_response_note", sa.Text(), nullable=True),
        "formula_id": sa.Column("formula_id", sa.BigInteger(), nullable=True),
        "pax_count": sa.Column("pax_count", sa.Integer(), nullable=True),
        "room_config": sa.Column("room_config", JSONB(), nullable=True),
        "guest_names": sa.Column("guest_names", sa.Text(), nullable=True),
    }

    for col_name, col_def in booking_columns.items():
        if not _col_exists(conn, "bookings", col_name):
            op.add_column("bookings", col_def)

    # Foreign keys for bookings
    fk_defs = [
        ("fk_bookings_requested_by", "bookings", "users", ["requested_by_id"], ["id"]),
        ("fk_bookings_assigned_to", "bookings", "users", ["assigned_to_id"], ["id"]),
        ("fk_bookings_formula", "bookings", "formulas", ["formula_id"], ["id"]),
    ]
    for fk_name, src_table, ref_table, src_cols, ref_cols in fk_defs:
        if not _fk_exists(conn, fk_name):
            op.create_foreign_key(fk_name, src_table, ref_table, src_cols, ref_cols, ondelete="SET NULL")

    # Index for pre-booking queries
    if not _index_exists(conn, "idx_bookings_pre_booking"):
        op.create_index(
            "idx_bookings_pre_booking",
            "bookings",
            ["tenant_id", "is_pre_booking", "status"],
        )

    # ── Notifications table ──────────────────────────────────────────────
    if not _table_exists(conn, "notifications"):
        op.create_table(
            "notifications",
            sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
            sa.Column("tenant_id", UUID(as_uuid=True),
                      sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
            sa.Column("user_id", UUID(as_uuid=True),
                      sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("type", sa.String(50), nullable=False),
            sa.Column("title", sa.String(255), nullable=False),
            sa.Column("message", sa.Text(), nullable=True),
            sa.Column("link", sa.String(500), nullable=True),
            sa.Column("is_read", sa.Boolean(), nullable=False, server_default="false"),
            sa.Column("metadata_json", JSONB(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True),
                      server_default=sa.func.now(), nullable=False),
        )
    else:
        # Ensure required columns exist on existing notifications table
        for col_name, col_def in [
            ("metadata_json", sa.Column("metadata_json", JSONB(), nullable=True)),
            ("link", sa.Column("link", sa.String(500), nullable=True)),
            ("tenant_id", sa.Column("tenant_id", UUID(as_uuid=True), nullable=True)),
        ]:
            if not _col_exists(conn, "notifications", col_name):
                op.add_column("notifications", col_def)

    # Index on notifications
    if not _index_exists(conn, "idx_notifications_user_unread"):
        op.create_index(
            "idx_notifications_user_unread",
            "notifications",
            ["tenant_id", "user_id", "is_read"],
        )


def downgrade() -> None:
    conn = op.get_bind()

    # Notifications index
    if _index_exists(conn, "idx_notifications_user_unread"):
        op.drop_index("idx_notifications_user_unread", table_name="notifications")
    # Don't drop notifications table — it may have been created externally

    # Bookings
    if _index_exists(conn, "idx_bookings_pre_booking"):
        op.drop_index("idx_bookings_pre_booking", table_name="bookings")

    for fk_name in ["fk_bookings_formula", "fk_bookings_assigned_to", "fk_bookings_requested_by"]:
        if _fk_exists(conn, fk_name):
            op.drop_constraint(fk_name, "bookings", type_="foreignkey")

    for col in ["guest_names", "room_config", "pax_count", "formula_id",
                "supplier_response_note", "email_sent_to", "email_sent_at",
                "assigned_to_id", "requested_by_id", "is_pre_booking"]:
        if _col_exists(conn, "bookings", col):
            op.drop_column("bookings", col)

    # Suppliers
    if _col_exists(conn, "suppliers", "requires_pre_booking"):
        op.drop_column("suppliers", "requires_pre_booking")
