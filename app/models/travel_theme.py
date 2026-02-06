"""
TravelTheme model - configurable travel themes/categories per tenant.
Examples: hiking, equestrian, family, luxury, adventure, culture, etc.
"""

from typing import Optional, List, TYPE_CHECKING

from sqlalchemy import String, Boolean, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import TenantBase

if TYPE_CHECKING:
    from app.models.trip import Trip


class TravelTheme(TenantBase):
    """
    A travel theme/category that can be assigned to trips.
    Configurable per tenant.
    """

    __tablename__ = "travel_themes"

    # Theme identity
    code: Mapped[str] = mapped_column(String(50), nullable=False)
    label: Mapped[str] = mapped_column(String(255), nullable=False)
    label_en: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # Visual
    icon: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)  # Icon name (e.g., "hiking", "horse")
    color: Mapped[Optional[str]] = mapped_column(String(7), nullable=True)  # Hex color (e.g., "#FF5733")

    # Description
    description: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    # Status and ordering
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    # Relationships (many-to-many via trip_themes)
    trips: Mapped[List["Trip"]] = relationship(
        "Trip",
        secondary="trip_themes",
        back_populates="themes",
    )

    def __repr__(self) -> str:
        return f"<TravelTheme(id={self.id}, code='{self.code}', label='{self.label}')>"


# Default themes to seed for new tenants
DEFAULT_TRAVEL_THEMES = [
    {"code": "randonnee", "label": "Randonnée", "label_en": "Hiking", "icon": "hiking"},
    {"code": "equestre", "label": "Équestre", "label_en": "Equestrian", "icon": "horse"},
    {"code": "famille", "label": "Famille", "label_en": "Family", "icon": "users"},
    {"code": "luxe", "label": "Luxe", "label_en": "Luxury", "icon": "star"},
    {"code": "aventure", "label": "Aventure", "label_en": "Adventure", "icon": "mountain"},
    {"code": "culture", "label": "Culture", "label_en": "Culture", "icon": "landmark"},
    {"code": "plage", "label": "Plage", "label_en": "Beach", "icon": "umbrella-beach"},
    {"code": "gastronomie", "label": "Gastronomie", "label_en": "Gastronomy", "icon": "utensils"},
    {"code": "bien_etre", "label": "Bien-être", "label_en": "Wellness", "icon": "spa"},
    {"code": "nature", "label": "Nature & Faune", "label_en": "Nature & Wildlife", "icon": "leaf"},
    {"code": "photo", "label": "Photo", "label_en": "Photography", "icon": "camera"},
    {"code": "sport", "label": "Sport", "label_en": "Sports", "icon": "person-running"},
]
