"""Add early_bird_discounts table.

Revision ID: 014_early_bird_discounts
Revises: 013_internal_notes
Create Date: 2025-02-07

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ARRAY


# revision identifiers, used by Alembic.
revision: str = '014_early_bird_discounts'
down_revision: Union[str, None] = '013_internal_notes'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'early_bird_discounts',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('accommodation_id', sa.Integer(), sa.ForeignKey('accommodations.id', ondelete='CASCADE'), nullable=False),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('days_in_advance', sa.Integer(), nullable=False),
        sa.Column('discount_percent', sa.Numeric(5, 2), nullable=False),
        sa.Column('discount_amount', sa.Numeric(12, 2), nullable=True),
        sa.Column('discount_currency', sa.String(3), nullable=True),
        sa.Column('valid_from', sa.Date(), nullable=True),
        sa.Column('valid_to', sa.Date(), nullable=True),
        sa.Column('season_ids', ARRAY(sa.Integer()), nullable=True),
        sa.Column('is_cumulative', sa.Boolean(), default=False),
        sa.Column('priority', sa.Integer(), default=1),
        sa.Column('is_active', sa.Boolean(), default=True),
    )

    # Create index for faster lookups
    op.create_index('ix_early_bird_discounts_accommodation_id', 'early_bird_discounts', ['accommodation_id'])


def downgrade() -> None:
    op.drop_index('ix_early_bird_discounts_accommodation_id')
    op.drop_table('early_bird_discounts')
