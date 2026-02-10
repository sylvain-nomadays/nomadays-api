"""Add block_type and parent_block_id to formulas for modular block system.

Revision ID: 036_formula_blocks
Revises: 035_trip_day_number_end
Create Date: 2026-02-08
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers
revision = '036_formula_blocks'
down_revision = '035_trip_day_number_end'
branch_labels = None
depends_on = None


def upgrade():
    # Block type: text (narrative only), activity (with formulas/items), accommodation (hotel)
    op.add_column('formulas', sa.Column(
        'block_type', sa.String(20), nullable=False, server_default='activity'
    ))
    # Self-referential FK for parent/child hierarchy
    op.add_column('formulas', sa.Column(
        'parent_block_id', sa.BigInteger(), nullable=True
    ))
    op.create_foreign_key(
        'fk_formulas_parent_block',
        'formulas', 'formulas',
        ['parent_block_id'], ['id'],
        ondelete='CASCADE'
    )
    op.create_index('idx_formulas_parent_block_id', 'formulas', ['parent_block_id'])
    op.create_index('idx_formulas_block_type', 'formulas', ['block_type'])


def downgrade():
    op.drop_index('idx_formulas_block_type', table_name='formulas')
    op.drop_index('idx_formulas_parent_block_id', table_name='formulas')
    op.drop_constraint('fk_formulas_parent_block', 'formulas', type_='foreignkey')
    op.drop_column('formulas', 'parent_block_id')
    op.drop_column('formulas', 'block_type')
