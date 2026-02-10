"""Move condition binding: condition_id on formulas, condition_option_id on items.

Before: Formula.condition_option_id → entire formula included/excluded
After:  Formula.condition_id → declares "this formula has a condition"
        Item.condition_option_id → "this item is for option X"
        Filtering happens per-item, not per-formula.

Also removes the deprecated items.condition_id column.

Revision ID: 045_conditions_item_level
Revises: 044_conditions_refactoring
"""
from alembic import op
import sqlalchemy as sa

revision = "045_conditions_item_level"
down_revision = "044_conditions_refactoring"
branch_labels = None
depends_on = None


def upgrade():
    # ── 1. Add condition_id to formulas (FK → conditions.id) ──────────
    op.add_column(
        "formulas",
        sa.Column("condition_id", sa.BigInteger(), nullable=True),
    )
    op.create_foreign_key(
        "fk_formulas_condition",
        "formulas",
        "conditions",
        ["condition_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("idx_formulas_condition_id", "formulas", ["condition_id"])

    # ── 2. Add condition_option_id to items (FK → condition_options.id) ─
    op.add_column(
        "items",
        sa.Column("condition_option_id", sa.BigInteger(), nullable=True),
    )
    op.create_foreign_key(
        "fk_items_condition_option",
        "items",
        "condition_options",
        ["condition_option_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("idx_items_condition_option_id", "items", ["condition_option_id"])

    # ── 3. Data migration ─────────────────────────────────────────────
    conn = op.get_bind()

    # 3a. Populate formulas.condition_id from condition_options via formulas.condition_option_id
    conn.execute(
        sa.text(
            "UPDATE formulas f "
            "SET condition_id = co.condition_id "
            "FROM condition_options co "
            "WHERE f.condition_option_id = co.id "
            "AND f.condition_option_id IS NOT NULL"
        )
    )

    # 3b. Propagate condition_option_id from formula to all its items
    conn.execute(
        sa.text(
            "UPDATE items i "
            "SET condition_option_id = f.condition_option_id "
            "FROM formulas f "
            "WHERE i.formula_id = f.id "
            "AND f.condition_option_id IS NOT NULL"
        )
    )

    # ── 4. Drop old formulas.condition_option_id ──────────────────────
    op.drop_index("idx_formulas_condition_option_id")
    op.drop_constraint("fk_formulas_condition_option", "formulas", type_="foreignkey")
    op.drop_column("formulas", "condition_option_id")

    # ── 5. Drop deprecated items.condition_id ─────────────────────────
    # First check if FK constraint exists (it may have a generated name)
    conn.execute(
        sa.text(
            "ALTER TABLE items DROP CONSTRAINT IF EXISTS items_condition_id_fkey"
        )
    )
    conn.execute(
        sa.text(
            "ALTER TABLE items DROP CONSTRAINT IF EXISTS fk_items_condition"
        )
    )
    op.drop_column("items", "condition_id")


def downgrade():
    conn = op.get_bind()

    # ── Restore items.condition_id (deprecated) ───────────────────────
    op.add_column(
        "items",
        sa.Column("condition_id", sa.BigInteger(), nullable=True),
    )

    # ── Restore formulas.condition_option_id ──────────────────────────
    op.add_column(
        "formulas",
        sa.Column("condition_option_id", sa.BigInteger(), nullable=True),
    )
    op.create_foreign_key(
        "fk_formulas_condition_option",
        "formulas",
        "condition_options",
        ["condition_option_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("idx_formulas_condition_option_id", "formulas", ["condition_option_id"])

    # Data rollback: pick first item's condition_option_id for each formula
    conn.execute(
        sa.text(
            "UPDATE formulas f "
            "SET condition_option_id = sub.condition_option_id "
            "FROM ("
            "  SELECT DISTINCT ON (formula_id) formula_id, condition_option_id "
            "  FROM items "
            "  WHERE condition_option_id IS NOT NULL "
            "  ORDER BY formula_id, sort_order"
            ") sub "
            "WHERE f.id = sub.formula_id"
        )
    )

    # Drop new columns
    op.drop_index("idx_items_condition_option_id")
    op.drop_constraint("fk_items_condition_option", "items", type_="foreignkey")
    op.drop_column("items", "condition_option_id")

    op.drop_index("idx_formulas_condition_id")
    op.drop_constraint("fk_formulas_condition", "formulas", type_="foreignkey")
    op.drop_column("formulas", "condition_id")
