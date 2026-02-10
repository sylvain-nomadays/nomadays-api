"""
API endpoints for accommodations, room categories, seasons, and rates.
"""

from typing import List, Optional
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, File, UploadFile, Form
from pydantic import BaseModel, Field
from datetime import datetime
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_db, get_current_user, get_current_tenant
from app.models import Accommodation, RoomCategory, AccommodationSeason, RoomRate, Supplier, Tenant, User, AccommodationPhoto
from app.models.accommodation import EarlyBirdDiscount, AccommodationExtra
from app.services.storage import upload_to_supabase, delete_from_supabase, get_mime_type, get_supabase_client, BUCKET_NAME
from app.services.image_processor import process_image_minimal, get_image_dimensions


router = APIRouter(prefix="/accommodations", tags=["Accommodations"])


# ============================================================================
# Schemas
# ============================================================================

class RoomCategoryResponse(BaseModel):
    id: int
    accommodation_id: int
    name: str
    code: Optional[str] = None
    description: Optional[str] = None
    min_occupancy: int = 1
    max_occupancy: int = 2
    max_adults: int = 2
    max_children: int = 1
    available_bed_types: List[str] = ["DBL"]
    size_sqm: Optional[int] = None
    amenities: Optional[List[str]] = None
    is_active: bool = True
    sort_order: int = 0

    class Config:
        from_attributes = True


class AccommodationSeasonResponse(BaseModel):
    id: int
    accommodation_id: int
    name: str
    code: Optional[str] = None
    season_type: str = "fixed"
    season_level: str = "high"  # low, high (default reference), peak
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    weekdays: Optional[List[int]] = None
    year: Optional[str] = None  # Can be "2024" or "2024-2025"
    priority: int = 1
    is_active: bool = True
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    class Config:
        from_attributes = True


class RoomRateResponse(BaseModel):
    id: int
    accommodation_id: int
    room_category_id: int
    season_id: Optional[int] = None
    bed_type: str = "DBL"
    base_occupancy: int = 2
    rate_type: str = "per_night"
    cost: float
    currency: str = "EUR"
    single_supplement: Optional[float] = None
    extra_adult: Optional[float] = None
    extra_child: Optional[float] = None
    meal_plan: str = "BB"
    valid_from: Optional[str] = None
    valid_to: Optional[str] = None
    notes: Optional[str] = None
    is_active: bool = True

    class Config:
        from_attributes = True


# ============================================================================
# Extras Schemas
# ============================================================================

class AccommodationExtraResponse(BaseModel):
    """Response schema for accommodation extras/supplements."""
    id: int
    accommodation_id: int
    name: str
    code: Optional[str] = None
    description: Optional[str] = None
    extra_type: str = "meal"
    unit_cost: float
    currency: str = "EUR"
    pricing_model: str = "per_person_per_night"
    season_id: Optional[int] = None
    valid_from: Optional[str] = None
    valid_to: Optional[str] = None
    is_included: bool = False
    is_mandatory: bool = False
    sort_order: int = 0
    is_active: bool = True

    class Config:
        from_attributes = True


class CreateAccommodationExtraRequest(BaseModel):
    """Request schema to create an extra."""
    name: str
    code: Optional[str] = None
    description: Optional[str] = None
    extra_type: str = "meal"  # meal, transfer, activity, service, other
    unit_cost: float
    currency: str = "EUR"
    pricing_model: str = "per_person_per_night"
    # per_person_per_night, per_room_per_night, per_person, per_unit, flat
    season_id: Optional[int] = None
    valid_from: Optional[str] = None
    valid_to: Optional[str] = None
    is_included: bool = False
    is_mandatory: bool = False
    sort_order: int = 0


class UpdateAccommodationExtraRequest(BaseModel):
    """Request schema to update an extra."""
    name: Optional[str] = None
    code: Optional[str] = None
    description: Optional[str] = None
    extra_type: Optional[str] = None
    unit_cost: Optional[float] = None
    currency: Optional[str] = None
    pricing_model: Optional[str] = None
    season_id: Optional[int] = None
    valid_from: Optional[str] = None
    valid_to: Optional[str] = None
    is_included: Optional[bool] = None
    is_mandatory: Optional[bool] = None
    sort_order: Optional[int] = None
    is_active: Optional[bool] = None


class PhotoSummary(BaseModel):
    """Compact photo schema for inclusion in AccommodationResponse."""
    id: int
    accommodation_id: int
    room_category_id: Optional[int] = None
    url: str
    thumbnail_url: Optional[str] = None
    url_medium: Optional[str] = None
    is_main: bool = False
    sort_order: int = 0

    class Config:
        from_attributes = True


class AccommodationResponse(BaseModel):
    id: int
    tenant_id: str
    supplier_id: int
    name: str
    description: Optional[str] = None
    star_rating: Optional[int] = None
    internal_priority: Optional[int] = None  # Priorité interne (1=primaire, 2=secondaire, etc.)
    internal_notes: Optional[str] = None  # Notes internes pour les vendeurs
    # Location (lien vers table locations pour filtrage)
    location_id: Optional[int] = None
    # Adresse Google Maps (géolocalisation précise)
    address: Optional[str] = None
    city: Optional[str] = None
    country_code: Optional[str] = None
    lat: Optional[float] = None
    lng: Optional[float] = None
    google_place_id: Optional[str] = None
    check_in_time: Optional[str] = None
    check_out_time: Optional[str] = None
    amenities: Optional[List[str]] = None
    reservation_email: Optional[str] = None
    reservation_phone: Optional[str] = None
    website_url: Optional[str] = None
    # Billing entity info (for logistics)
    billing_entity_name: Optional[str] = None  # Alternative name if different from supplier
    billing_entity_note: Optional[str] = None  # Note for logistics
    external_provider: Optional[str] = None
    external_id: Optional[str] = None
    # Lien futur vers article de contenu
    content_id: Optional[int] = None
    # Payment terms override (optional - if NULL, use supplier.default_payment_terms)
    payment_terms_id: Optional[int] = None
    status: str = "active"
    is_active: bool = True
    room_categories: List[RoomCategoryResponse] = []
    seasons: List[AccommodationSeasonResponse] = []
    photos: List[PhotoSummary] = []
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    class Config:
        from_attributes = True


class CreateAccommodationRequest(BaseModel):
    supplier_id: int
    name: str
    description: Optional[str] = None
    star_rating: Optional[int] = None
    internal_priority: Optional[int] = None
    internal_notes: Optional[str] = None  # Notes internes pour les vendeurs
    # Location (lien vers table locations pour filtrage)
    location_id: Optional[int] = None
    # Adresse Google Maps
    address: Optional[str] = None
    city: Optional[str] = None
    country_code: Optional[str] = None
    lat: Optional[float] = None
    lng: Optional[float] = None
    google_place_id: Optional[str] = None
    check_in_time: Optional[str] = None
    check_out_time: Optional[str] = None
    amenities: Optional[List[str]] = None
    reservation_email: Optional[str] = None
    reservation_phone: Optional[str] = None
    website_url: Optional[str] = None
    # Billing entity info (for logistics)
    billing_entity_name: Optional[str] = None
    billing_entity_note: Optional[str] = None
    external_provider: Optional[str] = None
    external_id: Optional[str] = None
    # Lien futur vers article de contenu
    content_id: Optional[int] = None
    # Payment terms override (optional)
    payment_terms_id: Optional[int] = None


class UpdateAccommodationRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    star_rating: Optional[int] = None
    internal_priority: Optional[int] = None
    internal_notes: Optional[str] = None  # Notes internes pour les vendeurs
    # Location (lien vers table locations pour filtrage)
    location_id: Optional[int] = None
    # Adresse Google Maps
    address: Optional[str] = None
    city: Optional[str] = None
    country_code: Optional[str] = None
    lat: Optional[float] = None
    lng: Optional[float] = None
    google_place_id: Optional[str] = None
    check_in_time: Optional[str] = None
    check_out_time: Optional[str] = None
    amenities: Optional[List[str]] = None
    reservation_email: Optional[str] = None
    reservation_phone: Optional[str] = None
    website_url: Optional[str] = None
    # Billing entity info (for logistics)
    billing_entity_name: Optional[str] = None
    billing_entity_note: Optional[str] = None
    external_provider: Optional[str] = None
    external_id: Optional[str] = None
    # Lien futur vers article de contenu
    content_id: Optional[int] = None
    # Payment terms override (optional)
    payment_terms_id: Optional[int] = None
    status: Optional[str] = None
    is_active: Optional[bool] = None


class CreateRoomCategoryRequest(BaseModel):
    name: str
    code: Optional[str] = None
    description: Optional[str] = None
    min_occupancy: int = 1
    max_occupancy: int = 2
    max_adults: int = 2
    max_children: int = 1
    available_bed_types: List[str] = Field(default=["DBL"])
    size_sqm: Optional[int] = None
    amenities: Optional[List[str]] = None


class UpdateRoomCategoryRequest(BaseModel):
    name: Optional[str] = None
    code: Optional[str] = None
    description: Optional[str] = None
    min_occupancy: Optional[int] = None
    max_occupancy: Optional[int] = None
    max_adults: Optional[int] = None
    max_children: Optional[int] = None
    available_bed_types: Optional[List[str]] = None
    size_sqm: Optional[int] = None
    amenities: Optional[List[str]] = None
    is_active: Optional[bool] = None
    sort_order: Optional[int] = None


class CreateSeasonRequest(BaseModel):
    name: str
    code: Optional[str] = None
    season_type: str = "fixed"
    season_level: str = "high"  # low, high (default reference), peak
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    weekdays: Optional[List[int]] = None
    year: Optional[str] = None  # Can be "2024" or "2024-2025"
    priority: int = 1


class UpdateSeasonRequest(BaseModel):
    name: Optional[str] = None
    code: Optional[str] = None
    season_type: Optional[str] = None
    season_level: Optional[str] = None  # low, high, peak
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    weekdays: Optional[List[int]] = None
    year: Optional[str] = None
    priority: Optional[int] = None
    is_active: Optional[bool] = None


class CreateRoomRateRequest(BaseModel):
    room_category_id: int
    season_id: Optional[int] = None
    bed_type: str = "DBL"
    base_occupancy: int = 2
    rate_type: str = "per_night"
    cost: float
    currency: str = "EUR"
    single_supplement: Optional[float] = None
    extra_adult: Optional[float] = None
    extra_child: Optional[float] = None
    meal_plan: str = "BB"
    valid_from: Optional[str] = None
    valid_to: Optional[str] = None
    notes: Optional[str] = None


class UpdateRoomRateRequest(BaseModel):
    season_id: Optional[int] = None
    bed_type: Optional[str] = None
    base_occupancy: Optional[int] = None
    rate_type: Optional[str] = None
    cost: Optional[float] = None
    currency: Optional[str] = None
    single_supplement: Optional[float] = None
    extra_adult: Optional[float] = None
    extra_child: Optional[float] = None
    meal_plan: Optional[str] = None
    valid_from: Optional[str] = None
    valid_to: Optional[str] = None
    notes: Optional[str] = None
    is_active: Optional[bool] = None


class BulkRatesRequest(BaseModel):
    rates: List[CreateRoomRateRequest]


# Early Bird Discount Schemas
class EarlyBirdDiscountResponse(BaseModel):
    id: int
    accommodation_id: int
    name: str
    days_in_advance: int
    discount_percent: float
    discount_amount: Optional[float] = None
    discount_currency: Optional[str] = None
    valid_from: Optional[str] = None
    valid_to: Optional[str] = None
    season_ids: Optional[List[int]] = None
    excluded_season_ids: Optional[List[int]] = None
    is_cumulative: bool = False
    priority: int = 1
    is_active: bool = True

    class Config:
        from_attributes = True


class CreateEarlyBirdDiscountRequest(BaseModel):
    name: str
    days_in_advance: int
    discount_percent: float
    discount_amount: Optional[float] = None
    discount_currency: Optional[str] = None
    valid_from: Optional[str] = None
    valid_to: Optional[str] = None
    season_ids: Optional[List[int]] = None
    excluded_season_ids: Optional[List[int]] = None
    is_cumulative: bool = False
    priority: int = 1


class UpdateEarlyBirdDiscountRequest(BaseModel):
    name: Optional[str] = None
    days_in_advance: Optional[int] = None
    discount_percent: Optional[float] = None
    discount_amount: Optional[float] = None
    discount_currency: Optional[str] = None
    valid_from: Optional[str] = None
    valid_to: Optional[str] = None
    season_ids: Optional[List[int]] = None
    excluded_season_ids: Optional[List[int]] = None
    is_cumulative: Optional[bool] = None
    priority: Optional[int] = None
    is_active: Optional[bool] = None


# ============================================================================
# Helper Functions
# ============================================================================

def photo_to_summary(photo: "AccommodationPhoto") -> dict:
    """Convert AccommodationPhoto model to compact summary dict."""
    return {
        "id": photo.id,
        "accommodation_id": photo.accommodation_id,
        "room_category_id": photo.room_category_id,
        "url": photo.url,
        "thumbnail_url": photo.thumbnail_url,
        "url_medium": photo.url_medium,
        "is_main": photo.is_main,
        "sort_order": photo.sort_order,
    }


def _safe_photos(acc: "Accommodation") -> list:
    """Safely get photos — returns [] if photos weren't eagerly loaded."""
    try:
        return [photo_to_summary(p) for p in (acc.photos or [])]
    except Exception:
        return []


def accommodation_to_response(acc: Accommodation) -> dict:
    """Convert Accommodation model to response dict."""
    return {
        "id": acc.id,
        "tenant_id": str(acc.tenant_id),
        "supplier_id": acc.supplier_id,
        "name": acc.name,
        "description": acc.description,
        "star_rating": acc.star_rating,
        "internal_priority": acc.internal_priority,
        "internal_notes": acc.internal_notes,
        # Location (lien vers table locations pour filtrage)
        "location_id": acc.location_id,
        # Adresse Google Maps (géolocalisation précise)
        "address": acc.address,
        "city": acc.city,
        "country_code": acc.country_code,
        "lat": float(acc.lat) if acc.lat else None,
        "lng": float(acc.lng) if acc.lng else None,
        "google_place_id": acc.google_place_id,
        "check_in_time": acc.check_in_time,
        "check_out_time": acc.check_out_time,
        "amenities": acc.amenities or [],
        "reservation_email": acc.reservation_email,
        "reservation_phone": acc.reservation_phone,
        "website_url": acc.website_url,
        # Billing entity info (for logistics)
        "billing_entity_name": getattr(acc, 'billing_entity_name', None),
        "billing_entity_note": getattr(acc, 'billing_entity_note', None),
        "external_provider": acc.external_provider,
        "external_id": acc.external_id,
        # Lien futur vers article de contenu
        "content_id": acc.content_id,
        # Payment terms override (optional - if NULL, use supplier.default_payment_terms)
        "payment_terms_id": getattr(acc, 'payment_terms_id', None),
        "status": acc.status,
        "is_active": acc.is_active,
        "room_categories": [category_to_response(c) for c in (acc.room_categories or [])],
        "seasons": [season_to_response(s) for s in (acc.seasons or [])],
        "photos": _safe_photos(acc),
        "created_at": acc.created_at.isoformat() if acc.created_at else None,
        "updated_at": acc.updated_at.isoformat() if acc.updated_at else None,
    }


