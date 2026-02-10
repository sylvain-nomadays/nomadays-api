"""Add AI extraction and validation fields to contracts.

- ai_extracted_at: When AI extracted data from PDF
- human_validated_at: When user validated the extraction
- validated_by_id: Who validated (UUID to match users.id)
- previous_contract_id: For contract renewal chain

Revision ID: 021_contract_ai_fields
Revises: 020_supplier_workflow
Create Date: 2025-02-07

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


# revision identifiers, used by Alembic.
revision: str = '021_contract_ai_fields'
down_revision: Union[str, None] = '020_supplier_workflow'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add AI extraction timestamp
    op.add_column('contracts', sa.Column(
        'ai_extracted_at',
        sa.DateTime(timezone=True),
        nullable=True
    ))

    # Add human validation timestamp
    op.add_column('contracts', sa.Column(
        'human_validated_at',
        sa.DateTime(timezone=True),
        nullable=True
    ))

    # Add validated_by user reference (UUID to match users.id)
    op.add_column('contracts', sa.Column(
        'validated_by_id',
        UUID(as_uuid=True),
        nullable=True
    ))
    op.create_foreign_key(
        'fk_contracts_validated_by_id',
        'contracts',
        'users',
        ['validated_by_id'],
        ['id'],
        ondelete='SET NULL'
    )

    # Add previous contract reference for renewal chain
    op.add_column('contracts', sa.Column(
        'previous_contract_id',
        sa.BigInteger(),
        nullable=True
    ))
    op.create_foreign_key(
        'fk_contracts_previous_contract_id',
        'contracts',
        'contracts',
        ['previous_contract_id'],
        ['id'],
        ondelete='SET NULL'
    )


def downgrade() -> None:
    # Drop foreign keys
    op.drop_constraint('fk_contracts_previous_contract_id', 'contracts', type_='foreignkey')
    op.drop_constraint('fk_contracts_validated_by_id', 'contracts', type_='foreignkey')

    # Drop columns
    op.drop_column('contracts', 'previous_contract_id')
    op.drop_column('contracts', 'validated_by_id')
    op.drop_column('contracts', 'human_validated_at')
    op.drop_column('contracts', 'ai_extracted_at')
