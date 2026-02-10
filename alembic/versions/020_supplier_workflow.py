"""Add contract_workflow_status and location_id to suppliers.

- contract_workflow_status: Track workflow state (needs_contract, contract_requested, dynamic_pricing)
- location_id: Optional link to Location entity for advanced filtering

Revision ID: 020_supplier_workflow
Revises: 019_supplier_vat
Create Date: 2025-02-07

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '020_supplier_workflow'
down_revision: Union[str, None] = '019_supplier_vat'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add contract_workflow_status column
    op.add_column('suppliers', sa.Column(
        'contract_workflow_status',
        sa.String(30),
        nullable=False,
        server_default='needs_contract'
    ))

    # Add location_id column (optional FK to locations table)
    op.add_column('suppliers', sa.Column(
        'location_id',
        sa.Integer(),
        sa.ForeignKey('locations.id', ondelete='SET NULL'),
        nullable=True
    ))

    # Create index on location_id for faster filtering
    op.create_index('ix_suppliers_location_id', 'suppliers', ['location_id'])

    # Create index on contract_workflow_status for filtering
    op.create_index('ix_suppliers_contract_workflow_status', 'suppliers', ['contract_workflow_status'])


def downgrade() -> None:
    # Drop indexes
    op.drop_index('ix_suppliers_contract_workflow_status', 'suppliers')
    op.drop_index('ix_suppliers_location_id', 'suppliers')

    # Drop columns
    op.drop_column('suppliers', 'location_id')
    op.drop_column('suppliers', 'contract_workflow_status')
