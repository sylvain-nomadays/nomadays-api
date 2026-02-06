"""
CountryVatRate model - VAT/TVA rates configuration per country per tenant.
Different rates can be set for different service categories.
"""

from decimal import Decimal
from typing import Optional

from sqlalchemy import String, Boolean, DECIMAL, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import TenantBase


class CountryVatRate(TenantBase):
    """
    VAT/TVA rates configuration for a specific country.
    Allows different rates for different service types (hotel, transport, etc.).
    """

    __tablename__ = "country_vat_rates"

    # Country
    country_code: Mapped[str] = mapped_column(String(2), nullable=False, index=True)
    country_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    # VAT rates by category (in percentage, e.g., 10.00 = 10%)
    vat_rate_standard: Mapped[Decimal] = mapped_column(
        DECIMAL(5, 2),
        default=Decimal("0.00"),
        nullable=False,
    )
    vat_rate_hotel: Mapped[Optional[Decimal]] = mapped_column(
        DECIMAL(5, 2),
        nullable=True,
    )
    vat_rate_restaurant: Mapped[Optional[Decimal]] = mapped_column(
        DECIMAL(5, 2),
        nullable=True,
    )
    vat_rate_transport: Mapped[Optional[Decimal]] = mapped_column(
        DECIMAL(5, 2),
        nullable=True,
    )
    vat_rate_activity: Mapped[Optional[Decimal]] = mapped_column(
        DECIMAL(5, 2),
        nullable=True,
    )

    # Status
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    # Unique constraint per tenant + country
    __table_args__ = (
        UniqueConstraint("tenant_id", "country_code", name="uq_country_vat_tenant_country"),
    )

    def __repr__(self) -> str:
        return f"<CountryVatRate(country='{self.country_code}', standard={self.vat_rate_standard}%)>"

    def get_rate_for_category(self, category: str) -> Decimal:
        """
        Get the VAT rate for a specific category.
        Falls back to standard rate if category-specific rate is not set.
        """
        rate_map = {
            "hotel": self.vat_rate_hotel,
            "accommodation": self.vat_rate_hotel,
            "restaurant": self.vat_rate_restaurant,
            "meal": self.vat_rate_restaurant,
            "transport": self.vat_rate_transport,
            "activity": self.vat_rate_activity,
        }

        specific_rate = rate_map.get(category.lower())
        return specific_rate if specific_rate is not None else self.vat_rate_standard


# Default VAT rates for common destinations
DEFAULT_COUNTRY_VAT_RATES = [
    {"country_code": "FR", "country_name": "France", "vat_rate_standard": Decimal("20.00"), "vat_rate_hotel": Decimal("10.00"), "vat_rate_restaurant": Decimal("10.00")},
    {"country_code": "MA", "country_name": "Maroc", "vat_rate_standard": Decimal("20.00"), "vat_rate_hotel": Decimal("10.00")},
    {"country_code": "TH", "country_name": "Thaïlande", "vat_rate_standard": Decimal("7.00")},
    {"country_code": "VN", "country_name": "Vietnam", "vat_rate_standard": Decimal("10.00")},
    {"country_code": "KH", "country_name": "Cambodge", "vat_rate_standard": Decimal("10.00")},
    {"country_code": "LA", "country_name": "Laos", "vat_rate_standard": Decimal("10.00")},
    {"country_code": "MM", "country_name": "Myanmar", "vat_rate_standard": Decimal("5.00")},
    {"country_code": "ID", "country_name": "Indonésie", "vat_rate_standard": Decimal("11.00")},
    {"country_code": "MY", "country_name": "Malaisie", "vat_rate_standard": Decimal("6.00")},
    {"country_code": "GE", "country_name": "Géorgie", "vat_rate_standard": Decimal("18.00")},
    {"country_code": "AM", "country_name": "Arménie", "vat_rate_standard": Decimal("20.00")},
]
