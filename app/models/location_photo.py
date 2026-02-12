"""LocationPhoto model for storing photo metadata for locations."""

from typing import Optional, TYPE_CHECKING
from datetime import datetime

from sqlalchemy import String, Boolean, Integer, ForeignKey, Text, BigInteger, DateTime
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import TenantBase

if TYPE_CHECKING:
    from app.models.location import Location


class LocationPhoto(TenantBase):
    """
    Photo attached to a location (destination).

    Photos are ordered by sort_order and distributed across trip days
    that reference this location. The first photo (sort_order=0) illustrates
    the first day at this location, the second photo the second day, etc.
    """

    __tablename__ = "location_photos"

    # Foreign key
    location_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("locations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Storage paths and URLs
    storage_path: Mapped[str] = mapped_column(String(500), nullable=False)
    url: Mapped[str] = mapped_column(String(1000), nullable=False)
    thumbnail_url: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)

    # Optimized variants
    url_avif: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    url_webp: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    url_medium: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)  # 800px
    url_large: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)   # 1920px
    lqip_data_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # Base64 blur

    # Metadata
    original_filename: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    file_size: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # Bytes
    mime_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    width: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    height: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    caption: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    alt_text: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # Flags
    is_main: Mapped[bool] = mapped_column(Boolean, default=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    # Timestamps
    created_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    updated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # Relationships
    location: Mapped["Location"] = relationship(
        "Location",
        back_populates="photos",
        lazy="raise",
    )

    def __repr__(self) -> str:
        return f"<LocationPhoto(id={self.id}, location_id={self.location_id}, is_main={self.is_main})>"
