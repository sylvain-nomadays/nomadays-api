"""Add logistics_alternative field to bookings

Revision ID: 073_booking_logistic_alt
Revises: 072_invoice_reminders
"""

from alembic import op
import sqlalchemy as sa

revision = "073_booking_logistic_alt"
down_revision = "072_invoice_reminders"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "bookings",
        sa.Column("logistics_alternative", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("bookings", "logistics_alternative")
