"""Add share_token for public invoice link sharing.

Enables DMCs to share invoices via a secure, unguessable URL.
Clients can view the invoice and download as PDF without authentication.

Revision ID: 068_invoice_share_token
Revises: 067_invoice_pax_count
Create Date: 2026-02-13
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "068_invoice_share_token"
down_revision = "067_invoice_pax_count"


def upgrade() -> None:
    # Share token (UUID v4) for public access — unique and indexed for fast lookup
    op.add_column("invoices", sa.Column("share_token", UUID(as_uuid=True), nullable=True))
    # When the share link was created
    op.add_column("invoices", sa.Column("share_token_created_at", sa.DateTime(timezone=True), nullable=True))
    # When the client last viewed the invoice via the share link
    op.add_column("invoices", sa.Column("shared_link_viewed_at", sa.DateTime(timezone=True), nullable=True))

    # Unique constraint + index for O(1) token lookup in public endpoints
    op.create_unique_constraint("uq_invoices_share_token", "invoices", ["share_token"])
    op.create_index("idx_invoices_share_token", "invoices", ["share_token"], unique=True)


def downgrade() -> None:
    op.drop_index("idx_invoices_share_token", table_name="invoices")
    op.drop_constraint("uq_invoices_share_token", "invoices", type_="unique")
    op.drop_column("invoices", "shared_link_viewed_at")
    op.drop_column("invoices", "share_token_created_at")
    op.drop_column("invoices", "share_token")
