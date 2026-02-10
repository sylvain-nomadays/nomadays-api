"""Add excluded_season_ids to early_bird_discounts.

Revision ID: 015_excluded_seasons
Revises: 014_early_bird_discounts
Create Date: 2025-02-07

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ARRAY


# revision identifiers, used by Alembic.
revision: str = '015_excluded_seasons'
down_revision: Union[str, None] = '014_early_bird_discounts'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'early_bird_discounts',
        sa.Column('excluded_season_ids', ARRAY(sa.Integer()), nullable=True)
    )


def downgrade() -> None:
    op.drop_column('early_bird_discounts', 'excluded_season_ids')
