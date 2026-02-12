"""Réforme facture électronique 2026 — nouveaux champs obligatoires.

Adds to invoices: client_siren, delivery address, operation_category,
vat_on_debits, electronic_format, PA transmission tracking.
Adds to tenants: siren.

Revision ID: 066_reform_efacture_2026
Revises: 065_invoicing_system
Create Date: 2026-02-12
"""
from alembic import op
import sqlalchemy as sa

revision = "066_reform_efacture_2026"
down_revision = "065_invoicing_system"


def upgrade() -> None:
    # ================================================================
    # 1. Invoices — réforme e-facture 2026
    # ================================================================

    # SIREN client (obligatoire B2B à partir de sept. 2026)
    op.add_column("invoices", sa.Column("client_siren", sa.String(9), nullable=True))

    # Adresse de livraison (si différente de l'adresse client)
    op.add_column("invoices", sa.Column("delivery_address_line1", sa.String(255), nullable=True))
    op.add_column("invoices", sa.Column("delivery_address_city", sa.String(100), nullable=True))
    op.add_column("invoices", sa.Column("delivery_address_postal_code", sa.String(10), nullable=True))
    op.add_column("invoices", sa.Column("delivery_address_country", sa.String(100), nullable=True))

    # Catégorie d'opération (obligatoire) — PS = prestation de services (agence de voyage)
    op.add_column("invoices", sa.Column(
        "operation_category",
        sa.String(4),
        server_default="PS",
        nullable=True,
    ))

    # Option TVA sur les débits (par défaut faux — encaissements pour agences de voyage)
    op.add_column("invoices", sa.Column(
        "vat_on_debits",
        sa.Boolean,
        server_default=sa.text("false"),
        nullable=True,
    ))

    # Format électronique Factur-X
    op.add_column("invoices", sa.Column(
        "electronic_format",
        sa.String(20),
        server_default="facturx_basic",
        nullable=True,
    ))

    # Statut transmission Plateforme de Dématérialisation Partenaire (PDP)
    op.add_column("invoices", sa.Column(
        "pa_transmission_status",
        sa.String(20),
        server_default="draft",
        nullable=True,
    ))
    op.add_column("invoices", sa.Column(
        "pa_transmission_date",
        sa.DateTime(timezone=True),
        nullable=True,
    ))
    op.add_column("invoices", sa.Column(
        "pa_transmission_id",
        sa.String(100),
        nullable=True,
    ))

    # ================================================================
    # 2. Tenants — SIREN émetteur
    # ================================================================
    op.add_column("tenants", sa.Column("siren", sa.String(9), nullable=True))


def downgrade() -> None:
    # Tenants
    op.drop_column("tenants", "siren")

    # Invoices
    op.drop_column("invoices", "pa_transmission_id")
    op.drop_column("invoices", "pa_transmission_date")
    op.drop_column("invoices", "pa_transmission_status")
    op.drop_column("invoices", "electronic_format")
    op.drop_column("invoices", "vat_on_debits")
    op.drop_column("invoices", "operation_category")
    op.drop_column("invoices", "delivery_address_country")
    op.drop_column("invoices", "delivery_address_postal_code")
    op.drop_column("invoices", "delivery_address_city")
    op.drop_column("invoices", "delivery_address_line1")
    op.drop_column("invoices", "client_siren")
