"""
TravelTheme model - fixed travel themes/categories.
12 themes are pre-defined and seeded per tenant. Not editable by tenants.
Examples: Culture & Histoire, Nature & Faune, Aventure & Trek, etc.
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
    Fixed list of 12 themes, seeded per tenant. Not user-editable.
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


# Fixed 12 travel themes — not editable by tenants
DEFAULT_TRAVEL_THEMES = [
    {"code": "culture_histoire", "label": "Culture & Histoire", "label_en": "Culture & History", "icon": "Bank", "color": "#B45309", "description": "Temples, monuments, traditions, artisanat"},
    {"code": "nature_faune", "label": "Nature & Faune", "label_en": "Nature & Wildlife", "icon": "Tree", "color": "#16A34A", "description": "Safari, parcs nationaux, faune & flore"},
    {"code": "aventure_trek", "label": "Aventure & Trek", "label_en": "Adventure & Trek", "icon": "Mountains", "color": "#DC2626", "description": "Randonnée, alpinisme, sports outdoor"},
    {"code": "plages_iles", "label": "Plages & Îles", "label_en": "Beaches & Islands", "icon": "Island", "color": "#0EA5E9", "description": "Balnéaire, snorkeling, farniente"},
    {"code": "famille", "label": "Famille", "label_en": "Family", "icon": "UsersThree", "color": "#F59E0B", "description": "Circuits adaptés enfants"},
    {"code": "luxe_bien_etre", "label": "Luxe & Bien-être", "label_en": "Luxury & Wellness", "icon": "Sparkle", "color": "#7C3AED", "description": "Spas, hôtels premium, relaxation"},
    {"code": "gastronomie_vins", "label": "Gastronomie & Vins", "label_en": "Gastronomy & Wines", "icon": "Wine", "color": "#BE185D", "description": "Food tours, cours de cuisine, vignobles"},
    {"code": "hors_sentiers", "label": "Hors des sentiers battus", "label_en": "Off the beaten track", "icon": "Compass", "color": "#059669", "description": "Immersion locale, destinations méconnues"},
    {"code": "road_trip", "label": "Road Trip", "label_en": "Road Trip", "icon": "Jeep", "color": "#EA580C", "description": "Autotour, liberté, itinérant"},
    {"code": "croisiere_nautique", "label": "Croisière & Nautique", "label_en": "Cruise & Nautical", "icon": "Boat", "color": "#0284C7", "description": "Croisière, voile, plongée"},
    {"code": "spiritualite", "label": "Spiritualité & Ressourcement", "label_en": "Spirituality & Retreat", "icon": "Flower", "color": "#8B5CF6", "description": "Yoga, méditation, retraites, pèlerinage"},
    {"code": "evenements_festivals", "label": "Événements & Festivals", "label_en": "Events & Festivals", "icon": "Confetti", "color": "#E11D48", "description": "Carnavals, fêtes locales"},
]
