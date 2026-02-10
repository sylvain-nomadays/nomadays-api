"""
SQLAlchemy models for Nomadays SaaS.
All models inherit from TenantBase for multi-tenant isolation.
"""

from app.models.base import Base, TenantBase, TimestampMixin
from app.models.tenant import Tenant
from app.models.user import User
from app.models.cost_nature import CostNature
from app.models.supplier import Supplier
from app.models.payment_terms import PaymentTerms
from app.models.location import Location
from app.models.accommodation import Accommodation, RoomCategory, AccommodationSeason, RoomRate
from app.models.accommodation_photo import AccommodationPhoto
from app.models.contract import Contract, ContractRate
from app.models.rate_catalog import RateCatalog
from app.models.dossier import Dossier
from app.models.partner_agency import PartnerAgency
from app.models.travel_theme import TravelTheme
from app.models.country_vat_rate import CountryVatRate
from app.models.trip import Trip, TripDay, TripPaxConfig, trip_themes
from app.models.trip_photo import TripPhoto
from app.models.trip_location import TripLocation, TripRoute
from app.models.trip_translation_cache import TripTranslationCache
from app.models.country_template import CountryTemplate
from app.models.formula import Formula
from app.models.condition import Condition, ConditionOption, TripCondition
from app.models.pax_category import PaxCategory
from app.models.item import Item, ItemSeason, ItemPriceTier
from app.models.booking import Booking, PaymentSchedule
from app.models.alert import AIAlert
from app.models.audit import AuditLog
from app.models.content import (
    ContentEntity,
    ContentTranslation,
    ContentPhoto,
    ContentTag,
    ContentRelation,
    content_entity_tags,
    ContentEntityType,
    ContentStatus,
    ContentRelationType,
    AIGenerationStatus,
)

__all__ = [
    "Base",
    "TenantBase",
    "TimestampMixin",
    "Tenant",
    "User",
    "CostNature",
    "Supplier",
    "PaymentTerms",
    "Location",
    "Accommodation",
    "RoomCategory",
    "AccommodationSeason",
    "RoomRate",
    "AccommodationPhoto",
    "Contract",
    "ContractRate",
    "RateCatalog",
    "Dossier",
    "PartnerAgency",
    "TravelTheme",
    "CountryVatRate",
    "Trip",
    "TripDay",
    "TripPaxConfig",
    "trip_themes",
    "TripPhoto",
    "TripLocation",
    "TripRoute",
    "TripTranslationCache",
    "CountryTemplate",
    "Formula",
    "Condition",
    "ConditionOption",
    "TripCondition",
    "PaxCategory",
    "Item",
    "ItemSeason",
    "ItemPriceTier",
    "Booking",
    "PaymentSchedule",
    "AIAlert",
    "AuditLog",
    # Content Article system
    "ContentEntity",
    "ContentTranslation",
    "ContentPhoto",
    "ContentTag",
    "ContentRelation",
    "content_entity_tags",
    "ContentEntityType",
    "ContentStatus",
    "ContentRelationType",
    "AIGenerationStatus",
]
