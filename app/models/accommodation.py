"""
Accommodation models - hotels, room categories, seasons, and rates.
"""

from typing import Optional, List, TYPE_CHECKING
from decimal import Decimal
from datetime import date

from sqlalchemy import (
    String, Boolean, Integer, ForeignKey, Numeric, Text, Date, Enum as SQLEnum, ARRAY
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import TenantBase, Base

if TYPE_CHECKING:
    from app.models.tenant import Tenant
    from app.models.supplier import Supplier
    from app.models.location import Location
    from app.models.payment_terms import PaymentTerms
    from app.models.accommodation_photo import AccommodationPhoto


# Enums
class AccommodationStatus:
    ACTIVE = "active"
    INACTIVE = "inactive"
    PENDING = "pending"


class SeasonType:
    FIXED = "fixed"
    RECURRING = "recurring"
    WEEKDAY = "weekday"


class MealPlan:
    RO = "RO"  # Room Only
    BB = "BB"  # Bed & Breakfast
    HB = "HB"  # Half Board
    FB = "FB"  # Full Board
    AI = "AI"  # All Inclusive


class RoomBedType:
    SGL = "SGL"
    DBL = "DBL"
    TWN = "TWN"
    TPL = "TPL"
    FAM = "FAM"
    EXB = "EXB"  # Extra Bed
    CNT = "CNT"  # Child/Cot


class Accommodation(TenantBase):
    """
    An accommodation linked to a supplier.
    Contains room categories, seasons, and rates.
    """

    __tablename__ = "accommodations"

    # Relationship to supplier
    supplier_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("suppliers.id", ondelete="CASCADE"), nullable=False
    )

    # Relationship to location (for filtering by destination: Chiang Mai, Bangkok, etc.)
    location_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("locations.id", ondelete="SET NULL"), nullable=True
    )

    # Future: link to content article for detailed description
    content_id: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True
    )  # Will be FK to content_articles table when created

    # Payment terms override (optional - if NULL, use supplier.default_payment_terms)
    payment_terms_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("payment_terms.id", ondelete="SET NULL"), nullable=True
    )

    # Basic info
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    star_rating: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Classification
    # star_rating: Classification officielle (1-5 étoiles)
    # internal_priority: Priorité interne pour les vendeurs (1=primaire, 2=secondaire, etc.)
    internal_priority: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Notes internes pour les vendeurs (ex: "pas de twin", "lit supplémentaire = matelas au sol")
    internal_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Location
    address: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    city: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    country_code: Mapped[Optional[str]] = mapped_column(String(2), nullable=True)
    lat: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 7), nullable=True)
    lng: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 7), nullable=True)
    google_place_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # Check-in / Check-out
    check_in_time: Mapped[Optional[str]] = mapped_column(String(5), nullable=True)  # HH:MM
    check_out_time: Mapped[Optional[str]] = mapped_column(String(5), nullable=True)

    # Amenities (stored as JSON array)
    amenities: Mapped[Optional[List[str]]] = mapped_column(ARRAY(String), nullable=True)

    # Contact
    reservation_email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    reservation_phone: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    website_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    # Billing entity info (for logistics to know who to invoice)
    # If different from supplier.name, use billing_entity_name
    billing_entity_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    billing_entity_note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # External provider (for availability sync)
    external_provider: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)  # ratehawk, hotelbeds, amadeus, manual
    external_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # Status
    status: Mapped[str] = mapped_column(String(20), default="active")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    # Relationships
    tenant: Mapped["Tenant"] = relationship("Tenant", back_populates="accommodations", lazy="raise")
    supplier: Mapped["Supplier"] = relationship("Supplier", back_populates="accommodations", lazy="raise")
    location: Mapped[Optional["Location"]] = relationship("Location", back_populates="accommodations", lazy="raise")
    payment_terms: Mapped[Optional["PaymentTerms"]] = relationship("PaymentTerms", lazy="raise")
    room_categories: Mapped[List["RoomCategory"]] = relationship(
        "RoomCategory", back_populates="accommodation", cascade="all, delete-orphan", lazy="raise"
    )
    seasons: Mapped[List["AccommodationSeason"]] = relationship(
        "AccommodationSeason", back_populates="accommodation", cascade="all, delete-orphan", lazy="raise"
    )
    rates: Mapped[List["RoomRate"]] = relationship(
        "RoomRate", back_populates="accommodation", cascade="all, delete-orphan", lazy="raise"
    )
    early_bird_discounts: Mapped[List["EarlyBirdDiscount"]] = relationship(
        "EarlyBirdDiscount", back_populates="accommodation", cascade="all, delete-orphan", lazy="raise"
    )
    extras: Mapped[List["AccommodationExtra"]] = relationship(
        "AccommodationExtra", back_populates="accommodation", cascade="all, delete-orphan", lazy="raise"
    )
    photos: Mapped[List["AccommodationPhoto"]] = relationship(
        "AccommodationPhoto", back_populates="accommodation", cascade="all, delete-orphan", lazy="raise"
    )

    def __repr__(self) -> str:
        return f"<Accommodation(id={self.id}, name='{self.name}')>"


