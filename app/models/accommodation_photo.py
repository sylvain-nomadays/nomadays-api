"""AccommodationPhoto model for storing photo metadata."""

from typing import Optional, TYPE_CHECKING
from datetime import datetime

from sqlalchemy import String, Boolean, Integer, ForeignKey, Text, BigInteger, DateTime
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import TenantBase

if TYPE_CHECKING:
    from app.models.accommodation import Accommodation, RoomCategory


class AccommodationPhoto(TenantBase):
    """
    Photo attached to an accommodation or a specific room category.

    - If room_category_id is NULL, the photo is at the hotel/accommodation level
    - If room_category_id is set, the photo is for that specific room type
    - is_main=True indicates the primary/hero photo for the accommodation or room
    """

    __tablename__ = "accommodation_photos"

    # Foreign keys
    accommodation_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("accommodations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    room_category_id: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        ForeignKey("room_categories.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Storage paths and URLs
    storage_path: Mapped[str] = mapped_column(String(500), nullable=False)
    url: Mapped[str] = mapped_column(String(1000), nullable=False)
    thumbnail_url: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)

    # Optimized variants (populated by image processing worker)
    url_avif: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    url_webp: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    url_medium: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)  # 800px
    url_large: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)   # 1920px
    srcset_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
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
    is_processed: Mapped[bool] = mapped_column(Boolean, default=False)
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

    # Relationships (lazy='raise' to prevent N+1 queries)
    accommodation: Mapped["Accommodation"] = relationship(
        "Accommodation",
        back_populates="photos",
        lazy="raise",
    )
    room_category: Mapped[Optional["RoomCategory"]] = relationship(
        "RoomCategory",
        back_populates="photos",
        lazy="raise",
    )

    def __repr__(self) -> str:
        return f"<AccommodationPhoto(id={self.id}, accommodation_id={self.accommodation_id}, is_main={self.is_main})>"
