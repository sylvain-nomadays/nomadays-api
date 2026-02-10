"""Add internal_notes to accommodations.

Revision ID: 013_internal_notes
Revises: 012_location_priority
Create Date: 2025-02-07

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '013_internal_notes'
down_revision: Union[str, None] = '012_location_priority'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add internal_notes column to accommodations table
    op.add_column('accommodations', sa.Column('internal_notes', sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column('accommodations', 'internal_notes')
