"""Client view grants — allow Supabase authenticated/anon to read accommodation & condition data.

These tables were created by Alembic and need explicit GRANT SELECT
for Supabase PostgREST queries (client-facing pages).

Revision ID: 076_client_view_grants
Revises: 075_trip_pricing_options
Create Date: 2026-02-14
"""
from alembic import op

# revision identifiers
revision = "076_client_view_grants"
down_revision = "075_trip_pricing_options"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Accommodation data for client trip program view
    op.execute("GRANT SELECT ON accommodations TO authenticated;")
    op.execute("GRANT SELECT ON accommodations TO anon;")
    op.execute("GRANT SELECT ON room_categories TO authenticated;")
    op.execute("GRANT SELECT ON room_categories TO anon;")
    op.execute("GRANT SELECT ON accommodation_photos TO authenticated;")
    op.execute("GRANT SELECT ON accommodation_photos TO anon;")

    # Conditions data for accommodation variant tabs
    op.execute("GRANT SELECT ON conditions TO authenticated;")
    op.execute("GRANT SELECT ON conditions TO anon;")
    op.execute("GRANT SELECT ON condition_options TO authenticated;")
    op.execute("GRANT SELECT ON condition_options TO anon;")
    op.execute("GRANT SELECT ON trip_conditions TO authenticated;")
    op.execute("GRANT SELECT ON trip_conditions TO anon;")

    # Items — needed to read condition_option_id for variant matching
    op.execute("GRANT SELECT ON items TO authenticated;")
    op.execute("GRANT SELECT ON items TO anon;")


def downgrade() -> None:
    op.execute("REVOKE SELECT ON items FROM authenticated;")
    op.execute("REVOKE SELECT ON items FROM anon;")
    op.execute("REVOKE SELECT ON trip_conditions FROM authenticated;")
    op.execute("REVOKE SELECT ON trip_conditions FROM anon;")
    op.execute("REVOKE SELECT ON condition_options FROM authenticated;")
    op.execute("REVOKE SELECT ON condition_options FROM anon;")
    op.execute("REVOKE SELECT ON conditions FROM authenticated;")
    op.execute("REVOKE SELECT ON conditions FROM anon;")
    op.execute("REVOKE SELECT ON accommodation_photos FROM authenticated;")
    op.execute("REVOKE SELECT ON accommodation_photos FROM anon;")
    op.execute("REVOKE SELECT ON room_categories FROM authenticated;")
    op.execute("REVOKE SELECT ON room_categories FROM anon;")
    op.execute("REVOKE SELECT ON accommodations FROM authenticated;")
    op.execute("REVOKE SELECT ON accommodations FROM anon;")
