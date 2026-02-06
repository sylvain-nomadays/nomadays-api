"""Trip presentation fields - description, highlights, inclusions, info

Revision ID: 004_trip_presentation
Revises: 003_trip_enhancements
Create Date: 2026-02-06

Adds presentation fields to trips table:
- description_short: Short presentation text (7-10 lines)
- description_tone: Tone of presentation (marketing, adventure, family, factual)
- highlights: Array of key highlights/experiences
- inclusions/exclusions: What's included/excluded
- info_* fields: General info, formalities, booking conditions, cancellation, additional
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, ENUM as PG_ENUM


# revision identifiers, used by Alembic.
revision: str = '004_trip_presentation'
down_revision: Union[str, None] = '003_trip_enhancements'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Create ENUM type for description tone
    op.execute("DROP TYPE IF EXISTS description_tone_enum CASCADE")
    op.execute("CREATE TYPE description_tone_enum AS ENUM ('marketing_emotionnel', 'aventure', 'familial', 'factuel')")

    description_tone = PG_ENUM('marketing_emotionnel', 'aventure', 'familial', 'factuel', name='description_tone_enum', create_type=False)

    # 2. Add presentation fields to trips table
    # Description
    op.add_column('trips', sa.Column('description_short', sa.Text, nullable=True))
    op.add_column('trips', sa.Column('description_tone', description_tone, server_default='factuel', nullable=True))
    op.add_column('trips', sa.Column('highlights', JSONB, server_default='[]', nullable=True))

    # Inclusions / Exclusions
    op.add_column('trips', sa.Column('inclusions', JSONB, server_default='[]', nullable=True))
    op.add_column('trips', sa.Column('exclusions', JSONB, server_default='[]', nullable=True))

    # Information fields
    op.add_column('trips', sa.Column('info_general', sa.Text, nullable=True))
    op.add_column('trips', sa.Column('info_formalities', sa.Text, nullable=True))
    op.add_column('trips', sa.Column('info_booking_conditions', sa.Text, nullable=True))
    op.add_column('trips', sa.Column('info_cancellation_policy', sa.Text, nullable=True))
    op.add_column('trips', sa.Column('info_additional', sa.Text, nullable=True))

    # Map configuration (for storing map display settings)
    op.add_column('trips', sa.Column('map_config', JSONB, nullable=True))


def downgrade() -> None:
    # Remove columns from trips
    op.drop_column('trips', 'map_config')
    op.drop_column('trips', 'info_additional')
    op.drop_column('trips', 'info_cancellation_policy')
    op.drop_column('trips', 'info_booking_conditions')
    op.drop_column('trips', 'info_formalities')
    op.drop_column('trips', 'info_general')
    op.drop_column('trips', 'exclusions')
    op.drop_column('trips', 'inclusions')
    op.drop_column('trips', 'highlights')
    op.drop_column('trips', 'description_tone')
    op.drop_column('trips', 'description_short')

    # Drop enum type
    op.execute("DROP TYPE IF EXISTS description_tone_enum")
