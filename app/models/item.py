"""
Item and ItemSeason models - the core of quotation.
Items are cost elements within formulas.
"""

from datetime import date
from decimal import Decimal
from typing import Optional, List, TYPE_CHECKING

from sqlalchemy import BigInteger, String, Date, Integer, Boolean, DECIMAL, ForeignKey, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import TenantBase

if TYPE_CHECKING:
    from app.models.formula import Formula
    from app.models.condition import ConditionOption
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

    # Cost nature — category (hébergement, transport, activité, guide, etc.)
    cost_nature_id: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        ForeignKey("cost_natures.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Payment flow — how this cost is paid (booking, advance, purchase_order, payroll, manual)
    payment_flow: Mapped[Optional[str]] = mapped_column(
        String(20),
        nullable=True,
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

    # Pricing method (quotation, margin, markup, amount)
    pricing_method: Mapped[str] = mapped_column(
        String(20),
        default="quotation",
    )
    pricing_value: Mapped[Optional[Decimal]] = mapped_column(DECIMAL(12, 2), nullable=True)

    # Ratio configuration (how quantity scales with pax)
    ratio_categories: Mapped[str] = mapped_column(String(255), default="adult")  # Comma-separated
    ratio_per: Mapped[int] = mapped_column(Integer, default=1)  # 1 item per N pax
    ratio_type: Mapped[str] = mapped_column(
        String(20),  # ratio, set
        default="ratio",
    )

    # Temporal multiplier
    times_type: Mapped[str] = mapped_column(
        String(20),  # service_days, total, fixed
        default="service_days",
    )
    times_value: Mapped[int] = mapped_column(Integer, default=1)

    # Conditional inclusion: link item to a specific condition option
    # If the parent formula has condition_id, this item is only included
    # when the trip's selected option matches this value.
    condition_option_id: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        ForeignKey("condition_options.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Tier pricing configuration
    # Which pax categories count for selecting the price tier.
    # NULL = use ratio_categories (retrocompatible). Comma-separated codes.
    tier_categories: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # Override tracking
    is_override: Mapped[bool] = mapped_column(Boolean, default=False)
    override_reason: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # TVA handling (columns already exist in DB from migration 003)
    # Whether the unit_cost includes VAT (TTC). If False, item is HT.
    # Default comes from CostNature.vat_recoverable_default at creation time.
    price_includes_vat: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false"
    )
    # Optional item-level VAT rate override (if None, uses CountryVatRate)
    vat_rate: Mapped[Optional[Decimal]] = mapped_column(DECIMAL(5, 2), nullable=True)

    # Ordering
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    # Relationships
    formula: Mapped["Formula"] = relationship("Formula", back_populates="items")
    cost_nature: Mapped[Optional["CostNature"]] = relationship("CostNature", lazy="selectin")
    supplier: Mapped[Optional["Supplier"]] = relationship("Supplier")
    rate_catalog: Mapped[Optional["RateCatalog"]] = relationship("RateCatalog")
    contract_rate: Mapped[Optional["ContractRate"]] = relationship("ContractRate")
    condition_option: Mapped[Optional["ConditionOption"]] = relationship("ConditionOption")
    seasons: Mapped[List["ItemSeason"]] = relationship(
        "ItemSeason",
        back_populates="item",
        cascade="all, delete-orphan",
    )
    price_tiers: Mapped[List["ItemPriceTier"]] = relationship(
        "ItemPriceTier",
        back_populates="item",
        cascade="all, delete-orphan",
        order_by="ItemPriceTier.pax_min",
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
    valid_from: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    valid_to: Mapped[Optional[date]] = mapped_column(Date, nullable=True)

    # Pricing overrides
    cost_multiplier: Mapped[Optional[Decimal]] = mapped_column(DECIMAL(12, 2), nullable=True)
    cost_override: Mapped[Optional[Decimal]] = mapped_column(DECIMAL(12, 2), nullable=True)

    # Relationships
    item: Mapped["Item"] = relationship("Item", back_populates="seasons")

    def __repr__(self) -> str:
        return f"<ItemSeason(id={self.id}, season='{self.season_name}')>"

    def is_date_in_season(self, check_date: date) -> bool:
        """Check if a date falls within this season."""
        if self.valid_from and self.valid_to:
            return self.valid_from <= check_date <= self.valid_to
        return False


class ItemPriceTier(TenantBase):
    """
    A price tier for an item based on pax count.
    When an item has price_tiers, the engine selects the matching tier
    based on the number of pax in the tier_categories (or ratio_categories).

    Supports:
    - Rule 1 (tiered per-person): ratio_type='ratio' + tiers → different unit_cost per pax range
    - Rule 2 (tiered set): ratio_type='set' + tiers → different total cost per pax range
    - Category adjustments: {"child": -10, "baby": -100} = -10% child, free baby
    """

    __tablename__ = "item_price_tiers"

    # Item relationship
    item_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("items.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Pax range (inclusive bounds)
    pax_min: Mapped[int] = mapped_column(Integer, nullable=False)
    pax_max: Mapped[int] = mapped_column(Integer, nullable=False)

    # Price for this tier
    unit_cost: Mapped[Decimal] = mapped_column(DECIMAL(12, 2), nullable=False)

    # Category-specific % adjustments (optional)
    # e.g. {"child": -10, "baby": -100} → -10% for children, free for babies
    category_adjustments_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    # Display order
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    # Relationships
    item: Mapped["Item"] = relationship("Item", back_populates="price_tiers")

    def __repr__(self) -> str:
        return f"<ItemPriceTier(id={self.id}, pax={self.pax_min}-{self.pax_max}, cost={self.unit_cost})>"


# Import at end to avoid circular imports
from app.models.formula import Formula
from app.models.condition import ConditionOption
from app.models.cost_nature import CostNature
from app.models.supplier import Supplier
from app.models.rate_catalog import RateCatalog
from app.models.contract import ContractRate
