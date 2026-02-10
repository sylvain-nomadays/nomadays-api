"""Supplier types array and payment terms on accommodation.

Converts suppliers.type (single string) to suppliers.types (array of strings).
Creates payment_terms table.
Adds payment_terms_id to accommodations for override capability.
Adds default_payment_terms_id to suppliers.

Revision ID: 017_types_payment
Revises: 016_locations
Create Date: 2025-02-07

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID


# revision identifiers, used by Alembic.
revision: str = '017_types_payment'
down_revision: Union[str, None] = '016_locations'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Create payment_terms table FIRST (before adding FKs)
    op.create_table(
        'payment_terms',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('tenant_id', UUID(as_uuid=True), sa.ForeignKey('tenants.id'), nullable=False),
        sa.Column('supplier_id', sa.Integer(), sa.ForeignKey('suppliers.id', ondelete='CASCADE'), nullable=True),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('installments', JSONB(), nullable=False, server_default='[]'),
        sa.Column('is_default', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_payment_terms_supplier_id', 'payment_terms', ['supplier_id'])
    op.create_index('ix_payment_terms_tenant_id', 'payment_terms', ['tenant_id'])

    # 2. Add new 'types' column as ARRAY(String) on suppliers
    op.add_column('suppliers', sa.Column('types', ARRAY(sa.String(50)), nullable=True))

    # 3. Migrate existing 'type' data to 'types' array
    # Convert single type to array with that type
    op.execute("""
        UPDATE suppliers
        SET types = ARRAY[type]::varchar(50)[]
        WHERE type IS NOT NULL
    """)

    # 4. Set default for suppliers without type
    op.execute("""
        UPDATE suppliers
        SET types = ARRAY['accommodation']::varchar(50)[]
        WHERE types IS NULL
    """)

    # 5. Make 'types' NOT NULL and drop 'type'
    op.alter_column('suppliers', 'types', nullable=False)
    op.drop_column('suppliers', 'type')

    # 6. Add default_payment_terms_id to suppliers
    op.add_column('suppliers', sa.Column(
        'default_payment_terms_id',
        sa.Integer(),
        sa.ForeignKey('payment_terms.id', ondelete='SET NULL'),
        nullable=True
    ))

    # 7. Add payment_terms_id to accommodations (override)
    op.add_column('accommodations', sa.Column(
        'payment_terms_id',
        sa.Integer(),
        sa.ForeignKey('payment_terms.id', ondelete='SET NULL'),
        nullable=True
    ))


def downgrade() -> None:
    # 1. Remove payment_terms_id from accommodations
    op.drop_column('accommodations', 'payment_terms_id')

    # 2. Remove default_payment_terms_id from suppliers
    op.drop_column('suppliers', 'default_payment_terms_id')

    # 3. Add back 'type' column
    op.add_column('suppliers', sa.Column('type', sa.String(50), nullable=True))

    # 4. Migrate 'types' array back to single 'type' (take first element)
    op.execute("""
        UPDATE suppliers
        SET type = types[1]
        WHERE types IS NOT NULL AND array_length(types, 1) > 0
    """)

    # 5. Set default for suppliers without type
    op.execute("""
        UPDATE suppliers
        SET type = 'accommodation'
        WHERE type IS NULL
    """)

    # 6. Make 'type' NOT NULL and drop 'types'
    op.alter_column('suppliers', 'type', nullable=False)
    op.drop_column('suppliers', 'types')

    # 7. Drop payment_terms table LAST
    op.drop_index('ix_payment_terms_tenant_id', 'payment_terms')
    op.drop_index('ix_payment_terms_supplier_id', 'payment_terms')
    op.drop_table('payment_terms')
