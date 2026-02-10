"""
Trip models - the main entity for quotation.
Includes Trip, TripDay, and TripPaxConfig.
"""

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Optional, List, TYPE_CHECKING

from sqlalchemy import BigInteger, String, Date, DateTime, Integer, Boolean, DECIMAL, JSON, ForeignKey, Enum as SQLEnum, Table, Column, Text
from sqlalchemy.dialects.postgresql import UUID, ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import TenantBase, Base

if TYPE_CHECKING:
    from app.models.user import User
    from app.models.dossier import Dossier
    from app.models.travel_theme import TravelTheme
    from app.models.trip_location import TripLocation
    from app.models.trip_photo import TripPhoto
    from app.models.location import Location
    from app.models.formula import Formula
    from app.models.condition import Condition, ConditionOption, TripCondition


# Many-to-many junction table for Trip <-> TravelTheme
trip_themes = Table(
    "trip_themes",
    Base.metadata,
    Column("trip_id", BigInteger, ForeignKey("trips.id", ondelete="CASCADE"), primary_key=True),
    Column("theme_id", BigInteger, ForeignKey("travel_themes.id", ondelete="CASCADE"), primary_key=True),
)


class Trip(TenantBase):
    """
    A trip/circuit that can be:
    - online: Published on website (master circuits)
    - gir: Group departures with fixed dates (linked to online master)
    - template: Internal reusable templates (library)
    - custom: Customized for specific clients
    """

    __tablename__ = "trips"

    # Identity
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    reference: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    # Type (category): online, gir, template, custom
    type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="template",
    )

    # Master trip relationship (for GIR: link to online master)
    master_trip_id: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        ForeignKey("trips.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Published status (for online circuits)
    is_published: Mapped[bool] = mapped_column(Boolean, default=False)

    # Template relationship (for derived trips - legacy, use master_trip_id for GIR)
    template_id: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        ForeignKey("trips.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Dossier relationship (for client trips)
    dossier_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("dossiers.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Client info (for type=client)
    client_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    client_email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # Trip details
    start_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    end_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    duration_days: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    # Destination (supports multi-country)
    destination_country: Mapped[Optional[str]] = mapped_column(String(2), nullable=True)  # Primary/legacy
    destination_countries: Mapped[Optional[list]] = mapped_column(ARRAY(String(2)), nullable=True)

    # Trip characteristics
    comfort_level: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # 1-5
    difficulty_level: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # 1-5

    # Pricing defaults
    default_currency: Mapped[str] = mapped_column(String(3), default="EUR")
    margin_pct: Mapped[Decimal] = mapped_column(DECIMAL(5, 2), default=Decimal("30.00"))
    margin_type: Mapped[str] = mapped_column(
        SQLEnum("margin", "markup", name="margin_type_enum"),
        default="margin",
    )

    # Commission structure
    primary_commission_pct: Mapped[Decimal] = mapped_column(DECIMAL(5, 2), default=Decimal("11.50"))
    primary_commission_label: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, default="Nomadays")
    secondary_commission_pct: Mapped[Optional[Decimal]] = mapped_column(DECIMAL(5, 2), nullable=True)
    secondary_commission_label: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    # TVA configuration
    vat_pct: Mapped[Decimal] = mapped_column(DECIMAL(5, 2), default=Decimal("0.00"))
    vat_calculation_mode: Mapped[str] = mapped_column(
        SQLEnum("on_margin", "on_selling_price", name="vat_calculation_mode_enum"),
        default="on_margin",
    )

    # Legacy field (kept for backward compatibility)
    operator_commission_pct: Mapped[Decimal] = mapped_column(DECIMAL(5, 2), default=Decimal("0.00"))

    # Currency exchange rates
    currency_rates_json: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)
    exchange_rate_mode: Mapped[str] = mapped_column(
        SQLEnum("manual", "kantox", name="exchange_rate_mode_enum"),
        default="manual",
    )

    # Presentation fields
    description_short: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    description_tone: Mapped[Optional[str]] = mapped_column(
        SQLEnum("marketing_emotionnel", "aventure", "familial", "factuel", name="description_tone_enum"),
        default="factuel",
        nullable=True,
    )
    highlights: Mapped[Optional[list]] = mapped_column(JSONB, default=list)  # [{title: str, icon?: str}]

    # Inclusions / Exclusions
    inclusions: Mapped[Optional[list]] = mapped_column(JSONB, default=list)  # [{text: str, is_default?: bool}]
    exclusions: Mapped[Optional[list]] = mapped_column(JSONB, default=list)  # [{text: str, is_default?: bool}]

    # Information fields
    info_general: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    info_formalities: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    info_booking_conditions: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    info_cancellation_policy: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    info_additional: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Map configuration
    map_config: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

    # Distribution (B2B syndication)
    is_distributable: Mapped[bool] = mapped_column(Boolean, default=False)
    distribution_channels: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)
    # Example: ["nomadays.com", "partner1.com", "comparateur.fr"]
    external_reference: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    pricing_rules_json: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    # Example: {"partner1": {"markup_pct": 5}, "default": {"markup_pct": 0}}

    # Source tracking (for imported circuits)
    source_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    source_imported_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Language and translation
    language: Mapped[str] = mapped_column(String(5), default="fr", nullable=False)  # fr, en, es, de, it, etc.
    source_trip_id: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        ForeignKey("trips.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )  # For translated circuits: reference to original

    # Status
    status: Mapped[str] = mapped_column(
        SQLEnum(
            "draft",
            "quoted",
            "sent",
            "confirmed",
            "operating",
            "completed",
            "cancelled",
            name="trip_status_enum"
        ),
        default="draft",
    )

    # Versioning
    version: Mapped[int] = mapped_column(Integer, default=1)

    # Ownership
    created_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    assigned_to_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Relationships
    template: Mapped[Optional["Trip"]] = relationship(
        "Trip",
        remote_side="Trip.id",
        foreign_keys=[template_id],
    )
    master_trip: Mapped[Optional["Trip"]] = relationship(
        "Trip",
        remote_side="Trip.id",
        foreign_keys=[master_trip_id],
    )
    gir_departures: Mapped[List["Trip"]] = relationship(
        "Trip",
        foreign_keys="Trip.master_trip_id",
        back_populates="master_trip",
    )
    dossier: Mapped[Optional["Dossier"]] = relationship("Dossier", back_populates="trips")
    created_by: Mapped[Optional["User"]] = relationship("User", foreign_keys=[created_by_id])
    assigned_to: Mapped[Optional["User"]] = relationship("User", foreign_keys=[assigned_to_id])
    days: Mapped[List["TripDay"]] = relationship(
        "TripDay",
        back_populates="trip",
        cascade="all, delete-orphan",
        order_by="TripDay.day_number",
    )
    transversal_formulas: Mapped[List["Formula"]] = relationship(
        "Formula",
        back_populates="trip",
        foreign_keys="Formula.trip_id",
        cascade="all, delete-orphan",
        order_by="Formula.sort_order",
    )
    trip_conditions: Mapped[List["TripCondition"]] = relationship(
        "TripCondition",
        back_populates="trip",
        cascade="all, delete-orphan",
    )
    pax_configs: Mapped[List["TripPaxConfig"]] = relationship(
        "TripPaxConfig",
        back_populates="trip",
        cascade="all, delete-orphan",
    )
    themes: Mapped[List["TravelTheme"]] = relationship(
        "TravelTheme",
        secondary=trip_themes,
        back_populates="trips",
    )
    locations: Mapped[List["TripLocation"]] = relationship(
        "TripLocation",
        back_populates="trip",
        cascade="all, delete-orphan",
        order_by="TripLocation.sort_order",
    )
    # Translation relationships
    source_trip: Mapped[Optional["Trip"]] = relationship(
        "Trip",
        remote_side="Trip.id",
        foreign_keys=[source_trip_id],
    )
    translations: Mapped[List["Trip"]] = relationship(
        "Trip",
        foreign_keys="Trip.source_trip_id",
        back_populates="source_trip",
    )
    # Translation caches (for preview)
    translation_caches: Mapped[List["TripTranslationCache"]] = relationship(
        "TripTranslationCache",
        back_populates="trip",
        cascade="all, delete-orphan",
    )
    # Photos (AI-generated or uploaded)
    photos: Mapped[List["TripPhoto"]] = relationship(
        "TripPhoto",
        back_populates="trip",
        cascade="all, delete-orphan",
        order_by="TripPhoto.sort_order",
    )

    def __repr__(self) -> str:
        return f"<Trip(id={self.id}, name='{self.name}', type='{self.type}')>"

    @property
    def calculated_end_date(self) -> Optional[date]:
        """Calculate end date from start date and duration."""
        if self.start_date and self.duration_days:
            from datetime import timedelta
            return self.start_date + timedelta(days=self.duration_days - 1)
        return self.end_date

    def can_confirm(self) -> bool:
        """Check if this trip can be confirmed."""
        if self.dossier and not self.dossier.can_confirm_trip():
            return False
        return True


class TripDay(TenantBase):
    """
    A day within a trip, containing formulas.
    """

    __tablename__ = "trip_days"

    # Trip relationship
    trip_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("trips.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Day info
    day_number: Mapped[int] = mapped_column(Integer, nullable=False)
    day_number_end: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # NULL = single day, value = range end
    title: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    description: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)

    # Locations (text fields for display)
    location_from: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    location_to: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # Location FK (link to static Location entity for geographic organization)
    location_id: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        ForeignKey("locations.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Ordering
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    # Meals included
    breakfast_included: Mapped[bool] = mapped_column(Boolean, default=False)
    lunch_included: Mapped[bool] = mapped_column(Boolean, default=False)
    dinner_included: Mapped[bool] = mapped_column(Boolean, default=False)

    # Relationships
    trip: Mapped["Trip"] = relationship("Trip", back_populates="days")
    location: Mapped[Optional["Location"]] = relationship("Location")
    formulas: Mapped[List["Formula"]] = relationship(
        "Formula",
        back_populates="trip_day",
        cascade="all, delete-orphan",
        order_by="Formula.sort_order",
    )
    photos: Mapped[List["TripPhoto"]] = relationship(
        "TripPhoto",
        back_populates="trip_day",
        cascade="all, delete-orphan",
        order_by="TripPhoto.sort_order",
    )

    def __repr__(self) -> str:
        return f"<TripDay(id={self.id}, day={self.day_number}, title='{self.title}')>"


class TripPaxConfig(TenantBase):
    """
    A pax configuration for quotation.
    Defines group composition and calculates totals.
    """

    __tablename__ = "trip_pax_configs"

    # Trip relationship
    trip_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("trips.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Configuration
    label: Mapped[str] = mapped_column(String(50), nullable=False)  # "2 pax", "4 pax"
    total_pax: Mapped[int] = mapped_column(Integer, nullable=False)

    # Composition breakdown
    args_json: Mapped[dict] = mapped_column(
        JSON,
        default=dict,
        # Example: {"adult": 4, "child": 1, "guide": 1, "driver": 1, "dbl": 2, "eb": 1}
    )

    # Margin override (optional)
    margin_override_pct: Mapped[Optional[Decimal]] = mapped_column(DECIMAL(5, 2), nullable=True)

    # Calculated totals (updated by quotation engine)
    total_cost: Mapped[Decimal] = mapped_column(DECIMAL(12, 2), default=Decimal("0.00"))
    total_price: Mapped[Decimal] = mapped_column(DECIMAL(12, 2), default=Decimal("0.00"))
    total_profit: Mapped[Decimal] = mapped_column(DECIMAL(12, 2), default=Decimal("0.00"))
    cost_per_person: Mapped[Decimal] = mapped_column(DECIMAL(12, 2), default=Decimal("0.00"))
    price_per_person: Mapped[Decimal] = mapped_column(DECIMAL(12, 2), default=Decimal("0.00"))

    # Relationships
    trip: Mapped["Trip"] = relationship("Trip", back_populates="pax_configs")

    def __repr__(self) -> str:
        return f"<TripPaxConfig(id={self.id}, label='{self.label}', total_pax={self.total_pax})>"


# Import at end to avoid circular imports
from app.models.formula import Formula
from app.models.condition import Condition, ConditionOption, TripCondition
from app.models.trip_translation_cache import TripTranslationCache
from app.models.trip_photo import TripPhoto
