"""Content CTA blocks table.

Revision ID: 033_content_cta_blocks
Revises: 032_content_articles
Create Date: 2025-02-08

CTA blocks for content pages:
- quote_request: Demande de devis
- related_circuit: Suggestion de circuit lié
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB


revision = '033_content_cta_blocks'
down_revision = '032_content_articles'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'content_cta_blocks',
        # Primary key
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('tenant_id', UUID(as_uuid=True), sa.ForeignKey('tenants.id', ondelete='CASCADE'), nullable=False, index=True),

        # CTA type
        sa.Column('cta_type', sa.String(50), nullable=False),  # quote_request, related_circuit

        # Content (multilingual JSONB)
        sa.Column('name', sa.String(255), nullable=False),  # Internal name
        sa.Column('title_json', JSONB, nullable=False),  # {"fr": "Votre voyage...", "en": "..."}
        sa.Column('description_json', JSONB, nullable=True),  # {"fr": "Avec SawaDiscovery...", "en": "..."}
        sa.Column('button_text_json', JSONB, nullable=False),  # {"fr": "Nous contacter", "en": "Contact us"}

        # Action
        sa.Column('button_action', sa.String(50), nullable=True),  # link, modal, form
        sa.Column('button_url', sa.String(500), nullable=True),  # For link action

        # Targeting
        sa.Column('entity_types', sa.ARRAY(sa.String(50)), nullable=True),  # ['destination', 'attraction']
        sa.Column('insert_position', sa.String(50), default='after_content'),  # after_intro, middle, after_content, sidebar

        # Styling
        sa.Column('style', sa.String(50), default='card'),  # card, banner, inline
        sa.Column('background_color', sa.String(20), nullable=True),  # #FEF7ED
        sa.Column('text_color', sa.String(20), nullable=True),
        sa.Column('icon', sa.String(50), nullable=True),  # sparkles, phone, mail

        # Status
        sa.Column('is_active', sa.Boolean, default=True, nullable=False),
        sa.Column('sort_order', sa.Integer, default=0, nullable=False),

        # Timestamps
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), onupdate=sa.text('now()'), nullable=False),
    )

    # Index for quick lookup
    op.create_index('ix_content_cta_blocks_type', 'content_cta_blocks', ['cta_type'])
    op.create_index('ix_content_cta_blocks_active', 'content_cta_blocks', ['is_active'])


def downgrade():
    op.drop_index('ix_content_cta_blocks_active')
    op.drop_index('ix_content_cta_blocks_type')
    op.drop_table('content_cta_blocks')