def category_to_response(cat: RoomCategory) -> dict:
    """Convert RoomCategory model to response dict."""
    return {
        "id": cat.id,
        "accommodation_id": cat.accommodation_id,
        "name": cat.name,
        "code": cat.code,
        "description": cat.description,
        "min_occupancy": cat.min_occupancy,
        "max_occupancy": cat.max_occupancy,
        "max_adults": cat.max_adults,
        "max_children": cat.max_children,
        "available_bed_types": cat.available_bed_types or ["DBL"],
        "size_sqm": cat.size_sqm,
        "amenities": cat.amenities or [],
        "is_active": cat.is_active,
        "sort_order": cat.sort_order,
    }


def season_to_response(season: AccommodationSeason) -> dict:
    """Convert AccommodationSeason model to response dict."""
    return {
        "id": season.id,
        "accommodation_id": season.accommodation_id,
        "name": season.name,
        "code": season.code,
        "season_type": season.season_type,
        "season_level": getattr(season, 'season_level', 'high'),
        "start_date": season.start_date,
        "end_date": season.end_date,
        "weekdays": season.weekdays,
        "year": season.year,
        "priority": season.priority,
        "is_active": season.is_active,
        "created_at": season.created_at.isoformat() if hasattr(season, 'created_at') and season.created_at else None,
        "updated_at": season.updated_at.isoformat() if hasattr(season, 'updated_at') and season.updated_at else None,
    }


def rate_to_response(rate: RoomRate) -> dict:
    """Convert RoomRate model to response dict."""
    return {
        "id": rate.id,
        "accommodation_id": rate.accommodation_id,
        "room_category_id": rate.room_category_id,
        "season_id": rate.season_id,
        "bed_type": rate.bed_type,
        "base_occupancy": rate.base_occupancy,
        "rate_type": rate.rate_type,
        "cost": float(rate.cost),
        "currency": rate.currency,
        "single_supplement": float(rate.single_supplement) if rate.single_supplement else None,
        "extra_adult": float(rate.extra_adult) if rate.extra_adult else None,
        "extra_child": float(rate.extra_child) if rate.extra_child else None,
        "meal_plan": rate.meal_plan,
        "valid_from": rate.valid_from.isoformat() if rate.valid_from else None,
        "valid_to": rate.valid_to.isoformat() if rate.valid_to else None,
        "notes": rate.notes,
        "is_active": rate.is_active,
    }


# ============================================================================
# Accommodation Endpoints
# ============================================================================

@router.get("", response_model=List[AccommodationResponse])
async def list_accommodations(
    supplier_id: Optional[int] = Query(None),
    status: Optional[str] = Query(None),
    location_id: Optional[int] = Query(None),
    search: Optional[str] = Query(None),
    star_rating_min: Optional[int] = Query(None),
    star_rating_max: Optional[int] = Query(None),
    country_code: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    tenant: Tenant = Depends(get_current_tenant),
):
    """List all accommodations for the tenant, with optional filters."""
    query = (
        select(Accommodation)
        .where(Accommodation.tenant_id == tenant.id)
        .options(
            selectinload(Accommodation.room_categories),
            selectinload(Accommodation.seasons),
            selectinload(Accommodation.photos),
        )
    )

    if supplier_id:
        query = query.where(Accommodation.supplier_id == supplier_id)
    if status:
        query = query.where(Accommodation.status == status)
    if location_id:
        query = query.where(Accommodation.location_id == location_id)
    if search:
        query = query.where(Accommodation.name.ilike(f"%{search}%"))
    if star_rating_min is not None:
        query = query.where(Accommodation.star_rating >= star_rating_min)
    if star_rating_max is not None:
        query = query.where(Accommodation.star_rating <= star_rating_max)
    if country_code:
        query = query.where(Accommodation.country_code == country_code.upper())

    query = query.order_by(Accommodation.name)

    result = await db.execute(query)
    accommodations = result.scalars().all()

    return [accommodation_to_response(acc) for acc in accommodations]


@router.get("/{accommodation_id}", response_model=AccommodationResponse)
async def get_accommodation(
    accommodation_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    tenant: Tenant = Depends(get_current_tenant),
):
    """Get a single accommodation by ID."""
    query = (
        select(Accommodation)
        .where(Accommodation.id == accommodation_id, Accommodation.tenant_id == tenant.id)
        .options(
            selectinload(Accommodation.room_categories),
            selectinload(Accommodation.seasons),
            selectinload(Accommodation.photos),
        )
    )
    result = await db.execute(query)
    accommodation = result.scalar_one_or_none()

    if not accommodation:
        raise HTTPException(status_code=404, detail="Accommodation not found")

    return accommodation_to_response(accommodation)


@router.post("", response_model=AccommodationResponse)
async def create_accommodation(
    data: CreateAccommodationRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    tenant: Tenant = Depends(get_current_tenant),
):
    """Create a new accommodation."""
    # Verify supplier exists and belongs to tenant
    supplier_query = select(Supplier).where(
        Supplier.id == data.supplier_id, Supplier.tenant_id == tenant.id
    )
    result = await db.execute(supplier_query)
    supplier = result.scalar_one_or_none()
    if not supplier:
        raise HTTPException(status_code=404, detail="Supplier not found")

    accommodation = Accommodation(
        tenant_id=tenant.id,
        supplier_id=data.supplier_id,
        name=data.name,
        description=data.description,
        star_rating=data.star_rating,
        internal_priority=data.internal_priority,
        internal_notes=data.internal_notes,
        # Location (lien vers table locations pour filtrage)
        location_id=data.location_id,
        # Adresse Google Maps
        address=data.address,
        city=data.city,
        country_code=data.country_code,
        lat=Decimal(str(data.lat)) if data.lat else None,
        lng=Decimal(str(data.lng)) if data.lng else None,
        google_place_id=data.google_place_id,
        check_in_time=data.check_in_time,
        check_out_time=data.check_out_time,
        amenities=data.amenities,
        reservation_email=data.reservation_email,
        reservation_phone=data.reservation_phone,
        website_url=data.website_url,
        # Billing entity info (for logistics)
        billing_entity_name=data.billing_entity_name,
        billing_entity_note=data.billing_entity_note,
        external_provider=data.external_provider,
        external_id=data.external_id,
        # Lien futur vers article de contenu
        content_id=data.content_id,
        # Payment terms override (optional)
        payment_terms_id=data.payment_terms_id,
    )

    db.add(accommodation)
    await db.commit()

    # Reload with relationships to avoid lazy loading issues
    result = await db.execute(
        select(Accommodation)
        .where(Accommodation.id == accommodation.id)
        .options(
            selectinload(Accommodation.room_categories),
            selectinload(Accommodation.seasons),
        )
    )
    accommodation = result.scalar_one()

    return accommodation_to_response(accommodation)


@router.patch("/{accommodation_id}", response_model=AccommodationResponse)
async def update_accommodation(
    accommodation_id: int,
    data: UpdateAccommodationRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    tenant: Tenant = Depends(get_current_tenant),
):
    """Update an accommodation."""
    query = select(Accommodation).where(
        Accommodation.id == accommodation_id, Accommodation.tenant_id == tenant.id
    )
    result = await db.execute(query)
    accommodation = result.scalar_one_or_none()

    if not accommodation:
        raise HTTPException(status_code=404, detail="Accommodation not found")

    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        if field in ["lat", "lng"] and value is not None:
            value = Decimal(str(value))
        setattr(accommodation, field, value)

    await db.commit()

    # Reload with relationships to avoid lazy loading issues
    result = await db.execute(
        select(Accommodation)
        .where(Accommodation.id == accommodation_id)
        .options(
            selectinload(Accommodation.room_categories),
            selectinload(Accommodation.seasons),
        )
    )
    accommodation = result.scalar_one()

    return accommodation_to_response(accommodation)


