"""
ForexHedge model — Kantox integration (READY, not connected).
Tracks forex hedging operations for travel dossiers.
Two purchases per dossier: deposit and balance.
"""

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Optional, TYPE_CHECKING

from sqlalchemy import BigInteger, String, Date, DateTime, DECIMAL, Text, ForeignKey, Enum as SQLEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import TenantBase

if TYPE_CHECKING:
    from app.models.dossier import Dossier
    from app.models.invoice import Invoice


class ForexHedge(TenantBase):
    """
    Forex hedging operation linked to a dossier.
    Kantox READY: models and CRUD exist, but no external API connection.

    Two hedges per dossier:
    - deposit: triggered on deposit payment, purchase at payment + 10 days
    - balance: triggered on balance due date, purchase at due + 7 days

    Client rate = Market rate - 2% (Nomadays margin)
    """

    __tablename__ = "forex_hedges"

    # References
    dossier_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("dossiers.id", ondelete="CASCADE"),
        nullable=False,
    )
    invoice_id: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        ForeignKey("invoices.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Hedge type
    hedge_type: Mapped[str] = mapped_column(
        SQLEnum("deposit", "balance", name="forex_hedge_type_enum"),
        nullable=False,
    )
    provider: Mapped[str] = mapped_column(String(50), server_default="kantox")
    reference: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    # Currencies
    from_currency: Mapped[str] = mapped_column(String(3), nullable=False)
    to_currency: Mapped[str] = mapped_column(String(3), nullable=False)

    # Amount & rate
    amount: Mapped[Decimal] = mapped_column(DECIMAL(12, 2), nullable=False)
    rate: Mapped[Optional[Decimal]] = mapped_column(DECIMAL(12, 6), nullable=True)

    # Dates
    purchase_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    executed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Status
    status: Mapped[str] = mapped_column(
        SQLEnum("pending", "executed", "cancelled", name="forex_hedge_status_enum"),
        server_default="pending",
    )

    # Notes
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Relationships
    dossier: Mapped["Dossier"] = relationship("Dossier")
    invoice: Mapped[Optional["Invoice"]] = relationship("Invoice")

    def __repr__(self) -> str:
        return f"<ForexHedge(id={self.id}, type='{self.hedge_type}', {self.from_currency}/{self.to_currency}, status='{self.status}')>"


# Imports at end to avoid circular imports
from app.models.dossier import Dossier
from app.models.invoice import Invoice
