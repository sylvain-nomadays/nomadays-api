"""Add payment_url column to invoice_payment_links.

Stores the Monetico payment URL for online deposit/balance payment.

Revision ID: 069_payment_link_url
Revises: 068_invoice_share_token
Create Date: 2026-02-13
"""
from alembic import op
import sqlalchemy as sa

revision = "069_payment_link_url"
down_revision = "068_invoice_share_token"


def upgrade() -> None:
    op.add_column(
        "invoice_payment_links",
        sa.Column("payment_url", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("invoice_payment_links", "payment_url")