@router.delete("/{accommodation_id}")
async def delete_accommodation(
    accommodation_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    tenant: Tenant = Depends(get_current_tenant),
):
    """Delete an accommodation."""
    query = select(Accommodation).where(
        Accommodation.id == accommodation_id, Accommodation.tenant_id == tenant.id
    )
    result = await db.execute(query)
    accommodation = result.scalar_one_or_none()

    if not accommodation:
        raise HTTPException(status_code=404, detail="Accommodation not found")

    await db.delete(accommodation)
    await db.commit()

    return {"message": "Accommodation deleted successfully"}


# ============================================================================
# Room Category Endpoints
# ============================================================================

@router.get("/{accommodation_id}/room-categories", response_model=List[RoomCategoryResponse])
async def list_room_categories(
    accommodation_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    tenant: Tenant = Depends(get_current_tenant),
):
    """List room categories for an accommodation."""
    # Verify accommodation
    acc_query = select(Accommodation).where(
        Accommodation.id == accommodation_id, Accommodation.tenant_id == tenant.id
    )
    result = await db.execute(acc_query)
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Accommodation not found")

    query = (
        select(RoomCategory)
        .where(RoomCategory.accommodation_id == accommodation_id)
        .order_by(RoomCategory.sort_order)
    )
    result = await db.execute(query)
    categories = result.scalars().all()

    return [category_to_response(c) for c in categories]


@router.post("/{accommodation_id}/room-categories", response_model=RoomCategoryResponse)
async def create_room_category(
    accommodation_id: int,
    data: CreateRoomCategoryRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    tenant: Tenant = Depends(get_current_tenant),
):
    """Create a room category."""
    # Verify accommodation
    acc_query = select(Accommodation).where(
        Accommodation.id == accommodation_id, Accommodation.tenant_id == tenant.id
    )
    result = await db.execute(acc_query)
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Accommodation not found")

    category = RoomCategory(
        accommodation_id=accommodation_id,
        **data.model_dump(),
    )

    db.add(category)
    await db.commit()
    await db.refresh(category)

    return category_to_response(category)


@router.patch("/{accommodation_id}/room-categories/{category_id}", response_model=RoomCategoryResponse)
async def update_room_category(
    accommodation_id: int,
    category_id: int,
    data: UpdateRoomCategoryRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    tenant: Tenant = Depends(get_current_tenant),
):
    """Update a room category."""
    query = (
        select(RoomCategory)
        .join(Accommodation)
        .where(
            RoomCategory.id == category_id,
            RoomCategory.accommodation_id == accommodation_id,
            Accommodation.tenant_id == tenant.id,
        )
    )
    result = await db.execute(query)
    category = result.scalar_one_or_none()

    if not category:
        raise HTTPException(status_code=404, detail="Room category not found")

    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(category, field, value)

    await db.commit()
    await db.refresh(category)

    return category_to_response(category)


@router.delete("/{accommodation_id}/room-categories/{category_id}")
async def delete_room_category(
    accommodation_id: int,
    category_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    tenant: Tenant = Depends(get_current_tenant),
):
    """Delete a room category."""
    query = (
        select(RoomCategory)
        .join(Accommodation)
        .where(
            RoomCategory.id == category_id,
            RoomCategory.accommodation_id == accommodation_id,
            Accommodation.tenant_id == tenant.id,
        )
    )
    result = await db.execute(query)
    category = result.scalar_one_or_none()

    if not category:
        raise HTTPException(status_code=404, detail="Room category not found")

    await db.delete(category)
    await db.commit()

    return {"message": "Room category deleted successfully"}


# ============================================================================
# Season Endpoints
# ============================================================================

@router.get("/{accommodation_id}/seasons", response_model=List[AccommodationSeasonResponse])
async def list_seasons(
    accommodation_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    tenant: Tenant = Depends(get_current_tenant),
):
    """List seasons for an accommodation."""
    acc_query = select(Accommodation).where(
        Accommodation.id == accommodation_id, Accommodation.tenant_id == tenant.id
    )
    result = await db.execute(acc_query)
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Accommodation not found")

    query = (
        select(AccommodationSeason)
        .where(AccommodationSeason.accommodation_id == accommodation_id)
        .order_by(AccommodationSeason.priority.desc())
    )
    result = await db.execute(query)
    seasons = result.scalars().all()

    return [season_to_response(s) for s in seasons]


@router.post("/{accommodation_id}/seasons", response_model=AccommodationSeasonResponse)
async def create_season(
    accommodation_id: int,
    data: CreateSeasonRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    tenant: Tenant = Depends(get_current_tenant),
):
    """Create a season."""
    acc_query = select(Accommodation).where(
        Accommodation.id == accommodation_id, Accommodation.tenant_id == tenant.id
    )
    result = await db.execute(acc_query)
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Accommodation not found")

    season = AccommodationSeason(
        accommodation_id=accommodation_id,
        **data.model_dump(),
    )

    db.add(season)
    await db.commit()
    await db.refresh(season)

    return season_to_response(season)


@router.patch("/{accommodation_id}/seasons/{season_id}", response_model=AccommodationSeasonResponse)
async def update_season(
    accommodation_id: int,
    season_id: int,
    data: UpdateSeasonRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    tenant: Tenant = Depends(get_current_tenant),
):
    """Update a season."""
    query = (
        select(AccommodationSeason)
        .join(Accommodation)
        .where(
            AccommodationSeason.id == season_id,
            AccommodationSeason.accommodation_id == accommodation_id,
            Accommodation.tenant_id == tenant.id,
        )
    )
    result = await db.execute(query)
    season = result.scalar_one_or_none()

    if not season:
        raise HTTPException(status_code=404, detail="Season not found")

    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(season, field, value)

    await db.commit()
    await db.refresh(season)

    return season_to_response(season)


@router.delete("/{accommodation_id}/seasons/{season_id}")
async def delete_season(
    accommodation_id: int,
    season_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    tenant: Tenant = Depends(get_current_tenant),
):
    """Delete a season and all associated rates."""
    query = (
        select(AccommodationSeason)
        .join(Accommodation)
        .where(
            AccommodationSeason.id == season_id,
            AccommodationSeason.accommodation_id == accommodation_id,
            Accommodation.tenant_id == tenant.id,
        )
    )
    result = await db.execute(query)
    season = result.scalar_one_or_none()

    if not season:
        raise HTTPException(status_code=404, detail="Season not found")

    # First, delete all rates associated with this season
    from sqlalchemy import delete as sql_delete
    delete_rates_query = sql_delete(RoomRate).where(RoomRate.season_id == season_id)
    await db.execute(delete_rates_query)

    # Then delete the season
    await db.delete(season)
    await db.commit()

    return {"message": "Season deleted successfully"}


# ============================================================================
# Room Rate Endpoints
# ============================================================================

@router.get("/{accommodation_id}/rates", response_model=List[RoomRateResponse])
async def list_rates(
    accommodation_id: int,
    room_category_id: Optional[int] = Query(None),
    season_id: Optional[int] = Query(None),
    bed_type: Optional[str] = Query(None),
    meal_plan: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    tenant: Tenant = Depends(get_current_tenant),
):
    """List rates for an accommodation."""
    acc_query = select(Accommodation).where(
        Accommodation.id == accommodation_id, Accommodation.tenant_id == tenant.id
    )
    result = await db.execute(acc_query)
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Accommodation not found")

    query = select(RoomRate).where(RoomRate.accommodation_id == accommodation_id)

    if room_category_id:
        query = query.where(RoomRate.room_category_id == room_category_id)
    if season_id:
        query = query.where(RoomRate.season_id == season_id)
    if bed_type:
        query = query.where(RoomRate.bed_type == bed_type)
    if meal_plan:
        query = query.where(RoomRate.meal_plan == meal_plan)

    result = await db.execute(query)
    rates = result.scalars().all()

    return [rate_to_response(r) for r in rates]


