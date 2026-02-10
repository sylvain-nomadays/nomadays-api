"""Add billing entity fields to accommodations.

Revision ID: 022_accommodation_billing
Revises: 021_contract_ai_fields
Create Date: 2025-02-07

Adds billing_entity_name and billing_entity_note to accommodations table
for logistics to know which entity to contact for invoicing.
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "022_accommodation_billing"
down_revision = "021_contract_ai_fields"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add billing entity fields to accommodations
    op.add_column(
        'accommodations',
        sa.Column('billing_entity_name', sa.String(255), nullable=True)
    )
    op.add_column(
        'accommodations',
        sa.Column('billing_entity_note', sa.Text(), nullable=True)
    )


def downgrade() -> None:
    op.drop_column('accommodations', 'billing_entity_note')
    op.drop_column('accommodations', 'billing_entity_name')
