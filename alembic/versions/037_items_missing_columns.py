"""Add conditions table + missing columns to items table: condition_id, is_override, override_reason

Revision ID: 037_items_missing_columns
Revises: 036_formula_blocks
"""
from alembic import op
import sqlalchemy as sa

revision = "037_items_missing_columns"
down_revision = "036_formula_blocks"
branch_labels = None
depends_on = None


def upgrade():
    # 1. Create conditions table (referenced by items.condition_id)
    op.create_table(
        "conditions",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("trip_id", sa.BigInteger(), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.String(500), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["trip_id"], ["trips.id"], ondelete="CASCADE"),
    )
    op.create_index("idx_conditions_tenant_id", "conditions", ["tenant_id"])
    op.create_index("idx_conditions_trip_id", "conditions", ["trip_id"])

    # 2. Add condition_id to items with FK to conditions
    op.add_column(
        "items",
        sa.Column("condition_id", sa.BigInteger(), nullable=True),
    )
    op.create_foreign_key(
        "fk_items_condition",
        "items",
        "conditions",
        ["condition_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("idx_items_condition_id", "items", ["condition_id"])

    # 3. Add is_override flag
    op.add_column(
        "items",
        sa.Column("is_override", sa.Boolean(), nullable=False, server_default="false"),
    )

    # 4. Add override_reason
    op.add_column(
        "items",
        sa.Column("override_reason", sa.String(255), nullable=True),
    )


def downgrade():
    op.drop_column("items", "override_reason")
    op.drop_column("items", "is_override")
    op.drop_index("idx_items_condition_id")
    op.drop_constraint("fk_items_condition", "items", type_="foreignkey")
    op.drop_column("items", "condition_id")
    op.drop_index("idx_conditions_trip_id")
    op.drop_index("idx_conditions_tenant_id")
    op.drop_table("conditions")
