"""Invoicing system — invoices, lines, VAT details, numbering, payment links,
trip insurances (Chapka ready), forex hedges (Kantox ready).

Adds VAT configuration columns to tenants.

Revision ID: 065_invoicing_system
Revises: 064_status_before_select
Create Date: 2026-02-12
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision = "065_invoicing_system"
down_revision = "064_status_before_select"


def upgrade() -> None:
    # ================================================================
    # 1. Add VAT / sender columns to tenants
    # ================================================================
    op.add_column("tenants", sa.Column("vat_regime", sa.String(20), nullable=True))
    op.add_column("tenants", sa.Column("vat_rate", sa.DECIMAL(5, 2), nullable=True))
    op.add_column("tenants", sa.Column("vat_legal_mention", sa.Text, nullable=True))
    op.add_column("tenants", sa.Column("invoice_sender_info", JSONB, nullable=True))

    # ================================================================
    # 2. invoice_number_sequences — atomic sequential numbering
    # ================================================================
    op.create_table(
        "invoice_number_sequences",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("tenant_id", UUID(as_uuid=True), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("type", sa.String(5), nullable=False),  # DEV, PRO, FA, AV
        sa.Column("year", sa.Integer, nullable=False),
        sa.Column("last_sequence", sa.Integer, nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("tenant_id", "type", "year", name="uq_inv_seq_tenant_type_year"),
    )

    # ================================================================
    # 3. invoices — main invoice table
    # ================================================================
    op.create_table(
        "invoices",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("tenant_id", UUID(as_uuid=True), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True),
        # Type & numbering
        sa.Column("type", sa.Enum("DEV", "PRO", "FA", "AV", name="invoice_type_enum"), nullable=False),
        sa.Column("number", sa.String(20), unique=True, nullable=False),
        sa.Column("year", sa.Integer, nullable=False),
        sa.Column("sequence", sa.Integer, nullable=False),
        # References
        sa.Column("dossier_id", UUID(as_uuid=True), sa.ForeignKey("dossiers.id", ondelete="SET NULL"), nullable=True),
        sa.Column("trip_id", sa.BigInteger, sa.ForeignKey("trips.id", ondelete="SET NULL"), nullable=True),
        sa.Column("cotation_id", sa.BigInteger, sa.ForeignKey("trip_cotations.id", ondelete="SET NULL"), nullable=True),
        sa.Column("parent_invoice_id", sa.BigInteger, sa.ForeignKey("invoices.id", ondelete="SET NULL"), nullable=True),
        # Client snapshot
        sa.Column("client_type", sa.Enum("individual", "company", name="client_type_enum"), server_default="individual"),
        sa.Column("client_name", sa.String(255), nullable=True),
        sa.Column("client_email", sa.String(255), nullable=True),
        sa.Column("client_phone", sa.String(50), nullable=True),
        sa.Column("client_company", sa.String(255), nullable=True),
        sa.Column("client_siret", sa.String(20), nullable=True),
        sa.Column("client_vat_number", sa.String(30), nullable=True),
        sa.Column("client_address", sa.Text, nullable=True),
        # Dates
        sa.Column("issue_date", sa.Date, nullable=False),
        sa.Column("due_date", sa.Date, nullable=True),
        sa.Column("travel_start_date", sa.Date, nullable=True),
        sa.Column("travel_end_date", sa.Date, nullable=True),
        # Amounts
        sa.Column("total_ht", sa.DECIMAL(12, 2), server_default="0"),
        sa.Column("total_ttc", sa.DECIMAL(12, 2), nullable=False, server_default="0"),
        sa.Column("deposit_amount", sa.DECIMAL(12, 2), server_default="0"),
        sa.Column("deposit_pct", sa.DECIMAL(5, 2), server_default="30.00"),
        sa.Column("balance_amount", sa.DECIMAL(12, 2), server_default="0"),
        sa.Column("currency", sa.String(3), server_default="EUR"),
        # VAT
        sa.Column("vat_regime", sa.Enum("exempt", "margin", name="vat_regime_enum"), nullable=True),
        sa.Column("vat_rate", sa.DECIMAL(5, 2), server_default="0"),
        sa.Column("vat_amount", sa.DECIMAL(12, 2), server_default="0"),
        sa.Column("vat_legal_mention", sa.Text, nullable=True),
        # Status
        sa.Column("status", sa.Enum("draft", "sent", "paid", "cancelled", name="invoice_status_enum"), server_default="draft"),
        # Payment
        sa.Column("payment_method", sa.String(50), nullable=True),
        sa.Column("payment_ref", sa.String(255), nullable=True),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("paid_amount", sa.DECIMAL(12, 2), nullable=True),
        # PDF
        sa.Column("pdf_url", sa.Text, nullable=True),
        sa.Column("pdf_generated_at", sa.DateTime(timezone=True), nullable=True),
        # Cancellation
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancellation_reason", sa.Text, nullable=True),
        # Metadata
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("client_notes", sa.Text, nullable=True),
        sa.Column("created_by_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sent_to_email", sa.String(255), nullable=True),
        # Timestamps
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("idx_invoices_tenant_dossier", "invoices", ["tenant_id", "dossier_id"])
    op.create_index("idx_invoices_tenant_status", "invoices", ["tenant_id", "status"])
    op.create_unique_constraint("uq_invoices_tenant_type_year_seq", "invoices", ["tenant_id", "type", "year", "sequence"])

    # ================================================================
    # 4. invoice_lines
    # ================================================================
    op.create_table(
        "invoice_lines",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("tenant_id", UUID(as_uuid=True), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("invoice_id", sa.BigInteger, sa.ForeignKey("invoices.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("sort_order", sa.Integer, server_default="0"),
        sa.Column("description", sa.Text, nullable=False),
        sa.Column("details", sa.Text, nullable=True),
        sa.Column("quantity", sa.DECIMAL(10, 2), server_default="1"),
        sa.Column("unit_price_ttc", sa.DECIMAL(12, 2), nullable=False),
        sa.Column("total_ttc", sa.DECIMAL(12, 2), nullable=False),
        sa.Column("line_type", sa.Enum("service", "deposit", "discount", "fee", "insurance", name="invoice_line_type_enum"), server_default="service"),
        # Timestamps
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # ================================================================
    # 5. invoice_vat_details — internal accounting only
    # ================================================================
    op.create_table(
        "invoice_vat_details",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("tenant_id", UUID(as_uuid=True), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("invoice_id", sa.BigInteger, sa.ForeignKey("invoices.id", ondelete="CASCADE"), unique=True, nullable=False),
        sa.Column("selling_price_ttc", sa.DECIMAL(12, 2), nullable=True),
        sa.Column("cost_price_ht", sa.DECIMAL(12, 2), nullable=True),
        sa.Column("margin_ttc", sa.DECIMAL(12, 2), nullable=True),
        sa.Column("margin_ht", sa.DECIMAL(12, 2), nullable=True),
        sa.Column("vat_rate", sa.DECIMAL(5, 2), nullable=True),
        sa.Column("vat_amount", sa.DECIMAL(12, 2), nullable=True),
        sa.Column("period", sa.String(7), nullable=True),  # "2026-02"
        # Timestamps
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # ================================================================
    # 6. invoice_payment_links
    # ================================================================
    op.create_table(
        "invoice_payment_links",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("tenant_id", UUID(as_uuid=True), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("invoice_id", sa.BigInteger, sa.ForeignKey("invoices.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("payment_type", sa.Enum("deposit", "balance", "full", name="invoice_payment_type_enum"), nullable=False),
        sa.Column("amount", sa.DECIMAL(12, 2), nullable=False),
        sa.Column("due_date", sa.Date, nullable=False),
        sa.Column("status", sa.Enum("pending", "paid", "overdue", "cancelled", name="invoice_payment_link_status_enum"), server_default="pending"),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("paid_amount", sa.DECIMAL(12, 2), nullable=True),
        sa.Column("payment_method", sa.String(50), nullable=True),
        sa.Column("payment_ref", sa.String(255), nullable=True),
        # Timestamps
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # ================================================================
    # 7. trip_insurances — Chapka READY
    # ================================================================
    op.create_table(
        "trip_insurances",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("tenant_id", UUID(as_uuid=True), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("dossier_id", UUID(as_uuid=True), sa.ForeignKey("dossiers.id", ondelete="CASCADE"), nullable=False),
        sa.Column("invoice_id", sa.BigInteger, sa.ForeignKey("invoices.id", ondelete="SET NULL"), nullable=True),
        sa.Column("insurance_type", sa.Enum("assistance", "annulation", "multirisques", name="insurance_type_enum"), nullable=False),
        sa.Column("provider", sa.String(50), server_default="chapka"),
        sa.Column("policy_number", sa.String(100), nullable=True),
        sa.Column("premium_amount", sa.DECIMAL(12, 2), nullable=True),
        sa.Column("commission_pct", sa.DECIMAL(5, 2), server_default="25.00"),
        sa.Column("commission_amount", sa.DECIMAL(12, 2), nullable=True),
        sa.Column("currency", sa.String(3), server_default="EUR"),
        sa.Column("status", sa.Enum("quoted", "active", "cancelled", name="insurance_status_enum"), server_default="quoted"),
        sa.Column("start_date", sa.Date, nullable=True),
        sa.Column("end_date", sa.Date, nullable=True),
        sa.Column("pax_count", sa.Integer, nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
        # Timestamps
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # ================================================================
    # 8. forex_hedges — Kantox READY
    # ================================================================
    op.create_table(
        "forex_hedges",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("tenant_id", UUID(as_uuid=True), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("dossier_id", UUID(as_uuid=True), sa.ForeignKey("dossiers.id", ondelete="CASCADE"), nullable=False),
        sa.Column("invoice_id", sa.BigInteger, sa.ForeignKey("invoices.id", ondelete="SET NULL"), nullable=True),
        sa.Column("hedge_type", sa.Enum("deposit", "balance", name="forex_hedge_type_enum"), nullable=False),
        sa.Column("provider", sa.String(50), server_default="kantox"),
        sa.Column("reference", sa.String(100), nullable=True),
        sa.Column("from_currency", sa.String(3), nullable=False),
        sa.Column("to_currency", sa.String(3), nullable=False),
        sa.Column("amount", sa.DECIMAL(12, 2), nullable=False),
        sa.Column("rate", sa.DECIMAL(12, 6), nullable=True),
        sa.Column("purchase_date", sa.Date, nullable=True),
        sa.Column("executed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.Enum("pending", "executed", "cancelled", name="forex_hedge_status_enum"), server_default="pending"),
        sa.Column("notes", sa.Text, nullable=True),
        # Timestamps
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("forex_hedges")
    op.drop_table("trip_insurances")
    op.drop_table("invoice_payment_links")
    op.drop_table("invoice_vat_details")
    op.drop_table("invoice_lines")
    op.drop_table("invoices")
    op.drop_table("invoice_number_sequences")

    # Drop enums
    sa.Enum(name="forex_hedge_status_enum").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="forex_hedge_type_enum").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="insurance_status_enum").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="insurance_type_enum").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="invoice_payment_link_status_enum").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="invoice_payment_type_enum").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="invoice_line_type_enum").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="invoice_status_enum").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="vat_regime_enum").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="client_type_enum").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="invoice_type_enum").drop(op.get_bind(), checkfirst=True)

    # Drop tenant columns
    op.drop_column("tenants", "invoice_sender_info")
    op.drop_column("tenants", "vat_legal_mention")
    op.drop_column("tenants", "vat_rate")
    op.drop_column("tenants", "vat_regime")
