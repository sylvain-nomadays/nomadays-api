"""Add pax_count and pax_names to invoices for insurance integration.

Tracks the number of insured persons per invoice (critical for Chapka API).
pax_names stores a JSON array of participant names when known.

Revision ID: 067_invoice_pax_count
Revises: 066_reform_efacture_2026
Create Date: 2026-02-12
"""
from alembic import op
import sqlalchemy as sa

revision = "067_invoice_pax_count"
down_revision = "066_reform_efacture_2026"


def upgrade() -> None:
    # Number of insured persons (for Chapka insurance API)
    op.add_column("invoices", sa.Column("pax_count", sa.Integer, nullable=True))
    # JSON array of participant names (when known)
    op.add_column("invoices", sa.Column("pax_names", sa.Text, nullable=True))


def downgrade() -> None:
    op.drop_column("invoices", "pax_names")
    op.drop_column("invoices", "pax_count")
