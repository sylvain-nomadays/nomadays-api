"""Add season_level to accommodation_seasons for pricing reference.

Revision ID: 026_season_level
Revises: 025_accommodation_extras
Create Date: 2025-02-07

Adds season_level field to distinguish:
- low: Basse saison
- high: Haute saison (default reference for pricing)
- peak: Peak/Fêtes (Noël, Nouvel An, etc.)
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "026_season_level"
down_revision = "025_accommodation_extras"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add season_level column with default 'high'
    op.add_column(
        'accommodation_seasons',
        sa.Column('season_level', sa.String(10), nullable=False, server_default='high')
    )

    # Try to auto-detect season levels based on common naming patterns
    # Peak seasons (Noël, Christmas, New Year, Easter, etc.)
    op.execute("""
        UPDATE accommodation_seasons
        SET season_level = 'peak'
        WHERE LOWER(name) SIMILAR TO '%(noel|noël|christmas|new year|nouvel an|easter|pâques|paques|festive|peak|xmas)%'
    """)

    # Low seasons
    op.execute("""
        UPDATE accommodation_seasons
        SET season_level = 'low'
        WHERE LOWER(name) SIMILAR TO '%(low|basse|green|mousson|monsoon|off.?season)%'
        AND season_level = 'high'
    """)


def downgrade() -> None:
    op.drop_column('accommodation_seasons', 'season_level')
