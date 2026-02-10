"""Add payment_flow column to items table.

Separates the payment flow (how a cost is paid: booking, advance, purchase_order,
payroll, manual) from the cost nature category (what is being bought: HTL, TRS, ACT...).

Revision ID: 040_item_payment_flow
Revises: 039_trip_days_location_id
"""
from alembic import op
import sqlalchemy as sa

revision = "040_item_payment_flow"
down_revision = "039_trip_days_location_id"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "items",
        sa.Column("payment_flow", sa.String(20), nullable=True),
    )


def downgrade():
    op.drop_column("items", "payment_flow")
