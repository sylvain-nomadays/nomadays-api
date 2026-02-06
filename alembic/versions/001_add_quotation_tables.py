"""Add new tables for quotation system

Revision ID: 001_quotation
Revises:
Create Date: 2026-02-06

This migration adds new tables for the quotation system WITHOUT
modifying or deleting existing tables (tenants, users, etc.)
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = '001_quotation'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create cost_natures table
    op.create_table('cost_natures',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('code', sa.String(length=50), nullable=False),
        sa.Column('label', sa.String(length=255), nullable=False),
        sa.Column('generates_booking', sa.Boolean(), server_default='false', nullable=False),
        sa.Column('generates_purchase_order', sa.Boolean(), server_default='false', nullable=False),
        sa.Column('generates_payroll', sa.Boolean(), server_default='false', nullable=False),
        sa.Column('generates_advance', sa.Boolean(), server_default='false', nullable=False),
        sa.Column('vat_recoverable_default', sa.Boolean(), server_default='false', nullable=False),
        sa.Column('accounting_code', sa.String(length=20), nullable=True),
        sa.Column('is_system', sa.Boolean(), server_default='false', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_cost_natures_tenant_id', 'cost_natures', ['tenant_id'])

    # Create suppliers table
    op.create_table('suppliers',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('type', sa.String(length=50), nullable=False),
        sa.Column('contact_name', sa.String(length=255), nullable=True),
        sa.Column('contact_email', sa.String(length=255), nullable=True),
        sa.Column('contact_phone', sa.String(length=100), nullable=True),
        sa.Column('country_code', sa.String(length=2), nullable=True),
        sa.Column('city', sa.String(length=255), nullable=True),
        sa.Column('address', sa.String(length=500), nullable=True),
        sa.Column('tax_id', sa.String(length=100), nullable=True),
        sa.Column('payment_terms', sa.String(length=255), nullable=True),
        sa.Column('default_currency', sa.String(length=3), server_default='EUR', nullable=True),
        sa.Column('is_active', sa.Boolean(), server_default='true', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_suppliers_tenant_id', 'suppliers', ['tenant_id'])
    op.create_index('ix_suppliers_name', 'suppliers', ['name'])

    # Create contracts table
    op.create_table('contracts',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('supplier_id', sa.BigInteger(), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('reference', sa.String(length=100), nullable=True),
        sa.Column('file_storage_key', sa.String(length=500), nullable=True),
        sa.Column('valid_from', sa.Date(), nullable=False),
        sa.Column('valid_to', sa.Date(), nullable=False),
        sa.Column('payment_terms_json', postgresql.JSON(), nullable=True),
        sa.Column('cancellation_terms_json', postgresql.JSON(), nullable=True),
        sa.Column('status', sa.String(length=50), server_default='draft', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['supplier_id'], ['suppliers.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_contracts_tenant_id', 'contracts', ['tenant_id'])
    op.create_index('ix_contracts_supplier_id', 'contracts', ['supplier_id'])

    # Create contract_rates table
    op.create_table('contract_rates',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('contract_id', sa.BigInteger(), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('unit_type', sa.String(length=50), nullable=False),
        sa.Column('unit_cost', sa.DECIMAL(precision=12, scale=2), nullable=False),
        sa.Column('currency', sa.String(length=3), server_default='EUR', nullable=False),
        sa.Column('valid_from', sa.Date(), nullable=True),
        sa.Column('valid_to', sa.Date(), nullable=True),
        sa.Column('meta_json', postgresql.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['contract_id'], ['contracts.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_contract_rates_tenant_id', 'contract_rates', ['tenant_id'])
    op.create_index('ix_contract_rates_contract_id', 'contract_rates', ['contract_id'])

    # Create rate_catalog table
    op.create_table('rate_catalog',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('supplier_id', sa.BigInteger(), nullable=True),
        sa.Column('contract_rate_id', sa.BigInteger(), nullable=True),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('unit_type', sa.String(length=50), nullable=False),
        sa.Column('base_cost', sa.DECIMAL(precision=12, scale=2), nullable=False),
        sa.Column('currency', sa.String(length=3), server_default='EUR', nullable=False),
        sa.Column('is_active', sa.Boolean(), server_default='true', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['supplier_id'], ['suppliers.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['contract_rate_id'], ['contract_rates.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_rate_catalog_tenant_id', 'rate_catalog', ['tenant_id'])
    op.create_index('ix_rate_catalog_name', 'rate_catalog', ['name'])

    # Create trips table
    op.create_table('trips',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('reference', sa.String(length=100), nullable=True),
        sa.Column('type', sa.String(length=50), server_default='template', nullable=False),
        sa.Column('template_id', sa.BigInteger(), nullable=True),
        sa.Column('client_name', sa.String(length=255), nullable=True),
        sa.Column('client_email', sa.String(length=255), nullable=True),
        sa.Column('start_date', sa.Date(), nullable=True),
        sa.Column('duration_days', sa.Integer(), server_default='1', nullable=False),
        sa.Column('destination_country', sa.String(length=2), nullable=True),
        sa.Column('default_currency', sa.String(length=3), server_default='EUR', nullable=False),
        sa.Column('margin_pct', sa.DECIMAL(precision=5, scale=2), server_default='30.00', nullable=False),
        sa.Column('margin_type', sa.String(length=20), server_default='margin', nullable=False),
        sa.Column('vat_pct', sa.DECIMAL(precision=5, scale=2), server_default='0.00', nullable=False),
        sa.Column('status', sa.String(length=50), server_default='draft', nullable=False),
        sa.Column('version', sa.Integer(), server_default='1', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['template_id'], ['trips.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_trips_tenant_id', 'trips', ['tenant_id'])
    op.create_index('ix_trips_name', 'trips', ['name'])

    # Create trip_days table
    op.create_table('trip_days',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('trip_id', sa.BigInteger(), nullable=False),
        sa.Column('day_number', sa.Integer(), nullable=False),
        sa.Column('title', sa.String(length=255), nullable=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('location_from', sa.String(length=255), nullable=True),
        sa.Column('location_to', sa.String(length=255), nullable=True),
        sa.Column('sort_order', sa.Integer(), server_default='0', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['trip_id'], ['trips.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_trip_days_tenant_id', 'trip_days', ['tenant_id'])
    op.create_index('ix_trip_days_trip_id', 'trip_days', ['trip_id'])

    # Create trip_pax_configs table
    op.create_table('trip_pax_configs',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('trip_id', sa.BigInteger(), nullable=False),
        sa.Column('label', sa.String(length=100), nullable=False),
        sa.Column('total_pax', sa.Integer(), nullable=False),
        sa.Column('args_json', postgresql.JSON(), nullable=True),
        sa.Column('margin_override_pct', sa.DECIMAL(precision=5, scale=2), nullable=True),
        sa.Column('total_cost', sa.DECIMAL(precision=12, scale=2), nullable=True),
        sa.Column('total_price', sa.DECIMAL(precision=12, scale=2), nullable=True),
        sa.Column('total_profit', sa.DECIMAL(precision=12, scale=2), nullable=True),
        sa.Column('cost_per_person', sa.DECIMAL(precision=12, scale=2), nullable=True),
        sa.Column('price_per_person', sa.DECIMAL(precision=12, scale=2), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['trip_id'], ['trips.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_trip_pax_configs_tenant_id', 'trip_pax_configs', ['tenant_id'])
    op.create_index('ix_trip_pax_configs_trip_id', 'trip_pax_configs', ['trip_id'])

    # Create formulas table
    op.create_table('formulas',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('trip_day_id', sa.BigInteger(), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('description_html', sa.Text(), nullable=True),
        sa.Column('service_day_start', sa.Integer(), nullable=True),
        sa.Column('service_day_end', sa.Integer(), nullable=True),
        sa.Column('sort_order', sa.Integer(), server_default='0', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['trip_day_id'], ['trip_days.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_formulas_tenant_id', 'formulas', ['tenant_id'])
    op.create_index('ix_formulas_trip_day_id', 'formulas', ['trip_day_id'])

    # Create items table
    op.create_table('items',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('formula_id', sa.BigInteger(), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('cost_nature_id', sa.BigInteger(), nullable=True),
        sa.Column('supplier_id', sa.BigInteger(), nullable=True),
        sa.Column('rate_catalog_id', sa.BigInteger(), nullable=True),
        sa.Column('contract_rate_id', sa.BigInteger(), nullable=True),
        sa.Column('currency', sa.String(length=3), server_default='EUR', nullable=False),
        sa.Column('unit_cost', sa.DECIMAL(precision=12, scale=2), server_default='0', nullable=False),
        sa.Column('pricing_method', sa.String(length=50), server_default='quotation', nullable=False),
        sa.Column('pricing_value', sa.DECIMAL(precision=12, scale=2), nullable=True),
        sa.Column('ratio_categories', sa.String(length=100), server_default='adult', nullable=False),
        sa.Column('ratio_per', sa.Integer(), server_default='1', nullable=False),
        sa.Column('ratio_type', sa.String(length=20), server_default='ratio', nullable=False),
        sa.Column('times_type', sa.String(length=20), server_default='fixed', nullable=False),
        sa.Column('times_value', sa.Integer(), server_default='1', nullable=False),
        sa.Column('sort_order', sa.Integer(), server_default='0', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['formula_id'], ['formulas.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['cost_nature_id'], ['cost_natures.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['supplier_id'], ['suppliers.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['rate_catalog_id'], ['rate_catalog.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['contract_rate_id'], ['contract_rates.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_items_tenant_id', 'items', ['tenant_id'])
    op.create_index('ix_items_formula_id', 'items', ['formula_id'])

    # Create item_seasons table
    op.create_table('item_seasons',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('item_id', sa.BigInteger(), nullable=False),
        sa.Column('season_name', sa.String(length=100), nullable=False),
        sa.Column('valid_from', sa.Date(), nullable=True),
        sa.Column('valid_to', sa.Date(), nullable=True),
        sa.Column('cost_multiplier', sa.DECIMAL(precision=5, scale=2), nullable=True),
        sa.Column('cost_override', sa.DECIMAL(precision=12, scale=2), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['item_id'], ['items.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_item_seasons_tenant_id', 'item_seasons', ['tenant_id'])
    op.create_index('ix_item_seasons_item_id', 'item_seasons', ['item_id'])

    # Create bookings table
    op.create_table('bookings',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('trip_id', sa.BigInteger(), nullable=False),
        sa.Column('item_id', sa.BigInteger(), nullable=True),
        sa.Column('supplier_id', sa.BigInteger(), nullable=True),
        sa.Column('status', sa.String(length=50), server_default='pending', nullable=False),
        sa.Column('service_date', sa.Date(), nullable=True),
        sa.Column('quantity', sa.Integer(), server_default='1', nullable=False),
        sa.Column('unit_cost', sa.DECIMAL(precision=12, scale=2), nullable=True),
        sa.Column('total_cost', sa.DECIMAL(precision=12, scale=2), nullable=True),
        sa.Column('currency', sa.String(length=3), server_default='EUR', nullable=False),
        sa.Column('confirmation_ref', sa.String(length=255), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['trip_id'], ['trips.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['item_id'], ['items.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['supplier_id'], ['suppliers.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_bookings_tenant_id', 'bookings', ['tenant_id'])
    op.create_index('ix_bookings_trip_id', 'bookings', ['trip_id'])

    # Create ai_alerts table
    op.create_table('ai_alerts',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('trip_id', sa.BigInteger(), nullable=True),
        sa.Column('item_id', sa.BigInteger(), nullable=True),
        sa.Column('alert_type', sa.String(length=50), nullable=False),
        sa.Column('severity', sa.String(length=20), server_default='info', nullable=False),
        sa.Column('message', sa.Text(), nullable=False),
        sa.Column('expected_value', sa.DECIMAL(precision=12, scale=2), nullable=True),
        sa.Column('actual_value', sa.DECIMAL(precision=12, scale=2), nullable=True),
        sa.Column('deviation_pct', sa.DECIMAL(precision=5, scale=2), nullable=True),
        sa.Column('acknowledged', sa.Boolean(), server_default='false', nullable=False),
        sa.Column('acknowledged_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['trip_id'], ['trips.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['item_id'], ['items.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_ai_alerts_tenant_id', 'ai_alerts', ['tenant_id'])
    op.create_index('ix_ai_alerts_trip_id', 'ai_alerts', ['trip_id'])

    # Create audit_log table
    op.create_table('audit_log',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('entity_type', sa.String(length=50), nullable=False),
        sa.Column('entity_id', sa.BigInteger(), nullable=False),
        sa.Column('action', sa.String(length=50), nullable=False),
        sa.Column('old_values_json', postgresql.JSON(), nullable=True),
        sa.Column('new_values_json', postgresql.JSON(), nullable=True),
        sa.Column('context', sa.String(length=255), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_audit_log_tenant_id', 'audit_log', ['tenant_id'])


def downgrade() -> None:
    op.drop_table('audit_log')
    op.drop_table('ai_alerts')
    op.drop_table('bookings')
    op.drop_table('item_seasons')
    op.drop_table('items')
    op.drop_table('formulas')
    op.drop_table('trip_pax_configs')
    op.drop_table('trip_days')
    op.drop_table('trips')
    op.drop_table('rate_catalog')
    op.drop_table('contract_rates')
    op.drop_table('contracts')
    op.drop_table('suppliers')
    op.drop_table('cost_natures')
