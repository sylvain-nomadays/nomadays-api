"""
Trip Translation Cache model.
Stores cached translations for quick preview without regenerating.
"""

from datetime import datetime
from typing import Optional, List, Any

from sqlalchemy import String, Text, Boolean, DateTime, ForeignKey, BigInteger, Index
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import TenantBase


class TripTranslationCache(TenantBase):
    """
    Cached translation of a trip for quick preview.

    When a user wants to preview a circuit in another language,
    we store the translation here to avoid regenerating it every time.

    If the source trip is modified, the cache is marked as stale.
    """

    __tablename__ = "trip_translation_caches"

    # Reference to the source trip
    trip_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("trips.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Target language code (en, es, de, it, pt, nl, ru, zh, ja)
    language: Mapped[str] = mapped_column(String(5), nullable=False)

    # Translated content
    name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    description_short: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    highlights: Mapped[Optional[List[Any]]] = mapped_column(JSONB, nullable=True)
    inclusions: Mapped[Optional[List[Any]]] = mapped_column(JSONB, nullable=True)
    exclusions: Mapped[Optional[List[Any]]] = mapped_column(JSONB, nullable=True)

    # Info fields
    info_general: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    info_formalities: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    info_booking_conditions: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    info_cancellation_policy: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    info_additional: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Translated days (JSON array)
    # [{day_number: int, title: str, description: str}]
    translated_days: Mapped[Optional[List[Any]]] = mapped_column(JSONB, nullable=True)

    # Cache metadata
    cached_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
    )

    # Hash of the source content to detect changes
    source_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    # Whether the cache is outdated (source was modified)
    is_stale: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Relationship to trip
    trip: Mapped["Trip"] = relationship("Trip", back_populates="translation_caches")

    __table_args__ = (
        # Unique constraint: one cache per trip per language
        Index("ix_trip_translation_caches_trip_language", "trip_id", "language", unique=True),
        Index("ix_trip_translation_caches_is_stale", "trip_id", "is_stale"),
    )

    def __repr__(self) -> str:
        return f"<TripTranslationCache trip_id={self.trip_id} language={self.language} stale={self.is_stale}>"