class RoomCategory(Base):
    """
    A room category within an accommodation (Standard, Suite, Deluxe, etc.)
    """

    __tablename__ = "room_categories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    accommodation_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("accommodations.id", ondelete="CASCADE"), nullable=False
    )

    # Basic info
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    code: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Occupancy
    min_occupancy: Mapped[int] = mapped_column(Integer, default=1)
    max_occupancy: Mapped[int] = mapped_column(Integer, default=2)
    max_adults: Mapped[int] = mapped_column(Integer, default=2)
    max_children: Mapped[int] = mapped_column(Integer, default=1)

    # Bed types available
    available_bed_types: Mapped[List[str]] = mapped_column(ARRAY(String), default=["DBL"])

    # Size
    size_sqm: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Amenities
    amenities: Mapped[Optional[List[str]]] = mapped_column(ARRAY(String), nullable=True)

    # Status & ordering
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    # Relationships
    accommodation: Mapped["Accommodation"] = relationship("Accommodation", back_populates="room_categories")
    rates: Mapped[List["RoomRate"]] = relationship(
        "RoomRate", back_populates="room_category", cascade="all, delete-orphan", passive_deletes=True
    )
    photos: Mapped[List["AccommodationPhoto"]] = relationship(
        "AccommodationPhoto", back_populates="room_category", cascade="all, delete-orphan", lazy="raise"
    )

    def __repr__(self) -> str:
        return f"<RoomCategory(id={self.id}, name='{self.name}', code='{self.code}')>"


class AccommodationSeason(Base):
    """
    A pricing season for an accommodation.
    """

    __tablename__ = "accommodation_seasons"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    accommodation_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("accommodations.id", ondelete="CASCADE"), nullable=False
    )

    # Basic info
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    code: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    original_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)  # Original name from contract before harmonization

    # Season type
    season_type: Mapped[str] = mapped_column(String(20), default="fixed")  # fixed, recurring, weekday

    # Dates (for fixed and recurring)
    start_date: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)  # YYYY-MM-DD or MM-DD
    end_date: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)

    # Days of week (for weekday type) - stored as comma-separated: "0,5,6" for Sun, Fri, Sat
    weekdays: Mapped[Optional[List[int]]] = mapped_column(ARRAY(Integer), nullable=True)

    # Year (null = recurring, can be "2024" or "2024-2025" for ranges)
    year: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)

    # Priority (higher wins in overlapping)
    priority: Mapped[int] = mapped_column(Integer, default=1)

    # Season level for pricing reference
    # low = basse saison, high = haute saison (default reference), peak = peak/fêtes
    season_level: Mapped[str] = mapped_column(String(10), default="high")

    # Status
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    # Relationships
    accommodation: Mapped["Accommodation"] = relationship("Accommodation", back_populates="seasons")
    rates: Mapped[List["RoomRate"]] = relationship("RoomRate", back_populates="season")

    def __repr__(self) -> str:
        return f"<AccommodationSeason(id={self.id}, name='{self.name}', code='{self.code}', level='{self.season_level}')>"


class RoomRate(Base):
    """
    A rate for a specific room category, season, bed type, and meal plan combination.
    """

    __tablename__ = "room_rates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    accommodation_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("accommodations.id", ondelete="CASCADE"), nullable=False
    )
    room_category_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("room_categories.id", ondelete="CASCADE"), nullable=False
    )
    season_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("accommodation_seasons.id", ondelete="SET NULL"), nullable=True
    )

    # Bed type
    bed_type: Mapped[str] = mapped_column(String(10), nullable=False, default="DBL")

    # Occupancy base
    base_occupancy: Mapped[int] = mapped_column(Integer, default=2)

    # Rate type
    rate_type: Mapped[str] = mapped_column(String(30), default="per_night")  # per_night, per_person_per_night

    # Cost
    cost: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="EUR")

    # Supplements
    single_supplement: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 2), nullable=True)
    extra_adult: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 2), nullable=True)
    extra_child: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 2), nullable=True)

    # Meal plan
    meal_plan: Mapped[str] = mapped_column(String(5), default="BB")  # RO, BB, HB, FB, AI

    # Validity
    valid_from: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    valid_to: Mapped[Optional[date]] = mapped_column(Date, nullable=True)

    # Notes
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Status
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    # Relationships
    accommodation: Mapped["Accommodation"] = relationship("Accommodation", back_populates="rates")
    room_category: Mapped["RoomCategory"] = relationship("RoomCategory", back_populates="rates")
    season: Mapped[Optional["AccommodationSeason"]] = relationship("AccommodationSeason", back_populates="rates")

    def __repr__(self) -> str:
        return f"<RoomRate(id={self.id}, room={self.room_category_id}, season={self.season_id}, cost={self.cost})>"


