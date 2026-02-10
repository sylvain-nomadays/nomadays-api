"""Add website field to suppliers.

Revision ID: 018_supplier_website
Revises: 017_types_payment
Create Date: 2025-02-07

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '018_supplier_website'
down_revision: Union[str, None] = '017_types_payment'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add website column to suppliers
    op.add_column('suppliers', sa.Column('website', sa.String(500), nullable=True))


def downgrade() -> None:
    # Remove website column
    op.drop_column('suppliers', 'website')