@router.post("/{accommodation_id}/rates", response_model=RoomRateResponse)
async def create_rate(
    accommodation_id: int,
    data: CreateRoomRateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    tenant: Tenant = Depends(get_current_tenant),
):
    """Create a room rate."""
    acc_query = select(Accommodation).where(
        Accommodation.id == accommodation_id, Accommodation.tenant_id == tenant.id
    )
    result = await db.execute(acc_query)
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Accommodation not found")

    rate = RoomRate(
        accommodation_id=accommodation_id,
        room_category_id=data.room_category_id,
        season_id=data.season_id,
        bed_type=data.bed_type,
        base_occupancy=data.base_occupancy,
        rate_type=data.rate_type,
        cost=Decimal(str(data.cost)),
        currency=data.currency,
        single_supplement=Decimal(str(data.single_supplement)) if data.single_supplement else None,
        extra_adult=Decimal(str(data.extra_adult)) if data.extra_adult else None,
        extra_child=Decimal(str(data.extra_child)) if data.extra_child else None,
        meal_plan=data.meal_plan,
        notes=data.notes,
    )

    db.add(rate)
    await db.commit()
    await db.refresh(rate)

    return rate_to_response(rate)


@router.patch("/{accommodation_id}/rates/{rate_id}", response_model=RoomRateResponse)
async def update_rate(
    accommodation_id: int,
    rate_id: int,
    data: UpdateRoomRateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    tenant: Tenant = Depends(get_current_tenant),
):
    """Update a room rate."""
    query = (
        select(RoomRate)
        .join(Accommodation)
        .where(
            RoomRate.id == rate_id,
            RoomRate.accommodation_id == accommodation_id,
            Accommodation.tenant_id == tenant.id,
        )
    )
    result = await db.execute(query)
    rate = result.scalar_one_or_none()

    if not rate:
        raise HTTPException(status_code=404, detail="Rate not found")

    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        if field in ["cost", "single_supplement", "extra_adult", "extra_child"] and value is not None:
            value = Decimal(str(value))
        setattr(rate, field, value)

    await db.commit()
    await db.refresh(rate)

    return rate_to_response(rate)


@router.delete("/{accommodation_id}/rates/{rate_id}")
async def delete_rate(
    accommodation_id: int,
    rate_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    tenant: Tenant = Depends(get_current_tenant),
):
    """Delete a room rate."""
    query = (
        select(RoomRate)
        .join(Accommodation)
        .where(
            RoomRate.id == rate_id,
            RoomRate.accommodation_id == accommodation_id,
            Accommodation.tenant_id == tenant.id,
        )
    )
    result = await db.execute(query)
    rate = result.scalar_one_or_none()

    if not rate:
        raise HTTPException(status_code=404, detail="Rate not found")

    await db.delete(rate)
    await db.commit()

    return {"message": "Rate deleted successfully"}


@router.post("/{accommodation_id}/rates/bulk", response_model=List[RoomRateResponse])
async def bulk_upsert_rates(
    accommodation_id: int,
    data: BulkRatesRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    tenant: Tenant = Depends(get_current_tenant),
):
    """Bulk create or update rates."""
    acc_query = select(Accommodation).where(
        Accommodation.id == accommodation_id, Accommodation.tenant_id == tenant.id
    )
    result = await db.execute(acc_query)
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Accommodation not found")

    created_rates = []
    for rate_data in data.rates:
        # Check if rate already exists
        existing_query = select(RoomRate).where(
            RoomRate.accommodation_id == accommodation_id,
            RoomRate.room_category_id == rate_data.room_category_id,
            RoomRate.season_id == rate_data.season_id,
            RoomRate.bed_type == rate_data.bed_type,
            RoomRate.meal_plan == rate_data.meal_plan,
        )
        result = await db.execute(existing_query)
        existing = result.scalar_one_or_none()

        if existing:
            # Update
            existing.cost = Decimal(str(rate_data.cost))
            existing.currency = rate_data.currency
            existing.single_supplement = Decimal(str(rate_data.single_supplement)) if rate_data.single_supplement else None
            existing.extra_adult = Decimal(str(rate_data.extra_adult)) if rate_data.extra_adult else None
            existing.extra_child = Decimal(str(rate_data.extra_child)) if rate_data.extra_child else None
            created_rates.append(existing)
        else:
            # Create
            rate = RoomRate(
                accommodation_id=accommodation_id,
                room_category_id=rate_data.room_category_id,
                season_id=rate_data.season_id,
                bed_type=rate_data.bed_type,
                base_occupancy=rate_data.base_occupancy,
                rate_type=rate_data.rate_type,
                cost=Decimal(str(rate_data.cost)),
                currency=rate_data.currency,
                single_supplement=Decimal(str(rate_data.single_supplement)) if rate_data.single_supplement else None,
                extra_adult=Decimal(str(rate_data.extra_adult)) if rate_data.extra_adult else None,
                extra_child=Decimal(str(rate_data.extra_child)) if rate_data.extra_child else None,
                meal_plan=rate_data.meal_plan,
                notes=rate_data.notes,
            )
            db.add(rate)
            created_rates.append(rate)

    await db.commit()

    for rate in created_rates:
        await db.refresh(rate)

    return [rate_to_response(r) for r in created_rates]


# ============================================================================
# Supplier Accommodation Endpoint
# ============================================================================

@router.get("/by-supplier/{supplier_id}", response_model=AccommodationResponse)
async def get_accommodation_by_supplier(
    supplier_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    tenant: Tenant = Depends(get_current_tenant),
):
    """Get the accommodation for a supplier."""
    query = (
        select(Accommodation)
        .where(Accommodation.supplier_id == supplier_id, Accommodation.tenant_id == tenant.id)
        .options(
            selectinload(Accommodation.room_categories),
            selectinload(Accommodation.seasons),
        )
    )
    result = await db.execute(query)
    accommodation = result.scalar_one_or_none()

    if not accommodation:
        raise HTTPException(status_code=404, detail="Accommodation not found")

    return accommodation_to_response(accommodation)


# ============================================================================
# Early Bird Discount Endpoints
# ============================================================================

def early_bird_to_response(discount: EarlyBirdDiscount) -> dict:
    """Convert EarlyBirdDiscount model to response dict."""
    return {
        "id": discount.id,
        "accommodation_id": discount.accommodation_id,
        "name": discount.name,
        "days_in_advance": discount.days_in_advance,
        "discount_percent": float(discount.discount_percent),
        "discount_amount": float(discount.discount_amount) if discount.discount_amount else None,
        "discount_currency": discount.discount_currency,
        "valid_from": discount.valid_from.isoformat() if discount.valid_from else None,
        "valid_to": discount.valid_to.isoformat() if discount.valid_to else None,
        "season_ids": discount.season_ids,
        "excluded_season_ids": discount.excluded_season_ids,
        "is_cumulative": discount.is_cumulative,
        "priority": discount.priority,
        "is_active": discount.is_active,
    }


@router.get("/{accommodation_id}/early-bird", response_model=List[EarlyBirdDiscountResponse])
async def list_early_bird_discounts(
    accommodation_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    tenant: Tenant = Depends(get_current_tenant),
):
    """List early bird discounts for an accommodation."""
    acc_query = select(Accommodation).where(
        Accommodation.id == accommodation_id, Accommodation.tenant_id == tenant.id
    )
    result = await db.execute(acc_query)
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Accommodation not found")

    query = (
        select(EarlyBirdDiscount)
        .where(EarlyBirdDiscount.accommodation_id == accommodation_id)
        .order_by(EarlyBirdDiscount.days_in_advance)
    )
    result = await db.execute(query)
    discounts = result.scalars().all()

    return [early_bird_to_response(d) for d in discounts]


