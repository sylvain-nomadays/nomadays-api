"""Trip locations, routes, and country templates

Revision ID: 005_trip_locations
Revises: 004_trip_presentation
Create Date: 2026-02-06

Adds:
- trip_locations table: Geographic waypoints with geocoding support
- trip_routes table: Routes between locations with distances/durations
- country_templates table: Default templates for inclusions, exclusions, etc.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB, ENUM as PG_ENUM


# revision identifiers, used by Alembic.
revision: str = '005_trip_locations'
down_revision: Union[str, None] = '004_trip_presentation'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Create ENUM types
    op.execute("DROP TYPE IF EXISTS location_type_enum CASCADE")
    op.execute("DROP TYPE IF EXISTS travel_mode_enum CASCADE")
    op.execute("DROP TYPE IF EXISTS template_type_enum CASCADE")

    op.execute("CREATE TYPE location_type_enum AS ENUM ('overnight', 'waypoint', 'poi', 'activity')")
    op.execute("CREATE TYPE travel_mode_enum AS ENUM ('driving', 'walking', 'transit', 'flight', 'boat')")
    op.execute("CREATE TYPE template_type_enum AS ENUM ('inclusions', 'exclusions', 'formalities', 'booking_conditions', 'cancellation_policy', 'general_info')")

    location_type = PG_ENUM('overnight', 'waypoint', 'poi', 'activity', name='location_type_enum', create_type=False)
    travel_mode = PG_ENUM('driving', 'walking', 'transit', 'flight', 'boat', name='travel_mode_enum', create_type=False)
    template_type = PG_ENUM('inclusions', 'exclusions', 'formalities', 'booking_conditions', 'cancellation_policy', 'general_info', name='template_type_enum', create_type=False)

    # 2. Create trip_locations table
    # Stores geographic points for each trip with geocoding data from Google Maps
    op.create_table(
        'trip_locations',
        sa.Column('id', sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column('trip_id', sa.BigInteger, sa.ForeignKey('trips.id', ondelete='CASCADE'), nullable=False),
        sa.Column('tenant_id', UUID(as_uuid=True), sa.ForeignKey('tenants.id', ondelete='CASCADE'), nullable=False),

        # Location info
        sa.Column('name', sa.String(255), nullable=False),  # "Chiang Mai", "Temple of Dawn"
        sa.Column('place_id', sa.String(100), nullable=True),  # Google Place ID for deduplication

        # Coordinates (from geocoding)
        sa.Column('lat', sa.DECIMAL(10, 7), nullable=True),
        sa.Column('lng', sa.DECIMAL(10, 7), nullable=True),

        # Additional info
        sa.Column('address', sa.Text, nullable=True),  # Formatted address from Google
        sa.Column('country_code', sa.String(2), nullable=True),  # ISO country code
        sa.Column('region', sa.String(100), nullable=True),  # Province/state

        # Trip context
        sa.Column('day_number', sa.Integer, nullable=True),  # Associated day (can be NULL for general POI)
        sa.Column('location_type', location_type, server_default='overnight', nullable=False),
        sa.Column('description', sa.Text, nullable=True),  # Optional description of this stop

        # Ordering
        sa.Column('sort_order', sa.Integer, server_default='0', nullable=False),

        # Timestamps
        sa.Column('created_at', sa.DateTime, server_default=sa.text('NOW()'), nullable=False),
        sa.Column('updated_at', sa.DateTime, server_default=sa.text('NOW()'), nullable=False),
    )
    op.create_index('ix_trip_locations_trip_id', 'trip_locations', ['trip_id'])
    op.create_index('ix_trip_locations_tenant_id', 'trip_locations', ['tenant_id'])
    op.create_index('ix_trip_locations_place_id', 'trip_locations', ['place_id'])

    # 3. Create trip_routes table
    # Stores routes between locations (distance, duration, polyline for map display)
    op.create_table(
        'trip_routes',
        sa.Column('id', sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column('trip_id', sa.BigInteger, sa.ForeignKey('trips.id', ondelete='CASCADE'), nullable=False),
        sa.Column('tenant_id', UUID(as_uuid=True), sa.ForeignKey('tenants.id', ondelete='CASCADE'), nullable=False),

        # Route endpoints
        sa.Column('from_location_id', sa.BigInteger, sa.ForeignKey('trip_locations.id', ondelete='CASCADE'), nullable=False),
        sa.Column('to_location_id', sa.BigInteger, sa.ForeignKey('trip_locations.id', ondelete='CASCADE'), nullable=False),

        # Route details
        sa.Column('distance_km', sa.DECIMAL(10, 2), nullable=True),  # Distance in kilometers
        sa.Column('duration_minutes', sa.Integer, nullable=True),  # Duration in minutes
        sa.Column('polyline', sa.Text, nullable=True),  # Encoded polyline from Google Directions
        sa.Column('travel_mode', travel_mode, server_default='driving', nullable=False),

        # Cache metadata
        sa.Column('calculated_at', sa.DateTime, server_default=sa.text('NOW()'), nullable=False),

        # Timestamps
        sa.Column('created_at', sa.DateTime, server_default=sa.text('NOW()'), nullable=False),
        sa.Column('updated_at', sa.DateTime, server_default=sa.text('NOW()'), nullable=False),

        # Unique constraint: one route per pair of locations and travel mode
        sa.UniqueConstraint('trip_id', 'from_location_id', 'to_location_id', 'travel_mode', name='uq_trip_route_locations'),
    )
    op.create_index('ix_trip_routes_trip_id', 'trip_routes', ['trip_id'])
    op.create_index('ix_trip_routes_tenant_id', 'trip_routes', ['tenant_id'])

    # 4. Create country_templates table
    # Stores default templates for inclusions, exclusions, formalities per country
    op.create_table(
        'country_templates',
        sa.Column('id', sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column('tenant_id', UUID(as_uuid=True), sa.ForeignKey('tenants.id', ondelete='CASCADE'), nullable=False),

        # Country (ISO 2-letter code) - NULL means global default
        sa.Column('country_code', sa.String(2), nullable=True),
        sa.Column('country_name', sa.String(100), nullable=True),

        # Template type
        sa.Column('template_type', template_type, nullable=False),

        # Content (JSONB for flexibility)
        # For inclusions/exclusions: [{ "text": "...", "default": true }]
        # For text templates: { "content": "...", "variables": ["destination", "duration"] }
        sa.Column('content', JSONB, nullable=False),

        # Metadata
        sa.Column('is_active', sa.Boolean, server_default='true', nullable=False),
        sa.Column('sort_order', sa.Integer, server_default='0', nullable=False),

        # Timestamps
        sa.Column('created_at', sa.DateTime, server_default=sa.text('NOW()'), nullable=False),
        sa.Column('updated_at', sa.DateTime, server_default=sa.text('NOW()'), nullable=False),

        # Unique constraint: one template per type per country per tenant
        sa.UniqueConstraint('tenant_id', 'country_code', 'template_type', name='uq_country_template_type'),
    )
    op.create_index('ix_country_templates_tenant_id', 'country_templates', ['tenant_id'])
    op.create_index('ix_country_templates_country_code', 'country_templates', ['country_code'])

    # 5. Seed default global templates for inclusions/exclusions
    op.execute("""
        INSERT INTO country_templates (tenant_id, country_code, template_type, content, is_active, sort_order)
        SELECT
            t.id,
            NULL,  -- Global (no specific country)
            'inclusions',
            '[
                {"text": "Hébergement selon le programme", "default": true},
                {"text": "Petits-déjeuners", "default": true},
                {"text": "Transferts privés", "default": true},
                {"text": "Guide francophone", "default": true},
                {"text": "Activités mentionnées au programme", "default": true},
                {"text": "Entrées sur les sites", "default": true}
            ]'::jsonb,
            true,
            0
        FROM tenants t
        ON CONFLICT DO NOTHING
    """)

    op.execute("""
        INSERT INTO country_templates (tenant_id, country_code, template_type, content, is_active, sort_order)
        SELECT
            t.id,
            NULL,  -- Global (no specific country)
            'exclusions',
            '[
                {"text": "Vols internationaux", "default": true},
                {"text": "Assurance voyage", "default": true},
                {"text": "Repas non mentionnés", "default": true},
                {"text": "Pourboires", "default": true},
                {"text": "Dépenses personnelles", "default": true},
                {"text": "Frais de visa", "default": false}
            ]'::jsonb,
            true,
            0
        FROM tenants t
        ON CONFLICT DO NOTHING
    """)


def downgrade() -> None:
    # Drop tables in reverse order
    op.drop_index('ix_country_templates_country_code', table_name='country_templates')
    op.drop_index('ix_country_templates_tenant_id', table_name='country_templates')
    op.drop_table('country_templates')

    op.drop_index('ix_trip_routes_tenant_id', table_name='trip_routes')
    op.drop_index('ix_trip_routes_trip_id', table_name='trip_routes')
    op.drop_table('trip_routes')

    op.drop_index('ix_trip_locations_place_id', table_name='trip_locations')
    op.drop_index('ix_trip_locations_tenant_id', table_name='trip_locations')
    op.drop_index('ix_trip_locations_trip_id', table_name='trip_locations')
    op.drop_table('trip_locations')

    # Drop enum types
    op.execute("DROP TYPE IF EXISTS template_type_enum")
    op.execute("DROP TYPE IF EXISTS travel_mode_enum")
    op.execute("DROP TYPE IF EXISTS location_type_enum")
