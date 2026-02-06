"""
Rate Catalog model - the tenant's price database.
Rates can come from contracts, be manually entered, or AI-suggested.
"""

from datetime import date
from decimal import Decimal
from typing import Optional

from sqlalchemy import BigInteger, String, Date, DECIMAL, ForeignKey, Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import TenantBase


class RateCatalog(TenantBase):
    """
    A rate in the tenant's catalog.
    Can be linked to a contract rate (synced) or manual entry.
    """

    __tablename__ = "rate_catalog"

    # Source tracking
    contract_rate_id: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        ForeignKey("contract_rates.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    supplier_id: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        ForeignKey("suppliers.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    cost_nature_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("cost_natures.id", ondelete="RESTRICT"),
        nullable=False,
    )

    # Service identification
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    category: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)  # accommodation, activity, transport
    pax_category: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    # Pricing
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="EUR")
    price: Mapped[Decimal] = mapped_column(DECIMAL(12, 2), nullable=False)

    # Seasonality
    season_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    valid_from: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    valid_to: Mapped[Optional[date]] = mapped_column(Date, nullable=True)

    # Day of week (bitmask)
    day_of_week_mask: Mapped[int] = mapped_column(default=127)

    # Source type
    source: Mapped[str] = mapped_column(
        SQLEnum("contract", "manual", "ai_suggested", name="rate_source_enum"),
        default="manual",
    )

    # Relationships
    contract_rate: Mapped[Optional["ContractRate"]] = relationship("ContractRate")
    supplier: Mapped[Optional["Supplier"]] = relationship("Supplier")
    cost_nature: Mapped["CostNature"] = relationship("CostNature")

    def __repr__(self) -> str:
        return f"<RateCatalog(id={self.id}, name='{self.name}', price={self.price})>"


# Import at end to avoid circular imports
from app.models.contract import ContractRate
from app.models.supplier import Supplier
from app.models.cost_nature import CostNature
