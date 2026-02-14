"""Add payment reminder fields to invoices

Revision ID: 072_invoice_reminders
Revises: 071_cgv_acceptance
"""

from alembic import op
import sqlalchemy as sa

revision = "072_invoice_reminders"
down_revision = "071_cgv_acceptance"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Reminder enabled toggle (seller can disable)
    op.add_column(
        "invoices",
        sa.Column("reminder_enabled", sa.Boolean(), server_default="true", nullable=False),
    )
    # Computed reminder date (due_date - 7 days)
    op.add_column(
        "invoices",
        sa.Column("reminder_date", sa.Date(), nullable=True),
    )
    # Timestamp when reminder was actually sent (prevents duplicates)
    op.add_column(
        "invoices",
        sa.Column("reminder_sent_at", sa.DateTime(timezone=True), nullable=True),
    )
    # Partial index for the daily scheduler query
    op.create_index(
        "idx_invoices_reminder_pending",
        "invoices",
        ["tenant_id", "reminder_date"],
        postgresql_where=sa.text(
            "type = 'FA' AND status IN ('draft', 'sent') "
            "AND reminder_enabled = true AND reminder_sent_at IS NULL"
        ),
    )


def downgrade() -> None:
    op.drop_index("idx_invoices_reminder_pending", table_name="invoices")
    op.drop_column("invoices", "reminder_sent_at")
    op.drop_column("invoices", "reminder_date")
    op.drop_column("invoices", "reminder_enabled")
