"""
Item and ItemSeason models - the core of quotation.
Items are cost elements within formulas.
"""

from datetime import date
from decimal import Decimal
from typing import Optional, List, TYPE_CHECKING

from sqlalchemy import BigInteger, String, Date, Integer, Boolean, DECIMAL, ForeignKey, Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import TenantBase

if TYPE_CHECKING:
    from app.models.formula import Formula, Condition
    from app.models.cost_nature import CostNature
    from app.models.supplier import Supplier
    from app.models.rate_catalog import RateCatalog
    from app.models.contract import ContractRate


class Item(TenantBase):
    """
    A cost item within a formula.
    This is the core entity for quotation calculation.
    """

    __tablename__ = "items"

    # Formula relationship
    formula_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("formulas.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Identity
    name: Mapped[str] = mapped_column(String(255), nullable=False)

    # Cost nature (determines downstream processing)
    cost_nature_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("cost_natures.id", ondelete="RESTRICT"),
        nullable=False,
    )

    # Supplier (optional)
    supplier_id: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        ForeignKey("suppliers.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Rate references (for price synchronization)
    rate_catalog_id: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        ForeignKey("rate_catalog.id", ondelete="SET NULL"),
        nullable=True,
    )
    contract_rate_id: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        ForeignKey("contract_rates.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Pricing
    currency: Mapped[str] = mapped_column(String(3), default="THB")
    unit_cost: Mapped[Decimal] = mapped_column(DECIMAL(12, 2), default=Decimal("0.00"))

    # Pricing method
    pricing_method: Mapped[str] = mapped_column(
        SQLEnum("quotation", "margin", "markup", "amount", name="pricing_method_enum"),
        default="quotation",
    )
    pricing_value: Mapped[Optional[Decimal]] = mapped_column(DECIMAL(12, 2), nullable=True)

    # Ratio configuration (how quantity scales with pax)
    ratio_categories: Mapped[str] = mapped_column(String(255), default="adult")  # Comma-separated
    ratio_per: Mapped[int] = mapped_column(Integer, default=1)  # 1 item per N pax
    ratio_type: Mapped[str] = mapped_column(
        SQLEnum("ratio", "set", name="ratio_type_enum"),
        default="ratio",
    )

    # Temporal multiplier
    times_type: Mapped[str] = mapped_column(
        SQLEnum("service_days", "total", "fixed", name="times_type_enum"),
        default="service_days",
    )
    times_value: Mapped[int] = mapped_column(Integer, default=1)

    # Conditional inclusion
    condition_id: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        ForeignKey("conditions.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Override tracking
    is_override: Mapped[bool] = mapped_column(Boolean, default=False)
    override_reason: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # Ordering
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    # Relationships
    formula: Mapped["Formula"] = relationship("Formula", back_populates="items")
    cost_nature: Mapped["CostNature"] = relationship("CostNature")
    supplier: Mapped[Optional["Supplier"]] = relationship("Supplier")
    rate_catalog: Mapped[Optional["RateCatalog"]] = relationship("RateCatalog")
    contract_rate: Mapped[Optional["ContractRate"]] = relationship("ContractRate")
    condition: Mapped[Optional["Condition"]] = relationship("Condition")
    seasons: Mapped[List["ItemSeason"]] = relationship(
        "ItemSeason",
        back_populates="item",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<Item(id={self.id}, name='{self.name}', unit_cost={self.unit_cost})>"

    def get_ratio_categories_list(self) -> List[str]:
        """Get ratio categories as a list."""
        return [c.strip() for c in self.ratio_categories.split(",") if c.strip()]


class ItemSeason(TenantBase):
    """
    Seasonal pricing for an item.
    Overrides unit_cost when the trip date falls within the season.
    """

    __tablename__ = "item_seasons"

    # Item relationship
    item_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("items.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Season definition
    season_name: Mapped[str] = mapped_column(String(100), nullable=False)
    date_start: Mapped[date] = mapped_column(Date, nullable=False)
    date_end: Mapped[date] = mapped_column(Date, nullable=False)

    # Day of week (bitmask)
    day_of_week_mask: Mapped[int] = mapped_column(Integer, default=127)

    # Pricing
    price: Mapped[Decimal] = mapped_column(DECIMAL(12, 2), nullable=False)

    # Availability flag
    is_unavailable: Mapped[bool] = mapped_column(Boolean, default=False)

    # Relationships
    item: Mapped["Item"] = relationship("Item", back_populates="seasons")

    def __repr__(self) -> str:
        return f"<ItemSeason(id={self.id}, season='{self.season_name}', price={self.price})>"

    def is_date_in_season(self, check_date: date) -> bool:
        """Check if a date falls within this season."""
        return self.date_start <= check_date <= self.date_end


# Import at end to avoid circular imports
from app.models.formula import Formula, Condition
from app.models.cost_nature import CostNature
from app.models.supplier import Supplier
from app.models.rate_catalog import RateCatalog
from app.models.contract import ContractRate
