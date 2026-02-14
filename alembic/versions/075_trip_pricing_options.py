"""Trip pricing options — multi-tarif support + validity date + advisor notes.

Adds:
- trip_pax_configs.valid_until: date de validité de l'offre tarifaire
- trip_pax_configs.is_primary: marque le tarif principal (vs option/supplément)
- trip_pax_configs.option_type: 'base' | 'supplement' | 'alternative'
- trip_pax_configs.description: texte libre pour décrire l'option
- trips.advisor_notes_html: notes de l'agent sur les choix / différences

Revision ID: 075_trip_pricing_options
Revises: 074_cms_snippets
Create Date: 2026-02-14
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers
revision = "075_trip_pricing_options"
down_revision = "074_cms_snippets"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── trip_pax_configs: multi-tarif support ──
    op.add_column(
        "trip_pax_configs",
        sa.Column("valid_until", sa.Date(), nullable=True, comment="Date de validité de l'offre"),
    )
    op.add_column(
        "trip_pax_configs",
        sa.Column(
            "is_primary",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
            comment="Tarif principal (true) vs option/supplément (false)",
        ),
    )
    op.add_column(
        "trip_pax_configs",
        sa.Column(
            "option_type",
            sa.String(20),
            server_default="base",
            nullable=False,
            comment="Type: base, supplement, alternative",
        ),
    )
    op.add_column(
        "trip_pax_configs",
        sa.Column(
            "description",
            sa.Text(),
            nullable=True,
            comment="Description de l'option (ex: Hôtel Classique 3*, Guide francophone)",
        ),
    )
    op.add_column(
        "trip_pax_configs",
        sa.Column(
            "supplement_price",
            sa.Numeric(12, 2),
            nullable=True,
            comment="Prix du supplément (si option_type = supplement)",
        ),
    )
    op.add_column(
        "trip_pax_configs",
        sa.Column(
            "supplement_per_person",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
            comment="Le supplément est-il par personne ?",
        ),
    )
    op.add_column(
        "trip_pax_configs",
        sa.Column(
            "sort_order",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
            comment="Ordre d'affichage",
        ),
    )

    # ── trips: advisor notes for proposal comparison ──
    op.add_column(
        "trips",
        sa.Column(
            "advisor_notes_html",
            sa.Text(),
            nullable=True,
            comment="Notes de l'agent sur les choix et différences entre propositions",
        ),
    )

    # GRANT SELECT for client-side access (Supabase PostgREST)
    # Note: trip_pax_configs already has GRANT from previous session,
    # but we ensure the new columns are accessible
    op.execute("GRANT SELECT ON trip_pax_configs TO authenticated;")
    op.execute("GRANT SELECT ON trip_pax_configs TO anon;")


def downgrade() -> None:
    op.drop_column("trips", "advisor_notes_html")
    op.drop_column("trip_pax_configs", "sort_order")
    op.drop_column("trip_pax_configs", "supplement_per_person")
    op.drop_column("trip_pax_configs", "supplement_price")
    op.drop_column("trip_pax_configs", "description")
    op.drop_column("trip_pax_configs", "option_type")
    op.drop_column("trip_pax_configs", "is_primary")
    op.drop_column("trip_pax_configs", "valid_until")
