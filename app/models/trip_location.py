"""
Trip Location models - geographic waypoints and routes.
Supports geocoding via Google Maps API.
"""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Optional, List, TYPE_CHECKING

from sqlalchemy import BigInteger, String, Integer, Text, DECIMAL, DateTime, ForeignKey, Enum as SQLEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import TenantBase

if TYPE_CHECKING:
    from app.models.trip import Trip


class TripLocation(TenantBase):
    """
    A geographic location/waypoint within a trip.
    Stores coordinates from Google Maps geocoding.
    """

    __tablename__ = "trip_locations"

    # Trip relationship
    trip_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("trips.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Location info
    name: Mapped[str] = mapped_column(String(255), nullable=False)  # "Chiang Mai"
    place_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)  # Google Place ID

    # Coordinates (from geocoding)
    lat: Mapped[Optional[Decimal]] = mapped_column(DECIMAL(10, 7), nullable=True)
    lng: Mapped[Optional[Decimal]] = mapped_column(DECIMAL(10, 7), nullable=True)

    # Additional info
    address: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # Formatted address
    country_code: Mapped[Optional[str]] = mapped_column(String(2), nullable=True)  # ISO country code
    region: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)  # Province/state

    # Trip context
    day_number: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    location_type: Mapped[str] = mapped_column(
        SQLEnum("overnight", "waypoint", "poi", "activity", name="location_type_enum"),
        default="overnight",
        nullable=False,
    )
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Ordering
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    # Relationships
    trip: Mapped["Trip"] = relationship("Trip", back_populates="locations")
    routes_from: Mapped[List["TripRoute"]] = relationship(
        "TripRoute",
        foreign_keys="TripRoute.from_location_id",
        back_populates="from_location",
        cascade="all, delete-orphan",
    )
    routes_to: Mapped[List["TripRoute"]] = relationship(
        "TripRoute",
        foreign_keys="TripRoute.to_location_id",
        back_populates="to_location",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<TripLocation(id={self.id}, name='{self.name}', day={self.day_number})>"

    @property
    def has_coordinates(self) -> bool:
        """Check if this location has valid coordinates."""
        return self.lat is not None and self.lng is not None

    def to_marker_dict(self) -> dict:
        """Return dict suitable for map marker."""
        return {
            "id": self.id,
            "name": self.name,
            "lat": float(self.lat) if self.lat else None,
            "lng": float(self.lng) if self.lng else None,
            "day_number": self.day_number,
            "type": self.location_type,
        }


class TripRoute(TenantBase):
    """
    A route between two locations.
    Stores distance, duration, and polyline from Google Directions API.
    """

    __tablename__ = "trip_routes"

    # Trip relationship
    trip_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("trips.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Route endpoints
    from_location_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("trip_locations.id", ondelete="CASCADE"),
        nullable=False,
    )
    to_location_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("trip_locations.id", ondelete="CASCADE"),
        nullable=False,
    )

    # Route details
    distance_km: Mapped[Optional[Decimal]] = mapped_column(DECIMAL(10, 2), nullable=True)
    duration_minutes: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    polyline: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # Encoded polyline
    travel_mode: Mapped[str] = mapped_column(
        SQLEnum("driving", "walking", "transit", "flight", "boat", name="travel_mode_enum"),
        default="driving",
        nullable=False,
    )

    # Cache metadata
    calculated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
    )

    # Relationships
    from_location: Mapped["TripLocation"] = relationship(
        "TripLocation",
        foreign_keys=[from_location_id],
        back_populates="routes_from",
    )
    to_location: Mapped["TripLocation"] = relationship(
        "TripLocation",
        foreign_keys=[to_location_id],
        back_populates="routes_to",
    )

    def __repr__(self) -> str:
        return f"<TripRoute(from={self.from_location_id}, to={self.to_location_id}, {self.distance_km}km)>"

    @property
    def duration_formatted(self) -> str:
        """Return duration in human-readable format."""
        if not self.duration_minutes:
            return ""
        hours = self.duration_minutes // 60
        minutes = self.duration_minutes % 60
        if hours > 0:
            return f"{hours}h{minutes:02d}"
        return f"{minutes}min"

    def to_route_dict(self) -> dict:
        """Return dict suitable for map route display."""
        return {
            "from_id": self.from_location_id,
            "to_id": self.to_location_id,
            "distance_km": float(self.distance_km) if self.distance_km else None,
            "duration_minutes": self.duration_minutes,
            "duration_formatted": self.duration_formatted,
            "polyline": self.polyline,
            "travel_mode": self.travel_mode,
        }
