"""Add promo_codes, promo_code_usages tables and billing_address columns on invoices.

Promo codes are centralized (no tenant_id) — shared across all DMCs.
Billing address fields allow clients to validate their address on the public invoice page.

Revision ID: 070_promo_codes_and_billing
Revises: 069_payment_link_url
Create Date: 2026-02-13
"""
from alembic import op
import sqlalchemy as sa

revision = "070_promo_codes_and_billing"
down_revision = "069_payment_link_url"


def upgrade() -> None:
    # --- Promo codes (centralized, no tenant_id) ---
    op.create_table(
        "promo_codes",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("code", sa.String(50), unique=True, nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "discount_type",
            sa.Enum("fixed", "percentage", name="promo_discount_type_enum"),
            nullable=False,
        ),
        sa.Column("discount_value", sa.Numeric(10, 2), nullable=False),
        sa.Column("currency", sa.String(3), server_default="EUR"),
        sa.Column("min_amount", sa.Numeric(10, 2), server_default="0"),
        sa.Column("max_uses", sa.Integer(), nullable=True),  # null = unlimited
        sa.Column("current_uses", sa.Integer(), server_default="0"),
        sa.Column("valid_from", sa.Date(), nullable=True),
        sa.Column("valid_until", sa.Date(), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default="true"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    # --- Promo code usage tracking ---
    op.create_table(
        "promo_code_usages",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "promo_code_id",
            sa.BigInteger(),
            sa.ForeignKey("promo_codes.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "invoice_id",
            sa.BigInteger(),
            sa.ForeignKey("invoices.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("discount_amount", sa.Numeric(10, 2), nullable=False),
        sa.Column(
            "applied_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_promo_code_usages_invoice_id",
        "promo_code_usages",
        ["invoice_id"],
    )

    # --- Billing address columns on invoices ---
    op.add_column("invoices", sa.Column("billing_address_line1", sa.String(255), nullable=True))
    op.add_column("invoices", sa.Column("billing_address_line2", sa.String(255), nullable=True))
    op.add_column("invoices", sa.Column("billing_address_city", sa.String(100), nullable=True))
    op.add_column("invoices", sa.Column("billing_address_postal", sa.String(20), nullable=True))
    op.add_column("invoices", sa.Column("billing_address_country", sa.String(100), nullable=True))
    op.add_column(
        "invoices",
        sa.Column("billing_address_validated_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("invoices", "billing_address_validated_at")
    op.drop_column("invoices", "billing_address_country")
    op.drop_column("invoices", "billing_address_postal")
    op.drop_column("invoices", "billing_address_city")
    op.drop_column("invoices", "billing_address_line2")
    op.drop_column("invoices", "billing_address_line1")
    op.drop_index("ix_promo_code_usages_invoice_id", table_name="promo_code_usages")
    op.drop_table("promo_code_usages")
    op.drop_table("promo_codes")
    sa.Enum(name="promo_discount_type_enum").drop(op.get_bind())
