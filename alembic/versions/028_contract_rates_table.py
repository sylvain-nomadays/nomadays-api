"""Update contract_rates table schema to match model.

Revision ID: 028_contract_rates_table
Revises: 027_contract_status_enum
Create Date: 2025-02-07

The contract_rates table exists with different column names.
This migration renames and adds columns to match the model.

Existing schema: name, unit_type, unit_cost, valid_from, valid_to, meta_json
Model expects: service_name, service_code, base_price, season_name, etc.
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "028_contract_rates_table"
down_revision = "027_contract_status_enum"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Check if table exists and update it
    conn = op.get_bind()
    inspector = sa.inspect(conn)

    if 'contract_rates' in inspector.get_table_names():
        existing_columns = [col['name'] for col in inspector.get_columns('contract_rates')]

        # Rename 'name' to 'service_name' if it exists
        if 'name' in existing_columns and 'service_name' not in existing_columns:
            op.alter_column('contract_rates', 'name', new_column_name='service_name')

        # Rename 'unit_cost' to 'base_price' if it exists
        if 'unit_cost' in existing_columns and 'base_price' not in existing_columns:
            op.alter_column('contract_rates', 'unit_cost', new_column_name='base_price')

        # Add missing columns
        if 'service_code' not in existing_columns:
            op.add_column('contract_rates', sa.Column('service_code', sa.String(100), nullable=True))

        if 'pax_category' not in existing_columns:
            op.add_column('contract_rates', sa.Column('pax_category', sa.String(50), nullable=True))

        if 'season_name' not in existing_columns:
            op.add_column('contract_rates', sa.Column('season_name', sa.String(100), nullable=True))

        if 'season_start_mmdd' not in existing_columns:
            op.add_column('contract_rates', sa.Column('season_start_mmdd', sa.String(5), nullable=True))

        if 'season_end_mmdd' not in existing_columns:
            op.add_column('contract_rates', sa.Column('season_end_mmdd', sa.String(5), nullable=True))

        if 'day_of_week_mask' not in existing_columns:
            op.add_column('contract_rates', sa.Column('day_of_week_mask', sa.Integer(), nullable=False, server_default='127'))

        if 'min_pax' not in existing_columns:
            op.add_column('contract_rates', sa.Column('min_pax', sa.Integer(), nullable=True))

        if 'max_pax' not in existing_columns:
            op.add_column('contract_rates', sa.Column('max_pax', sa.Integer(), nullable=True))

        # Drop old columns that are no longer needed
        if 'unit_type' in existing_columns:
            op.drop_column('contract_rates', 'unit_type')

        if 'valid_from' in existing_columns:
            op.drop_column('contract_rates', 'valid_from')

        if 'valid_to' in existing_columns:
            op.drop_column('contract_rates', 'valid_to')

        if 'meta_json' in existing_columns:
            op.drop_column('contract_rates', 'meta_json')
    else:
        # Create table if it doesn't exist (fresh install)
        from sqlalchemy.dialects.postgresql import UUID

        op.create_table(
            'contract_rates',
            sa.Column('id', sa.BigInteger(), nullable=False, autoincrement=True),
            sa.Column('tenant_id', UUID(as_uuid=True), nullable=False),
            sa.Column('contract_id', sa.BigInteger(), nullable=False),

            # Service identification
            sa.Column('service_name', sa.String(255), nullable=False),
            sa.Column('service_code', sa.String(100), nullable=True),
            sa.Column('pax_category', sa.String(50), nullable=True),

            # Pricing
            sa.Column('currency', sa.String(3), nullable=False, server_default='EUR'),
            sa.Column('base_price', sa.Numeric(12, 2), nullable=False),

            # Seasonal pricing
            sa.Column('season_name', sa.String(100), nullable=True),
            sa.Column('season_start_mmdd', sa.String(5), nullable=True),
            sa.Column('season_end_mmdd', sa.String(5), nullable=True),

            # Day of week restrictions
            sa.Column('day_of_week_mask', sa.Integer(), nullable=False, server_default='127'),

            # Pax restrictions
            sa.Column('min_pax', sa.Integer(), nullable=True),
            sa.Column('max_pax', sa.Integer(), nullable=True),

            # Timestamps
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),

            # Keys
            sa.PrimaryKeyConstraint('id'),
            sa.ForeignKeyConstraint(['contract_id'], ['contracts.id'], ondelete='CASCADE'),
            sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
        )

        # Create indexes
        op.create_index('ix_contract_rates_contract_id', 'contract_rates', ['contract_id'])
        op.create_index('ix_contract_rates_tenant_id', 'contract_rates', ['tenant_id'])


def downgrade() -> None:
    # This is a complex migration - just drop and recreate in original format
    # Note: This will lose data
    conn = op.get_bind()
    inspector = sa.inspect(conn)

    if 'contract_rates' in inspector.get_table_names():
        existing_columns = [col['name'] for col in inspector.get_columns('contract_rates')]

        # Rename back
        if 'service_name' in existing_columns:
            op.alter_column('contract_rates', 'service_name', new_column_name='name')

        if 'base_price' in existing_columns:
            op.alter_column('contract_rates', 'base_price', new_column_name='unit_cost')

        # Re-add dropped columns
        if 'unit_type' not in existing_columns:
            op.add_column('contract_rates', sa.Column('unit_type', sa.String(50), nullable=True))

        if 'valid_from' not in existing_columns:
            op.add_column('contract_rates', sa.Column('valid_from', sa.Date(), nullable=True))

        if 'valid_to' not in existing_columns:
            op.add_column('contract_rates', sa.Column('valid_to', sa.Date(), nullable=True))

        if 'meta_json' not in existing_columns:
            op.add_column('contract_rates', sa.Column('meta_json', sa.JSON(), nullable=True))

        # Drop new columns
        for col in ['service_code', 'pax_category', 'season_name', 'season_start_mmdd',
                    'season_end_mmdd', 'day_of_week_mask', 'min_pax', 'max_pax']:
            if col in existing_columns:
                op.drop_column('contract_rates', col)
