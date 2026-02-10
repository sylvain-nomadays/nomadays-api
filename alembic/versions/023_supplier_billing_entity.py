"""Add billing entity fields to suppliers.

Revision ID: 023_supplier_billing_entity
Revises: 022_accommodation_billing
Create Date: 2025-02-07

Adds billing_entity_name and billing_entity_note to suppliers table
for logistics to know which entity to contact for invoicing.
These fields were initially on accommodations but moved to supplier level.
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "023_supplier_billing_entity"
down_revision = "022_accommodation_billing"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add billing entity fields to suppliers
    op.add_column(
        'suppliers',
        sa.Column('billing_entity_name', sa.String(255), nullable=True)
    )
    op.add_column(
        'suppliers',
        sa.Column('billing_entity_note', sa.Text(), nullable=True)
    )


def downgrade() -> None:
    op.drop_column('suppliers', 'billing_entity_note')
    op.drop_column('suppliers', 'billing_entity_name')
