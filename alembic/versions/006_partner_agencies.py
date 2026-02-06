"""Partner agencies for B2B white-label

Revision ID: 006_partner_agencies
Revises: 005_trip_locations
Create Date: 2026-02-06

Adds:
- partner_agencies table: B2B partner configuration with branding and templates
- partner_agency_id on dossiers: Link dossier to a partner agency
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB


# revision identifiers, used by Alembic.
revision: str = '006_partner_agencies'
down_revision: Union[str, None] = '005_trip_locations'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Create partner_agencies table
    op.create_table(
        'partner_agencies',
        sa.Column('id', sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column('tenant_id', UUID(as_uuid=True), sa.ForeignKey('tenants.id', ondelete='CASCADE'), nullable=False),

        # Identity
        sa.Column('name', sa.String(255), nullable=False),  # "Trace Directe"
        sa.Column('code', sa.String(50), nullable=True),  # Short code for reference
        sa.Column('is_active', sa.Boolean, server_default='true', nullable=False),

        # Contact info
        sa.Column('contact_name', sa.String(255), nullable=True),
        sa.Column('contact_email', sa.String(255), nullable=True),
        sa.Column('contact_phone', sa.String(50), nullable=True),
        sa.Column('website', sa.String(255), nullable=True),
        sa.Column('address', sa.Text, nullable=True),

        # Branding
        sa.Column('logo_url', sa.String(500), nullable=True),  # URL to logo image
        sa.Column('primary_color', sa.String(7), nullable=True),  # Hex color e.g. #1a5f4a
        sa.Column('secondary_color', sa.String(7), nullable=True),
        sa.Column('accent_color', sa.String(7), nullable=True),
        sa.Column('font_family', sa.String(100), nullable=True),  # e.g. "Montserrat"

        # PDF/Document configuration
        sa.Column('pdf_header_html', sa.Text, nullable=True),  # Custom header HTML
        sa.Column('pdf_footer_html', sa.Text, nullable=True),  # Custom footer HTML
        sa.Column('pdf_style', sa.String(50), server_default='modern'),  # modern, classic, minimal

        # Templates - stored as JSON for flexibility
        # Structure: { "content": "...", "variables": ["client_name", "destination"] }
        sa.Column('template_booking_conditions', JSONB, nullable=True),
        sa.Column('template_cancellation_policy', JSONB, nullable=True),
        sa.Column('template_general_info', JSONB, nullable=True),
        sa.Column('template_legal_mentions', JSONB, nullable=True),

        # Additional settings
        sa.Column('settings_json', JSONB, nullable=True),  # Extra configuration

        # Metadata
        sa.Column('notes', sa.Text, nullable=True),
        sa.Column('sort_order', sa.Integer, server_default='0', nullable=False),

        # Timestamps
        sa.Column('created_at', sa.DateTime, server_default=sa.text('NOW()'), nullable=False),
        sa.Column('updated_at', sa.DateTime, server_default=sa.text('NOW()'), nullable=False),
    )
    op.create_index('ix_partner_agencies_tenant_id', 'partner_agencies', ['tenant_id'])
    op.create_index('ix_partner_agencies_code', 'partner_agencies', ['code'])

    # 2. Add partner_agency_id to dossiers
    op.add_column('dossiers', sa.Column(
        'partner_agency_id',
        sa.BigInteger,
        sa.ForeignKey('partner_agencies.id', ondelete='SET NULL'),
        nullable=True
    ))
    op.create_index('ix_dossiers_partner_agency_id', 'dossiers', ['partner_agency_id'])

    # 3. Rename marketing_source to clarify it's for tracking, not partner
    # Keep marketing_source for analytics (Google Ads, Facebook, etc.)
    # partner_agency_id is for B2B partner relationship


def downgrade() -> None:
    # Remove partner_agency_id from dossiers
    op.drop_index('ix_dossiers_partner_agency_id', table_name='dossiers')
    op.drop_column('dossiers', 'partner_agency_id')

    # Drop partner_agencies table
    op.drop_index('ix_partner_agencies_code', table_name='partner_agencies')
    op.drop_index('ix_partner_agencies_tenant_id', table_name='partner_agencies')
    op.drop_table('partner_agencies')
