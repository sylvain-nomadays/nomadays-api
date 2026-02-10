"""Add is_vat_registered field to suppliers.

When true, the supplier issues invoices with VAT that can be deducted.

Revision ID: 019_supplier_vat
Revises: 018_supplier_website
Create Date: 2025-02-07

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '019_supplier_vat'
down_revision: Union[str, None] = '018_supplier_website'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add is_vat_registered column (default False = not VAT registered)
    op.add_column('suppliers', sa.Column(
        'is_vat_registered',
        sa.Boolean(),
        nullable=False,
        server_default='false'
    ))


def downgrade() -> None:
    op.drop_column('suppliers', 'is_vat_registered')