@router.post("/{accommodation_id}/early-bird", response_model=EarlyBirdDiscountResponse)
async def create_early_bird_discount(
    accommodation_id: int,
    data: CreateEarlyBirdDiscountRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    tenant: Tenant = Depends(get_current_tenant),
):
    """Create an early bird discount."""
    acc_query = select(Accommodation).where(
        Accommodation.id == accommodation_id, Accommodation.tenant_id == tenant.id
    )
    result = await db.execute(acc_query)
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Accommodation not found")

    discount = EarlyBirdDiscount(
        accommodation_id=accommodation_id,
        name=data.name,
        days_in_advance=data.days_in_advance,
        discount_percent=Decimal(str(data.discount_percent)),
        discount_amount=Decimal(str(data.discount_amount)) if data.discount_amount else None,
        discount_currency=data.discount_currency,
        season_ids=data.season_ids,
        excluded_season_ids=data.excluded_season_ids,
        is_cumulative=data.is_cumulative,
        priority=data.priority,
    )

    db.add(discount)
    await db.commit()
    await db.refresh(discount)

    return early_bird_to_response(discount)


@router.patch("/{accommodation_id}/early-bird/{discount_id}", response_model=EarlyBirdDiscountResponse)
async def update_early_bird_discount(
    accommodation_id: int,
    discount_id: int,
    data: UpdateEarlyBirdDiscountRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    tenant: Tenant = Depends(get_current_tenant),
):
    """Update an early bird discount."""
    query = (
        select(EarlyBirdDiscount)
        .join(Accommodation)
        .where(
            EarlyBirdDiscount.id == discount_id,
            EarlyBirdDiscount.accommodation_id == accommodation_id,
            Accommodation.tenant_id == tenant.id,
        )
    )
    result = await db.execute(query)
    discount = result.scalar_one_or_none()

    if not discount:
        raise HTTPException(status_code=404, detail="Early bird discount not found")

    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        if field in ["discount_percent", "discount_amount"] and value is not None:
            value = Decimal(str(value))
        setattr(discount, field, value)

    await db.commit()
    await db.refresh(discount)

    return early_bird_to_response(discount)


@router.delete("/{accommodation_id}/early-bird/{discount_id}")
async def delete_early_bird_discount(
    accommodation_id: int,
    discount_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    tenant: Tenant = Depends(get_current_tenant),
):
    """Delete an early bird discount."""
    query = (
        select(EarlyBirdDiscount)
        .join(Accommodation)
        .where(
            EarlyBirdDiscount.id == discount_id,
            EarlyBirdDiscount.accommodation_id == accommodation_id,
            Accommodation.tenant_id == tenant.id,
        )
    )
    result = await db.execute(query)
    discount = result.scalar_one_or_none()

    if not discount:
        raise HTTPException(status_code=404, detail="Early bird discount not found")

    await db.delete(discount)
    await db.commit()

    return {"message": "Early bird discount deleted successfully"}


# ============================================================================
# Extras (Optional Supplements) Endpoints
# ============================================================================

@router.get("/{accommodation_id}/extras", response_model=List[AccommodationExtraResponse])
async def get_accommodation_extras(
    accommodation_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    tenant: Tenant = Depends(get_current_tenant),
):
    """Get all extras for an accommodation."""
    # Verify accommodation belongs to tenant
    acc_query = select(Accommodation).where(
        Accommodation.id == accommodation_id,
        Accommodation.tenant_id == tenant.id,
    )
    acc_result = await db.execute(acc_query)
    if not acc_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Accommodation not found")

    query = (
        select(AccommodationExtra)
        .where(AccommodationExtra.accommodation_id == accommodation_id)
        .order_by(AccommodationExtra.sort_order, AccommodationExtra.name)
    )
    result = await db.execute(query)
    extras = result.scalars().all()
    return extras


@router.post("/{accommodation_id}/extras", response_model=AccommodationExtraResponse, status_code=201)
async def create_accommodation_extra(
    accommodation_id: int,
    request: CreateAccommodationExtraRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    tenant: Tenant = Depends(get_current_tenant),
):
    """Create a new extra for an accommodation."""
    # Verify accommodation belongs to tenant
    acc_query = select(Accommodation).where(
        Accommodation.id == accommodation_id,
        Accommodation.tenant_id == tenant.id,
    )
    acc_result = await db.execute(acc_query)
    if not acc_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Accommodation not found")

    extra = AccommodationExtra(
        accommodation_id=accommodation_id,
        name=request.name,
        code=request.code,
        description=request.description,
        extra_type=request.extra_type,
        unit_cost=Decimal(str(request.unit_cost)),
        currency=request.currency,
        pricing_model=request.pricing_model,
        season_id=request.season_id,
        is_included=request.is_included,
        is_mandatory=request.is_mandatory,
        sort_order=request.sort_order,
        is_active=True,
    )
    db.add(extra)
    await db.commit()
    await db.refresh(extra)
    return extra


@router.get("/{accommodation_id}/extras/{extra_id}", response_model=AccommodationExtraResponse)
async def get_accommodation_extra(
    accommodation_id: int,
    extra_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    tenant: Tenant = Depends(get_current_tenant),
):
    """Get a specific extra."""
    query = (
        select(AccommodationExtra)
        .join(Accommodation)
        .where(
            AccommodationExtra.id == extra_id,
            AccommodationExtra.accommodation_id == accommodation_id,
            Accommodation.tenant_id == tenant.id,
        )
    )
    result = await db.execute(query)
    extra = result.scalar_one_or_none()

    if not extra:
        raise HTTPException(status_code=404, detail="Extra not found")

    return extra


@router.patch("/{accommodation_id}/extras/{extra_id}", response_model=AccommodationExtraResponse)
async def update_accommodation_extra(
    accommodation_id: int,
    extra_id: int,
    request: UpdateAccommodationExtraRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    tenant: Tenant = Depends(get_current_tenant),
):
    """Update an extra."""
    query = (
        select(AccommodationExtra)
        .join(Accommodation)
        .where(
            AccommodationExtra.id == extra_id,
            AccommodationExtra.accommodation_id == accommodation_id,
            Accommodation.tenant_id == tenant.id,
        )
    )
    result = await db.execute(query)
    extra = result.scalar_one_or_none()

    if not extra:
        raise HTTPException(status_code=404, detail="Extra not found")

    # Update fields if provided
    update_data = request.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        if field == "unit_cost" and value is not None:
            value = Decimal(str(value))
        setattr(extra, field, value)

    await db.commit()
    await db.refresh(extra)
    return extra


@router.delete("/{accommodation_id}/extras/{extra_id}")
async def delete_accommodation_extra(
    accommodation_id: int,
    extra_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    tenant: Tenant = Depends(get_current_tenant),
):
    """Delete an extra."""
    query = (
        select(AccommodationExtra)
        .join(Accommodation)
        .where(
            AccommodationExtra.id == extra_id,
            AccommodationExtra.accommodation_id == accommodation_id,
            Accommodation.tenant_id == tenant.id,
        )
    )
    result = await db.execute(query)
    extra = result.scalar_one_or_none()

    if not extra:
        raise HTTPException(status_code=404, detail="Extra not found")

    await db.delete(extra)
    await db.commit()

    return {"message": "Extra deleted successfully"}


# ============================================================================
# Photo Schemas
# ============================================================================

