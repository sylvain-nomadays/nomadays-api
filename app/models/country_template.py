"""
Country Template model - default templates for inclusions, exclusions, etc.
Templates can be global (country_code=NULL) or country-specific.
"""

import uuid
from typing import Optional, TYPE_CHECKING

from sqlalchemy import BigInteger, String, Integer, Boolean, ForeignKey, Enum as SQLEnum
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import TenantBase


class CountryTemplate(TenantBase):
    """
    Default template for inclusions, exclusions, formalities, etc.
    Can be global (no country) or country-specific.
    """

    __tablename__ = "country_templates"

    # Country (NULL = global default)
    country_code: Mapped[Optional[str]] = mapped_column(String(2), nullable=True, index=True)
    country_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    # Template type
    template_type: Mapped[str] = mapped_column(
        SQLEnum(
            "inclusions",
            "exclusions",
            "formalities",
            "booking_conditions",
            "cancellation_policy",
            "general_info",
            name="template_type_enum"
        ),
        nullable=False,
    )

    # Content (JSONB for flexibility)
    # For inclusions/exclusions: [{ "text": "...", "default": true }]
    # For text templates: { "content": "...", "variables": ["destination", "duration"] }
    content: Mapped[dict] = mapped_column(JSONB, nullable=False)

    # Metadata
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    def __repr__(self) -> str:
        country = self.country_code or "GLOBAL"
        return f"<CountryTemplate(type='{self.template_type}', country='{country}')>"

    @classmethod
    def get_template_for_country(
        cls,
        db,
        tenant_id: uuid.UUID,
        template_type: str,
        country_code: Optional[str] = None,
    ):
        """
        Get template for a specific country, falling back to global if not found.
        """
        from sqlalchemy import select, or_

        # First try country-specific, then global
        query = (
            select(cls)
            .where(cls.tenant_id == tenant_id)
            .where(cls.template_type == template_type)
            .where(cls.is_active == True)
            .where(
                or_(
                    cls.country_code == country_code,
                    cls.country_code.is_(None),
                )
            )
            .order_by(
                # Prefer country-specific over global
                cls.country_code.is_(None),
                cls.sort_order,
            )
        )
        return query


# Default templates for seeding
DEFAULT_INCLUSIONS = [
    {"text": "Hébergement selon le programme", "default": True},
    {"text": "Petits-déjeuners", "default": True},
    {"text": "Transferts privés", "default": True},
    {"text": "Guide francophone", "default": True},
    {"text": "Activités mentionnées au programme", "default": True},
    {"text": "Entrées sur les sites", "default": True},
]

DEFAULT_EXCLUSIONS = [
    {"text": "Vols internationaux", "default": True},
    {"text": "Assurance voyage", "default": True},
    {"text": "Repas non mentionnés", "default": True},
    {"text": "Pourboires", "default": True},
    {"text": "Dépenses personnelles", "default": True},
    {"text": "Frais de visa", "default": False},
]

# Country-specific formalities templates
FORMALITIES_BY_COUNTRY = {
    "TH": """**Passeport** : Valide 6 mois après la date de retour.

**Visa** : Exemption de visa pour les séjours touristiques de moins de 30 jours pour les ressortissants français.

**Santé** : Aucune vaccination obligatoire. Vaccinations universelles à jour recommandées.

**Décalage horaire** : +5h en été, +6h en hiver par rapport à la France.""",

    "VN": """**Passeport** : Valide 6 mois après la date de retour.

**Visa** : Exemption de visa pour les séjours de moins de 45 jours pour les ressortissants français (depuis août 2023).

**Santé** : Aucune vaccination obligatoire. Traitement antipaludique conseillé pour certaines régions.

**Décalage horaire** : +5h en été, +6h en hiver par rapport à la France.""",

    "KH": """**Passeport** : Valide 6 mois après la date de retour.

**Visa** : Visa obligatoire. E-visa disponible sur le site officiel du gouvernement cambodgien.

**Santé** : Aucune vaccination obligatoire. Traitement antipaludique recommandé.

**Décalage horaire** : +5h en été, +6h en hiver par rapport à la France.""",

    "MA": """**Passeport** : Valide pendant toute la durée du séjour.

**Visa** : Aucun visa requis pour les séjours de moins de 90 jours pour les ressortissants français.

**Santé** : Aucune vaccination obligatoire.

**Décalage horaire** : -1h en été, 0h en hiver par rapport à la France.""",
}
