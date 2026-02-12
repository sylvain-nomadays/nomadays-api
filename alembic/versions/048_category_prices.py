"""Add category_prices_json to items and item_price_tiers.

Allows defining absolute prices per pax category on an item.
E.g. {"adult": 2500, "teen": 1800, "child": 900, "guide": 0}

When NULL, behavior is unchanged (single unit_cost for all categories).
When set, overrides unit_cost per category. Takes priority over
category_adjustments_json (percentage-based) on price tiers.

Revision ID: 048
Revises: 047
Create Date: 2026-02-10 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers
revision = "048_category_prices"
down_revision = "047_pax_cats_price_tiers"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add category_prices_json to items table
    op.add_column(
        "items",
        sa.Column("category_prices_json", sa.JSON(), nullable=True),
    )

    # Add category_prices_json to item_price_tiers table
    op.add_column(
        "item_price_tiers",
        sa.Column("category_prices_json", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("item_price_tiers", "category_prices_json")
    op.drop_column("items", "category_prices_json")
