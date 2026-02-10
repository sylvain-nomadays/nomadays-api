"""Add location fields and internal_priority to accommodations and suppliers.

Revision ID: 012_location_priority
Revises: 011_accommodations
Create Date: 2025-02-07

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '012_location_priority'
down_revision: Union[str, None] = '011_accommodations'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add new columns to accommodations table
    op.add_column('accommodations', sa.Column('internal_priority', sa.Integer(), nullable=True))
    op.add_column('accommodations', sa.Column('city', sa.String(255), nullable=True))
    op.add_column('accommodations', sa.Column('country_code', sa.String(2), nullable=True))
    op.add_column('accommodations', sa.Column('google_place_id', sa.String(255), nullable=True))

    # Add new columns to suppliers table
    op.add_column('suppliers', sa.Column('lat', sa.Float(), nullable=True))
    op.add_column('suppliers', sa.Column('lng', sa.Float(), nullable=True))
    op.add_column('suppliers', sa.Column('google_place_id', sa.String(255), nullable=True))


def downgrade() -> None:
    # Remove columns from suppliers
    op.drop_column('suppliers', 'google_place_id')
    op.drop_column('suppliers', 'lng')
    op.drop_column('suppliers', 'lat')

    # Remove columns from accommodations
    op.drop_column('accommodations', 'google_place_id')
    op.drop_column('accommodations', 'country_code')
    op.drop_column('accommodations', 'city')
    op.drop_column('accommodations', 'internal_priority')
