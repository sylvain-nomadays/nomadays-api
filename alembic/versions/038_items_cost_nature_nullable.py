"""Ensure items.cost_nature_id is nullable (align model with DB schema)

Revision ID: 038_items_cost_nature_nullable
Revises: 037_items_missing_columns

Note: The original migration 001 already created cost_nature_id as nullable=True.
This migration is a safety net in case the column was later altered to NOT NULL.
The SQLAlchemy model was also updated to match (Mapped[Optional[int]], nullable=True).
"""
from alembic import op
import sqlalchemy as sa

revision = "038_items_cost_nature_nullable"
down_revision = "037_items_missing_columns"
branch_labels = None
depends_on = None


def upgrade():
    # Ensure cost_nature_id is nullable (should already be, but safety net)
    op.alter_column(
        "items",
        "cost_nature_id",
        existing_type=sa.BigInteger(),
        nullable=True,
    )


def downgrade():
    # No-op: we don't want to break existing data by making it NOT NULL
    pass