class AccommodationPhotoResponse(BaseModel):
    """Response schema for accommodation photos."""
    id: int
    accommodation_id: int
    room_category_id: Optional[int] = None
    url: str
    thumbnail_url: Optional[str] = None
    url_avif: Optional[str] = None
    url_webp: Optional[str] = None
    url_medium: Optional[str] = None
    url_large: Optional[str] = None
    srcset_json: Optional[str] = None
    lqip_data_url: Optional[str] = None
    original_filename: Optional[str] = None
    file_size: Optional[int] = None
    mime_type: Optional[str] = None
    width: Optional[int] = None
    height: Optional[int] = None
    caption: Optional[str] = None
    alt_text: Optional[str] = None
    is_main: bool = False
    is_processed: bool = False
    sort_order: int = 0
    created_at: Optional[str] = None

    class Config:
        from_attributes = True


class UpdatePhotoRequest(BaseModel):
    """Request schema for updating photo metadata."""
    caption: Optional[str] = None
    alt_text: Optional[str] = None
    is_main: Optional[bool] = None
    sort_order: Optional[int] = None


class ReorderPhotosRequest(BaseModel):
    """Request schema for reordering photos."""
    photo_ids: List[int]


# ============================================================================
# Photo Endpoints
# ============================================================================

@router.get("/{accommodation_id}/photos", response_model=List[AccommodationPhotoResponse])
async def get_accommodation_photos(
    accommodation_id: int,
    room_category_id: Optional[int] = Query(None, description="Filter by room category (null for hotel-level)"),
    include_all: bool = Query(False, description="Include all photos (hotel + room categories)"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    tenant: Tenant = Depends(get_current_tenant),
):
    """
    Get photos for an accommodation.

    - If room_category_id is provided, returns photos for that room category only
    - If room_category_id is null/not provided and include_all=false, returns hotel-level photos only
    - If include_all=true, returns all photos (hotel + all room categories)
    """
    # Verify accommodation exists and belongs to tenant
    acc_result = await db.execute(
        select(Accommodation).where(
            Accommodation.id == accommodation_id,
            Accommodation.tenant_id == tenant.id,
        )
    )
    accommodation = acc_result.scalar_one_or_none()
    if not accommodation:
        raise HTTPException(status_code=404, detail="Accommodation not found")

    # Build query
    query = select(AccommodationPhoto).where(
        AccommodationPhoto.accommodation_id == accommodation_id,
    )

    if room_category_id is not None:
        # Filter by specific room category
        query = query.where(AccommodationPhoto.room_category_id == room_category_id)
    elif not include_all:
        # Only hotel-level photos (room_category_id is NULL)
        query = query.where(AccommodationPhoto.room_category_id.is_(None))

    # Order by sort_order, then by is_main (main photo first)
    query = query.order_by(
        AccommodationPhoto.room_category_id.nullsfirst(),
        AccommodationPhoto.is_main.desc(),
        AccommodationPhoto.sort_order,
        AccommodationPhoto.id,
    )

    result = await db.execute(query)
    photos = result.scalars().all()

    return [
        AccommodationPhotoResponse(
            id=p.id,
            accommodation_id=p.accommodation_id,
            room_category_id=p.room_category_id,
            url=p.url,
            thumbnail_url=p.thumbnail_url,
            url_avif=p.url_avif,
            url_webp=p.url_webp,
            url_medium=p.url_medium,
            url_large=p.url_large,
            srcset_json=p.srcset_json,
            lqip_data_url=p.lqip_data_url,
            original_filename=p.original_filename,
            file_size=p.file_size,
            mime_type=p.mime_type,
            width=p.width,
            height=p.height,
            caption=p.caption,
            alt_text=p.alt_text,
            is_main=p.is_main,
            is_processed=p.is_processed,
            sort_order=p.sort_order,
            created_at=p.created_at.isoformat() if p.created_at else None,
        )
        for p in photos
    ]


@router.post("/{accommodation_id}/photos", response_model=AccommodationPhotoResponse)
async def upload_accommodation_photo(
    accommodation_id: int,
    file: UploadFile = File(...),
    room_category_id: Optional[int] = Form(None),
    caption: Optional[str] = Form(None),
    alt_text: Optional[str] = Form(None),
    is_main: bool = Form(False),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    tenant: Tenant = Depends(get_current_tenant),
):
    """
    Upload a new photo for an accommodation.

    - Set room_category_id to associate with a specific room type
    - Set is_main=true to make this the primary photo
    """
    # Verify accommodation exists and belongs to tenant
    acc_result = await db.execute(
        select(Accommodation).where(
            Accommodation.id == accommodation_id,
            Accommodation.tenant_id == tenant.id,
        )
    )
    accommodation = acc_result.scalar_one_or_none()
    if not accommodation:
        raise HTTPException(status_code=404, detail="Accommodation not found")

    # Verify room category if provided
    if room_category_id:
        rc_result = await db.execute(
            select(RoomCategory).where(
                RoomCategory.id == room_category_id,
                RoomCategory.accommodation_id == accommodation_id,
            )
        )
        if not rc_result.scalar_one_or_none():
            raise HTTPException(status_code=404, detail="Room category not found")

    # Read file content
    file_content = await file.read()
    file_size = len(file_content)
    mime_type = file.content_type or get_mime_type(file.filename or "image.jpg")

    try:
        # Upload to Supabase Storage
        storage_path, public_url = await upload_to_supabase(
            file_content=file_content,
            original_filename=file.filename or "image.jpg",
            tenant_id=str(tenant.id),
            accommodation_id=accommodation_id,
            room_category_id=room_category_id,
            mime_type=mime_type,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")

    # Process image for immediate use (thumbnail, dimensions, LQIP)
    thumbnail_url = None
    lqip_data_url = None
    width = None
    height = None

    try:
        thumbnail_data, medium_data, lqip_data_url, width, height = process_image_minimal(file_content)

        # Upload thumbnail
        base_path = storage_path.rsplit(".", 1)[0]
        thumbnail_path = f"{base_path}_thumbnail.jpg"

        client = get_supabase_client()
        client.storage.from_(BUCKET_NAME).upload(
            path=thumbnail_path,
            file=thumbnail_data,
            file_options={
                "content-type": "image/jpeg",
                "cache-control": "31536000",
            },
        )
        thumbnail_url = client.storage.from_(BUCKET_NAME).get_public_url(thumbnail_path)
    except Exception as e:
        # Image processing failed, but original upload succeeded
        # Log error but continue with unprocessed photo
        import logging
        logging.warning(f"Image processing failed for {storage_path}: {e}")

    # If this is set as main photo, unset any existing main photo
    if is_main:
        await db.execute(
            select(AccommodationPhoto)
            .where(
                AccommodationPhoto.accommodation_id == accommodation_id,
                AccommodationPhoto.room_category_id == room_category_id,
                AccommodationPhoto.is_main == True,
            )
        )
        # Update existing main photos to not be main
        from sqlalchemy import update
        await db.execute(
            update(AccommodationPhoto)
            .where(
                AccommodationPhoto.accommodation_id == accommodation_id,
                AccommodationPhoto.room_category_id == room_category_id,
                AccommodationPhoto.is_main == True,
            )
            .values(is_main=False)
        )

    # Get next sort_order
    sort_result = await db.execute(
        select(AccommodationPhoto.sort_order)
        .where(
            AccommodationPhoto.accommodation_id == accommodation_id,
            AccommodationPhoto.room_category_id == room_category_id,
        )
        .order_by(AccommodationPhoto.sort_order.desc())
        .limit(1)
    )
    max_sort = sort_result.scalar_one_or_none()
    next_sort = (max_sort or 0) + 1

    # Create photo record
    photo = AccommodationPhoto(
        tenant_id=tenant.id,
        accommodation_id=accommodation_id,
        room_category_id=room_category_id,
        storage_path=storage_path,
        url=public_url,
        thumbnail_url=thumbnail_url,
        lqip_data_url=lqip_data_url,
        original_filename=file.filename,
        file_size=file_size,
        mime_type=mime_type,
        width=width,
        height=height,
        caption=caption,
        alt_text=alt_text,
        is_main=is_main,
        is_processed=False,  # Will be processed by worker for AVIF/WebP variants
        sort_order=next_sort,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )

    db.add(photo)
    await db.commit()
    await db.refresh(photo)

    return AccommodationPhotoResponse(
        id=photo.id,
        accommodation_id=photo.accommodation_id,
        room_category_id=photo.room_category_id,
        url=photo.url,
        thumbnail_url=photo.thumbnail_url,
        url_avif=photo.url_avif,
        url_webp=photo.url_webp,
        url_medium=photo.url_medium,
        url_large=photo.url_large,
        srcset_json=photo.srcset_json,
        lqip_data_url=photo.lqip_data_url,
        original_filename=photo.original_filename,
        file_size=photo.file_size,
        mime_type=photo.mime_type,
        width=photo.width,
        height=photo.height,
        caption=photo.caption,
        alt_text=photo.alt_text,
        is_main=photo.is_main,
        is_processed=photo.is_processed,
        sort_order=photo.sort_order,
        created_at=photo.created_at.isoformat() if photo.created_at else None,
    )


@router.patch("/{accommodation_id}/photos/{photo_id}", response_model=AccommodationPhotoResponse)
async def update_accommodation_photo(
    accommodation_id: int,
    photo_id: int,
    data: UpdatePhotoRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    tenant: Tenant = Depends(get_current_tenant),
):
    """Update photo metadata (caption, alt_text, is_main, sort_order)."""
    # Find the photo
    query = (
        select(AccommodationPhoto)
        .join(Accommodation)
        .where(
            AccommodationPhoto.id == photo_id,
            AccommodationPhoto.accommodation_id == accommodation_id,
            Accommodation.tenant_id == tenant.id,
        )
    )
    result = await db.execute(query)
    photo = result.scalar_one_or_none()

    if not photo:
        raise HTTPException(status_code=404, detail="Photo not found")

    # If setting as main, unset other main photos for same category
    if data.is_main is True:
        from sqlalchemy import update
        await db.execute(
            update(AccommodationPhoto)
            .where(
                AccommodationPhoto.accommodation_id == accommodation_id,
                AccommodationPhoto.room_category_id == photo.room_category_id,
                AccommodationPhoto.is_main == True,
                AccommodationPhoto.id != photo_id,
            )
            .values(is_main=False)
        )

    # Update fields
    if data.caption is not None:
        photo.caption = data.caption
    if data.alt_text is not None:
        photo.alt_text = data.alt_text
    if data.is_main is not None:
        photo.is_main = data.is_main
    if data.sort_order is not None:
        photo.sort_order = data.sort_order

    photo.updated_at = datetime.utcnow()

    await db.commit()
    await db.refresh(photo)

    return AccommodationPhotoResponse(
        id=photo.id,
        accommodation_id=photo.accommodation_id,
        room_category_id=photo.room_category_id,
        url=photo.url,
        thumbnail_url=photo.thumbnail_url,
        url_avif=photo.url_avif,
        url_webp=photo.url_webp,
        url_medium=photo.url_medium,
        url_large=photo.url_large,
        srcset_json=photo.srcset_json,
        lqip_data_url=photo.lqip_data_url,
        original_filename=photo.original_filename,
        file_size=photo.file_size,
        mime_type=photo.mime_type,
        width=photo.width,
        height=photo.height,
        caption=photo.caption,
        alt_text=photo.alt_text,
        is_main=photo.is_main,
        is_processed=photo.is_processed,
        sort_order=photo.sort_order,
        created_at=photo.created_at.isoformat() if photo.created_at else None,
    )


@router.delete("/{accommodation_id}/photos/{photo_id}")
async def delete_accommodation_photo(
    accommodation_id: int,
    photo_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    tenant: Tenant = Depends(get_current_tenant),
):
    """Delete a photo from accommodation."""
    # Find the photo
    query = (
        select(AccommodationPhoto)
        .join(Accommodation)
        .where(
            AccommodationPhoto.id == photo_id,
            AccommodationPhoto.accommodation_id == accommodation_id,
            Accommodation.tenant_id == tenant.id,
        )
    )
    result = await db.execute(query)
    photo = result.scalar_one_or_none()

    if not photo:
        raise HTTPException(status_code=404, detail="Photo not found")

    # Delete from storage
    try:
        await delete_from_supabase(photo.storage_path)
    except Exception as e:
        # Log error but continue with database deletion
        print(f"Warning: Failed to delete from storage: {e}")

    # Delete from database
    await db.delete(photo)
    await db.commit()

    return {"message": "Photo deleted successfully"}


@router.post("/{accommodation_id}/photos/reorder")
async def reorder_accommodation_photos(
    accommodation_id: int,
    data: ReorderPhotosRequest,
    room_category_id: Optional[int] = Query(None, description="Room category to reorder (null for hotel-level)"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    tenant: Tenant = Depends(get_current_tenant),
):
    """
    Reorder photos by providing ordered list of photo IDs.

    The order in the photo_ids list becomes the new sort_order (0, 1, 2, ...).
    """
    # Verify accommodation exists and belongs to tenant
    acc_result = await db.execute(
        select(Accommodation).where(
            Accommodation.id == accommodation_id,
            Accommodation.tenant_id == tenant.id,
        )
    )
    if not acc_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Accommodation not found")

    # Update sort_order for each photo
    from sqlalchemy import update

    for index, photo_id in enumerate(data.photo_ids):
        await db.execute(
            update(AccommodationPhoto)
            .where(
                AccommodationPhoto.id == photo_id,
                AccommodationPhoto.accommodation_id == accommodation_id,
                AccommodationPhoto.room_category_id == room_category_id,
            )
            .values(sort_order=index, updated_at=datetime.utcnow())
        )

    await db.commit()

    return {"message": "Photos reordered successfully"}


@router.post("/{accommodation_id}/photos/{photo_id}/process")
async def process_photo_variants(
    accommodation_id: int,
    photo_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    tenant: Tenant = Depends(get_current_tenant),
):
    """
    Trigger processing of a photo to generate optimized variants (AVIF, WebP).

    This is normally done automatically by a background worker,
    but can be triggered manually if needed.
    """
    from app.services.image_worker import process_photo_immediately

    # Find the photo
    query = (
        select(AccommodationPhoto)
        .join(Accommodation)
        .where(
            AccommodationPhoto.id == photo_id,
            AccommodationPhoto.accommodation_id == accommodation_id,
            Accommodation.tenant_id == tenant.id,
        )
    )
    result = await db.execute(query)
    photo = result.scalar_one_or_none()

    if not photo:
        raise HTTPException(status_code=404, detail="Photo not found")

    if photo.is_processed:
        return {"message": "Photo already processed", "is_processed": True}

    success = await process_photo_immediately(db, photo_id)

    if success:
        return {"message": "Photo processed successfully", "is_processed": True}
    else:
        raise HTTPException(status_code=500, detail="Failed to process photo")


@router.post("/photos/process-batch")
async def process_unprocessed_photos_batch(
    limit: int = Query(default=10, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    tenant: Tenant = Depends(get_current_tenant),
):
    """
    Process a batch of unprocessed photos (admin function).

    This triggers the image processing worker to process up to `limit` photos.
    """
    from app.services.image_worker import process_unprocessed_photos

    # Only process photos belonging to this tenant
    processed_count = await process_unprocessed_photos(db, limit=limit)

    return {
        "message": f"Processed {processed_count} photos",
        "processed_count": processed_count,
    }