"""
Location model - represents geographical locations for filtering and organization.
Locations are used to categorize accommodations, activities, etc. by destination.
"""

from decimal import Decimal
from typing import Optional, List, TYPE_CHECKING

from sqlalchemy import String, Boolean, DECIMAL, BigInteger, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import TenantBase

if TYPE_CHECKING:
    from app.models.accommodation import Accommodation
    from app.models.location_photo import LocationPhoto


class Location(TenantBase):
    """
    A geographical location used for filtering and organizing products.
    Examples: Chiang Mai, Bangkok, Marrakech, Atlas Mountains, etc.
    """

    __tablename__ = "locations"

    # Identity
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, index=True)

    # Type of location
    location_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="city",
    )  # city, region, country, area, neighborhood

    # Hierarchy (optional)
    parent_id: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        ForeignKey("locations.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Geographic info
    country_code: Mapped[Optional[str]] = mapped_column(String(2), nullable=True)

    # Coordinates (center point for the location)
    lat: Mapped[Optional[Decimal]] = mapped_column(DECIMAL(10, 7), nullable=True)
    lng: Mapped[Optional[Decimal]] = mapped_column(DECIMAL(10, 7), nullable=True)

    # Google Place ID for the location
    google_place_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # Description
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Future: link to content article for destination page
    content_id: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        nullable=True,
    )  # Will be FK to content_articles table when created

    # Display order
    sort_order: Mapped[int] = mapped_column(default=0)

    # Status
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    # Relationships
    parent: Mapped[Optional["Location"]] = relationship(
        "Location",
        remote_side="Location.id",
        foreign_keys=[parent_id],
        lazy="raise",
    )
    children: Mapped[List["Location"]] = relationship(
        "Location",
        back_populates="parent",
        foreign_keys=[parent_id],
        lazy="raise",
    )
    accommodations: Mapped[List["Accommodation"]] = relationship(
        "Accommodation",
        back_populates="location",
        lazy="raise",
    )
    photos: Mapped[List["LocationPhoto"]] = relationship(
        "LocationPhoto",
        back_populates="location",
        lazy="raise",
        cascade="all, delete-orphan",
        order_by="LocationPhoto.sort_order",
    )

    def __repr__(self) -> str:
        return f"<Location(id={self.id}, name='{self.name}', type='{self.location_type}')>"
