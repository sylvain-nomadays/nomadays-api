"""Trip enhancements - dossiers, themes, TVA, commissions

Revision ID: 003_trip_enhancements
Revises: 38da96d5dbad
Create Date: 2026-02-06

Adds:
- dossiers table (client travel inquiries)
- travel_themes table (configurable themes per tenant)
- trip_themes junction table
- country_vat_rates table
- New columns on trips table (commission, TVA, characteristics)
- New columns on items table (TVA handling)
"""
from typing import Sequence, Union
from decimal import Decimal

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, ARRAY, ENUM as PG_ENUM


# revision identifiers, used by Alembic.
revision: str = '003_trip_enhancements'
down_revision: Union[str, None] = '38da96d5dbad'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Create ENUM types using IF NOT EXISTS (PostgreSQL 9.1+)
    op.execute("DROP TYPE IF EXISTS dossier_status_enum CASCADE")
    op.execute("DROP TYPE IF EXISTS vat_calculation_mode_enum CASCADE")
    op.execute("DROP TYPE IF EXISTS exchange_rate_mode_enum CASCADE")

    op.execute("CREATE TYPE dossier_status_enum AS ENUM ('lead', 'quote_in_progress', 'quote_sent', 'negotiation', 'confirmed', 'deposit_paid', 'fully_paid', 'in_trip', 'completed', 'lost', 'cancelled', 'archived')")
    op.execute("CREATE TYPE vat_calculation_mode_enum AS ENUM ('on_margin', 'on_selling_price')")
    op.execute("CREATE TYPE exchange_rate_mode_enum AS ENUM ('manual', 'kantox')")

    # Define ENUM types for use in columns
    dossier_status = PG_ENUM('lead', 'quote_in_progress', 'quote_sent', 'negotiation', 'confirmed', 'deposit_paid', 'fully_paid', 'in_trip', 'completed', 'lost', 'cancelled', 'archived', name='dossier_status_enum', create_type=False)
    vat_mode = PG_ENUM('on_margin', 'on_selling_price', name='vat_calculation_mode_enum', create_type=False)
    exchange_mode = PG_ENUM('manual', 'kantox', name='exchange_rate_mode_enum', create_type=False)

    # 2. Create dossiers table
    op.create_table(
        'dossiers',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('tenant_id', UUID(as_uuid=True), sa.ForeignKey('tenants.id', ondelete='CASCADE'), nullable=False),
        sa.Column('reference', sa.String(50), unique=True, nullable=False),
        sa.Column('status', dossier_status, server_default='lead', nullable=False),
        # Client info
        sa.Column('client_name', sa.String(255), nullable=True),
        sa.Column('client_email', sa.String(255), nullable=True),
        sa.Column('client_phone', sa.String(50), nullable=True),
        sa.Column('client_company', sa.String(255), nullable=True),
        sa.Column('client_address', sa.Text, nullable=True),
        # Travel dates
        sa.Column('departure_date_from', sa.Date, nullable=True),
        sa.Column('departure_date_to', sa.Date, nullable=True),
        # Budget
        sa.Column('budget_min', sa.DECIMAL(12, 2), nullable=True),
        sa.Column('budget_max', sa.DECIMAL(12, 2), nullable=True),
        sa.Column('budget_currency', sa.String(3), server_default='EUR'),
        # Pax
        sa.Column('pax_adults', sa.Integer, server_default='2'),
        sa.Column('pax_children', sa.Integer, server_default='0'),
        sa.Column('pax_infants', sa.Integer, server_default='0'),
        # Destination
        sa.Column('destination_countries', ARRAY(sa.String(2)), nullable=True),
        # Marketing
        sa.Column('marketing_source', sa.String(100), nullable=True),
        sa.Column('marketing_campaign', sa.String(255), nullable=True),
        # Notes
        sa.Column('internal_notes', sa.Text, nullable=True),
        sa.Column('lost_reason', sa.String(100), nullable=True),
        sa.Column('lost_comment', sa.Text, nullable=True),
        # Priority
        sa.Column('is_hot', sa.Boolean, server_default='false'),
        sa.Column('priority', sa.Integer, server_default='0'),
        # Ownership
        sa.Column('created_by_id', UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('assigned_to_id', UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('last_activity_at', sa.DateTime, nullable=True),
        # Timestamps
        sa.Column('created_at', sa.DateTime, server_default=sa.text('NOW()'), nullable=False),
        sa.Column('updated_at', sa.DateTime, server_default=sa.text('NOW()'), nullable=False),
    )
    op.create_index('ix_dossiers_tenant_id', 'dossiers', ['tenant_id'])
    op.create_index('ix_dossiers_status', 'dossiers', ['status'])

    # 3. Create travel_themes table
    op.create_table(
        'travel_themes',
        sa.Column('id', sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column('tenant_id', UUID(as_uuid=True), sa.ForeignKey('tenants.id', ondelete='CASCADE'), nullable=False),
        sa.Column('code', sa.String(50), nullable=False),
        sa.Column('label', sa.String(255), nullable=False),
        sa.Column('label_en', sa.String(255), nullable=True),
        sa.Column('icon', sa.String(50), nullable=True),
        sa.Column('color', sa.String(7), nullable=True),
        sa.Column('description', sa.String(500), nullable=True),
        sa.Column('is_active', sa.Boolean, server_default='true'),
        sa.Column('sort_order', sa.Integer, server_default='0'),
        sa.Column('created_at', sa.DateTime, server_default=sa.text('NOW()'), nullable=False),
        sa.Column('updated_at', sa.DateTime, server_default=sa.text('NOW()'), nullable=False),
    )
    op.create_index('ix_travel_themes_tenant_id', 'travel_themes', ['tenant_id'])

    # 4. Create trip_themes junction table
    op.create_table(
        'trip_themes',
        sa.Column('trip_id', sa.BigInteger, sa.ForeignKey('trips.id', ondelete='CASCADE'), primary_key=True),
        sa.Column('theme_id', sa.BigInteger, sa.ForeignKey('travel_themes.id', ondelete='CASCADE'), primary_key=True),
    )

    # 5. Create country_vat_rates table
    op.create_table(
        'country_vat_rates',
        sa.Column('id', sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column('tenant_id', UUID(as_uuid=True), sa.ForeignKey('tenants.id', ondelete='CASCADE'), nullable=False),
        sa.Column('country_code', sa.String(2), nullable=False),
        sa.Column('country_name', sa.String(100), nullable=True),
        sa.Column('vat_rate_standard', sa.DECIMAL(5, 2), server_default='0.00', nullable=False),
        sa.Column('vat_rate_hotel', sa.DECIMAL(5, 2), nullable=True),
        sa.Column('vat_rate_restaurant', sa.DECIMAL(5, 2), nullable=True),
        sa.Column('vat_rate_transport', sa.DECIMAL(5, 2), nullable=True),
        sa.Column('vat_rate_activity', sa.DECIMAL(5, 2), nullable=True),
        sa.Column('is_active', sa.Boolean, server_default='true'),
        sa.Column('created_at', sa.DateTime, server_default=sa.text('NOW()'), nullable=False),
        sa.Column('updated_at', sa.DateTime, server_default=sa.text('NOW()'), nullable=False),
        sa.UniqueConstraint('tenant_id', 'country_code', name='uq_country_vat_tenant_country'),
    )
    op.create_index('ix_country_vat_rates_tenant_id', 'country_vat_rates', ['tenant_id'])
    op.create_index('ix_country_vat_rates_country_code', 'country_vat_rates', ['country_code'])

    # 6. Add columns to trips table
    op.add_column('trips', sa.Column('dossier_id', UUID(as_uuid=True), sa.ForeignKey('dossiers.id', ondelete='SET NULL'), nullable=True))
    op.add_column('trips', sa.Column('end_date', sa.Date, nullable=True))
    op.add_column('trips', sa.Column('destination_countries', ARRAY(sa.String(2)), nullable=True))
    op.add_column('trips', sa.Column('comfort_level', sa.Integer, nullable=True))
    op.add_column('trips', sa.Column('difficulty_level', sa.Integer, nullable=True))
    # Commission structure
    op.add_column('trips', sa.Column('primary_commission_pct', sa.DECIMAL(5, 2), server_default='11.50', nullable=True))
    op.add_column('trips', sa.Column('primary_commission_label', sa.String(100), server_default='Nomadays', nullable=True))
    op.add_column('trips', sa.Column('secondary_commission_pct', sa.DECIMAL(5, 2), nullable=True))
    op.add_column('trips', sa.Column('secondary_commission_label', sa.String(100), nullable=True))
    # TVA mode
    vat_mode = PG_ENUM('on_margin', 'on_selling_price', name='vat_calculation_mode_enum', create_type=False)
    op.add_column('trips', sa.Column('vat_calculation_mode', vat_mode, server_default='on_margin', nullable=True))
    # Exchange rate mode
    exchange_mode = PG_ENUM('manual', 'kantox', name='exchange_rate_mode_enum', create_type=False)
    op.add_column('trips', sa.Column('exchange_rate_mode', exchange_mode, server_default='manual', nullable=True))

    # Create indexes
    op.create_index('ix_trips_dossier_id', 'trips', ['dossier_id'])

    # 7. Add columns to items table for TVA handling
    op.add_column('items', sa.Column('price_includes_vat', sa.Boolean, server_default='false', nullable=True))
    op.add_column('items', sa.Column('vat_rate', sa.DECIMAL(5, 2), nullable=True))
    op.add_column('items', sa.Column('vat_recoverable_amount', sa.DECIMAL(12, 2), nullable=True))

    # 8. Migrate existing data: copy destination_country to destination_countries array
    op.execute("""
        UPDATE trips
        SET destination_countries = ARRAY[destination_country]
        WHERE destination_country IS NOT NULL
        AND destination_countries IS NULL
    """)

    # 9. Copy operator_commission_pct to primary_commission_pct where applicable
    op.execute("""
        UPDATE trips
        SET primary_commission_pct = operator_commission_pct
        WHERE operator_commission_pct > 0
        AND primary_commission_pct IS NULL
    """)


def downgrade() -> None:
    # Remove columns from items
    op.drop_column('items', 'vat_recoverable_amount')
    op.drop_column('items', 'vat_rate')
    op.drop_column('items', 'price_includes_vat')

    # Remove columns from trips
    op.drop_index('ix_trips_dossier_id', table_name='trips')
    op.drop_column('trips', 'exchange_rate_mode')
    op.drop_column('trips', 'vat_calculation_mode')
    op.drop_column('trips', 'secondary_commission_label')
    op.drop_column('trips', 'secondary_commission_pct')
    op.drop_column('trips', 'primary_commission_label')
    op.drop_column('trips', 'primary_commission_pct')
    op.drop_column('trips', 'difficulty_level')
    op.drop_column('trips', 'comfort_level')
    op.drop_column('trips', 'destination_countries')
    op.drop_column('trips', 'end_date')
    op.drop_column('trips', 'dossier_id')

    # Drop tables
    op.drop_index('ix_country_vat_rates_country_code', table_name='country_vat_rates')
    op.drop_index('ix_country_vat_rates_tenant_id', table_name='country_vat_rates')
    op.drop_table('country_vat_rates')
    op.drop_table('trip_themes')
    op.drop_index('ix_travel_themes_tenant_id', table_name='travel_themes')
    op.drop_table('travel_themes')
    op.drop_index('ix_dossiers_status', table_name='dossiers')
    op.drop_index('ix_dossiers_tenant_id', table_name='dossiers')
    op.drop_table('dossiers')

    # Drop enum types
    op.execute("DROP TYPE IF EXISTS exchange_rate_mode_enum")
    op.execute("DROP TYPE IF EXISTS vat_calculation_mode_enum")
    op.execute("DROP TYPE IF EXISTS dossier_status_enum")
