"""Add applies_to field to conditions table.

Allows tagging conditions by scope: 'all' (default), 'accommodation', 'service'.
Used to filter which conditions appear in specific UI contexts
(e.g. only 'accommodation' conditions for hotel variant groups).

Revision ID: 046
Revises: 045
Create Date: 2025-01-01 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers
revision = "046_condition_applies_to"
down_revision = "045_conditions_item_level"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "conditions",
        sa.Column(
            "applies_to",
            sa.String(50),
            nullable=False,
            server_default="all",
        ),
    )
    # Add an index for filtering
    op.create_index("idx_conditions_applies_to", "conditions", ["tenant_id", "applies_to"])


def downgrade() -> None:
    op.drop_index("idx_conditions_applies_to", table_name="conditions")
    op.drop_column("conditions", "applies_to")
