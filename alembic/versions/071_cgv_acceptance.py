"""Add cgv_accepted_at to invoices

Revision ID: 071_cgv_acceptance
Revises: 070_promo_codes_and_billing
"""

from alembic import op
import sqlalchemy as sa

revision = "071_cgv_acceptance"
down_revision = "070_promo_codes_and_billing"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "invoices",
        sa.Column("cgv_accepted_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("invoices", "cgv_accepted_at")