class EarlyBirdDiscount(Base):
    """
    Early booking discount for an accommodation.
    Ex: -15% if booked 60+ days in advance, -20% if 90+ days.
    """

    __tablename__ = "early_bird_discounts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    accommodation_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("accommodations.id", ondelete="CASCADE"), nullable=False
    )

    # Discount parameters
    name: Mapped[str] = mapped_column(String(100), nullable=False)  # "Early Bird 60 jours"
    days_in_advance: Mapped[int] = mapped_column(Integer, nullable=False)  # 60
    discount_percent: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)  # 15.00 for 15%

    # Optional: fixed amount discount instead of percentage
    discount_amount: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 2), nullable=True)
    discount_currency: Mapped[Optional[str]] = mapped_column(String(3), nullable=True)

    # Validity period (optional: only valid during certain dates)
    valid_from: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    valid_to: Mapped[Optional[date]] = mapped_column(Date, nullable=True)

    # Applicable to specific seasons only (optional)
    # If season_ids is set: discount applies ONLY to these seasons
    season_ids: Mapped[Optional[List[int]]] = mapped_column(ARRAY(Integer), nullable=True)
    # If excluded_season_ids is set: discount does NOT apply to these seasons (ex: Noël, Haute saison)
    excluded_season_ids: Mapped[Optional[List[int]]] = mapped_column(ARRAY(Integer), nullable=True)

    # Cumulative: can this be combined with other discounts?
    is_cumulative: Mapped[bool] = mapped_column(Boolean, default=False)

    # Priority: if multiple discounts apply, which one wins?
    priority: Mapped[int] = mapped_column(Integer, default=1)

    # Status
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    # Relationships
    accommodation: Mapped["Accommodation"] = relationship("Accommodation", back_populates="early_bird_discounts")

    def __repr__(self) -> str:
        return f"<EarlyBirdDiscount(id={self.id}, days={self.days_in_advance}, discount={self.discount_percent}%)>"


class AccommodationExtra(Base):
    """
    Optional extras/supplements for an accommodation.
    Ex: Breakfast, Airport transfer, Spa access, etc.

    These are additional services that can be added to a room rate.
    """

    __tablename__ = "accommodation_extras"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    accommodation_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("accommodations.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # Basic info
    name: Mapped[str] = mapped_column(String(100), nullable=False)  # "Petit-déjeuner", "Transfert aéroport"
    code: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)  # "BRK", "TRF"
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Extra type for categorization
    extra_type: Mapped[str] = mapped_column(String(30), default="meal")
    # meal = Breakfast, Lunch, Dinner, Half-board upgrade, Full-board upgrade
    # transfer = Airport transfer, Train station transfer
    # activity = Spa, Gym, Pool access
    # service = Laundry, Parking, WiFi, Late checkout
    # other = Custom extras

    # Pricing
    unit_cost: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="EUR")

    # Pricing model
    pricing_model: Mapped[str] = mapped_column(String(30), default="per_person_per_night")
    # per_person_per_night = 350 THB × nb_persons × nb_nights (typical for breakfast)
    # per_room_per_night = 500 THB × nb_nights (typical for parking)
    # per_person = 800 THB × nb_persons (typical for one-way transfer)
    # per_unit = 1200 THB × quantity (typical for round-trip transfer, spa session)
    # flat = 2000 THB once (typical for late checkout)

    # Optional: link to a season for seasonal pricing
    season_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("accommodation_seasons.id", ondelete="SET NULL"), nullable=True
    )

    # Validity period (optional)
    valid_from: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    valid_to: Mapped[Optional[date]] = mapped_column(Date, nullable=True)

    # Included by default in base rate?
    is_included: Mapped[bool] = mapped_column(Boolean, default=False)

    # Is this mandatory for all bookings?
    is_mandatory: Mapped[bool] = mapped_column(Boolean, default=False)

    # Display order
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    # Status
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    # Relationships
    accommodation: Mapped["Accommodation"] = relationship("Accommodation", back_populates="extras")
    season: Mapped[Optional["AccommodationSeason"]] = relationship("AccommodationSeason")

    def __repr__(self) -> str:
        return f"<AccommodationExtra(id={self.id}, name='{self.name}', cost={self.unit_cost} {self.currency})>"
