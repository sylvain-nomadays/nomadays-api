"""
Invoice models — invoices, lines, VAT details, numbering sequences, payment links.
Supports DEV (devis), PRO (proforma), FA (facture), AV (avoir).
French legal requirements: sequential numbering, VAT on margin or exempt.
"""

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Optional, List, TYPE_CHECKING

from sqlalchemy import (
    BigInteger, String, Date, DateTime, Integer, DECIMAL, Text, Boolean,
    ForeignKey, Enum as SQLEnum, UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import TenantBase

if TYPE_CHECKING:
    from app.models.dossier import Dossier
    from app.models.trip import Trip
    from app.models.cotation import TripCotation
    from app.models.user import User


class InvoiceNumberSequence(TenantBase):
    """
    Atomic sequential numbering per tenant/type/year.
    Uses SELECT ... FOR UPDATE for gap-free allocation.
    """

    __tablename__ = "invoice_number_sequences"
    __table_args__ = (
        UniqueConstraint("tenant_id", "type", "year", name="uq_inv_seq_tenant_type_year"),
    )

    type: Mapped[str] = mapped_column(String(5), nullable=False)  # DEV, PRO, FA, AV
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    last_sequence: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")

    def __repr__(self) -> str:
        return f"<InvoiceNumberSequence(tenant={self.tenant_id}, type='{self.type}', year={self.year}, last={self.last_sequence})>"


class Invoice(TenantBase):
    """
    A financial document: Devis (DEV), Proforma (PRO), Facture (FA), or Avoir (AV).
    Client info is snapshot at creation time (immutable after emission).
    """

    __tablename__ = "invoices"

    # Type & numbering
    type: Mapped[str] = mapped_column(
        SQLEnum("DEV", "PRO", "FA", "AV", name="invoice_type_enum"),
        nullable=False,
    )
    number: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)

    # References
    dossier_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("dossiers.id", ondelete="SET NULL"),
        nullable=True,
    )
    trip_id: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        ForeignKey("trips.id", ondelete="SET NULL"),
        nullable=True,
    )
    cotation_id: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        ForeignKey("trip_cotations.id", ondelete="SET NULL"),
        nullable=True,
    )
    parent_invoice_id: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        ForeignKey("invoices.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Client snapshot (frozen at invoice creation)
    client_type: Mapped[Optional[str]] = mapped_column(
        SQLEnum("individual", "company", name="client_type_enum"),
        server_default="individual",
    )
    client_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    client_email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    client_phone: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    client_company: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    client_siret: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    client_vat_number: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    client_address: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    client_siren: Mapped[Optional[str]] = mapped_column(String(9), nullable=True)  # Réforme 2026 — obligatoire B2B

    # Delivery address (réforme 2026 — si différente de l'adresse client)
    delivery_address_line1: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    delivery_address_city: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    delivery_address_postal_code: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    delivery_address_country: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    # Dates
    issue_date: Mapped[date] = mapped_column(Date, nullable=False)
    due_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    travel_start_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    travel_end_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)

    # Amounts (all TTC for client-facing)
    total_ht: Mapped[Decimal] = mapped_column(DECIMAL(12, 2), server_default="0")
    total_ttc: Mapped[Decimal] = mapped_column(DECIMAL(12, 2), nullable=False, server_default="0")
    deposit_amount: Mapped[Decimal] = mapped_column(DECIMAL(12, 2), server_default="0")
    deposit_pct: Mapped[Decimal] = mapped_column(DECIMAL(5, 2), server_default="30.00")
    balance_amount: Mapped[Decimal] = mapped_column(DECIMAL(12, 2), server_default="0")
    currency: Mapped[str] = mapped_column(String(3), server_default="EUR")

    # VAT
    vat_regime: Mapped[Optional[str]] = mapped_column(
        SQLEnum("exempt", "margin", name="vat_regime_enum"),
        nullable=True,
    )
    vat_rate: Mapped[Decimal] = mapped_column(DECIMAL(5, 2), server_default="0")
    vat_amount: Mapped[Decimal] = mapped_column(DECIMAL(12, 2), server_default="0")
    vat_legal_mention: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Réforme e-facture 2026
    operation_category: Mapped[Optional[str]] = mapped_column(
        String(4), server_default="PS", nullable=True,
    )  # LB (livraison biens), PS (prestation services), LBPS (les deux)
    vat_on_debits: Mapped[Optional[bool]] = mapped_column(
        Boolean, server_default="false", nullable=True,
    )  # Option TVA sur débits (false = encaissements, standard agence voyage)
    electronic_format: Mapped[Optional[str]] = mapped_column(
        String(20), server_default="facturx_basic", nullable=True,
    )  # facturx_minimum, facturx_basic, facturx_en16931
    pa_transmission_status: Mapped[Optional[str]] = mapped_column(
        String(20), server_default="draft", nullable=True,
    )  # draft, pending, transmitted, accepted, rejected
    pa_transmission_date: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    pa_transmission_id: Mapped[Optional[str]] = mapped_column(
        String(100), nullable=True,
    )  # Identifiant retourné par la plateforme agréée

    # Status
    status: Mapped[str] = mapped_column(
        SQLEnum("draft", "sent", "paid", "cancelled", name="invoice_status_enum"),
        server_default="draft",
    )

    # Payment
    payment_method: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    payment_ref: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    paid_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    paid_amount: Mapped[Optional[Decimal]] = mapped_column(DECIMAL(12, 2), nullable=True)

    # PDF
    pdf_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    pdf_generated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Cancellation
    cancelled_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    cancellation_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Pax / Insured persons (for Chapka insurance integration)
    pax_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # Number of insured persons
    pax_names: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON array of participant names

    # Metadata
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    client_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    sent_to_email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # Relationships
    dossier: Mapped[Optional["Dossier"]] = relationship("Dossier", back_populates="invoices")
    trip: Mapped[Optional["Trip"]] = relationship("Trip")
    cotation: Mapped[Optional["TripCotation"]] = relationship("TripCotation")
    parent_invoice: Mapped[Optional["Invoice"]] = relationship(
        "Invoice", remote_side="Invoice.id", uselist=False,
    )
    created_by: Mapped[Optional["User"]] = relationship("User", foreign_keys=[created_by_id])
    lines: Mapped[List["InvoiceLine"]] = relationship(
        "InvoiceLine", back_populates="invoice", cascade="all, delete-orphan",
        order_by="InvoiceLine.sort_order",
    )
    vat_details: Mapped[Optional["InvoiceVatDetail"]] = relationship(
        "InvoiceVatDetail", back_populates="invoice", cascade="all, delete-orphan", uselist=False,
    )
    payment_links: Mapped[List["InvoicePaymentLink"]] = relationship(
        "InvoicePaymentLink", back_populates="invoice", cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<Invoice(id={self.id}, number='{self.number}', type='{self.type}', status='{self.status}')>"


class InvoiceLine(TenantBase):
    """A line item on an invoice."""

    __tablename__ = "invoice_lines"

    invoice_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("invoices.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    sort_order: Mapped[int] = mapped_column(Integer, server_default="0")
    description: Mapped[str] = mapped_column(Text, nullable=False)
    details: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    quantity: Mapped[Decimal] = mapped_column(DECIMAL(10, 2), server_default="1")
    unit_price_ttc: Mapped[Decimal] = mapped_column(DECIMAL(12, 2), nullable=False)
    total_ttc: Mapped[Decimal] = mapped_column(DECIMAL(12, 2), nullable=False)
    line_type: Mapped[str] = mapped_column(
        SQLEnum("service", "deposit", "discount", "fee", "insurance", name="invoice_line_type_enum"),
        server_default="service",
    )

    # Relationships
    invoice: Mapped["Invoice"] = relationship("Invoice", back_populates="lines")

    def __repr__(self) -> str:
        return f"<InvoiceLine(id={self.id}, desc='{self.description[:40]}', total={self.total_ttc})>"


class InvoiceVatDetail(TenantBase):
    """
    Internal VAT calculation for accounting (TVA sur la marge).
    NOT visible to client — only for tax return.
    """

    __tablename__ = "invoice_vat_details"

    invoice_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("invoices.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )
    selling_price_ttc: Mapped[Optional[Decimal]] = mapped_column(DECIMAL(12, 2), nullable=True)
    cost_price_ht: Mapped[Optional[Decimal]] = mapped_column(DECIMAL(12, 2), nullable=True)
    margin_ttc: Mapped[Optional[Decimal]] = mapped_column(DECIMAL(12, 2), nullable=True)
    margin_ht: Mapped[Optional[Decimal]] = mapped_column(DECIMAL(12, 2), nullable=True)
    vat_rate: Mapped[Optional[Decimal]] = mapped_column(DECIMAL(5, 2), nullable=True)
    vat_amount: Mapped[Optional[Decimal]] = mapped_column(DECIMAL(12, 2), nullable=True)
    period: Mapped[Optional[str]] = mapped_column(String(7), nullable=True)  # "2026-02"

    # Relationships
    invoice: Mapped["Invoice"] = relationship("Invoice", back_populates="vat_details")

    def __repr__(self) -> str:
        return f"<InvoiceVatDetail(invoice_id={self.invoice_id}, vat={self.vat_amount})>"


class InvoicePaymentLink(TenantBase):
    """Payment link for deposit or balance (Stripe or bank transfer)."""

    __tablename__ = "invoice_payment_links"

    invoice_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("invoices.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    payment_type: Mapped[str] = mapped_column(
        SQLEnum("deposit", "balance", "full", name="invoice_payment_type_enum"),
        nullable=False,
    )
    amount: Mapped[Decimal] = mapped_column(DECIMAL(12, 2), nullable=False)
    due_date: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(
        SQLEnum("pending", "paid", "overdue", "cancelled", name="invoice_payment_link_status_enum"),
        server_default="pending",
    )
    paid_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    paid_amount: Mapped[Optional[Decimal]] = mapped_column(DECIMAL(12, 2), nullable=True)
    payment_method: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    payment_ref: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # Relationships
    invoice: Mapped["Invoice"] = relationship("Invoice", back_populates="payment_links")

    def __repr__(self) -> str:
        return f"<InvoicePaymentLink(id={self.id}, type='{self.payment_type}', amount={self.amount}, status='{self.status}')>"


# Imports at end to avoid circular imports
from app.models.dossier import Dossier
from app.models.trip import Trip
from app.models.cotation import TripCotation
from app.models.user import User
