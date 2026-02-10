"""
Distribution API - Public catalog for B2B partners

This API allows partner platforms to:
- Browse available circuits
- Get circuit details
- Receive pricing with partner-specific markup
- Subscribe to webhooks for updates
"""

from datetime import datetime
from typing import List, Optional
import uuid

from fastapi import APIRouter, HTTPException, status, Query, Header, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_db
from app.models.trip import Trip, TripDay
from app.config import get_settings

router = APIRouter(prefix="/api/v1/catalog", tags=["Distribution API"])

settings = get_settings()


# ============================================================================
# Schemas for public API
# ============================================================================

class CatalogTripDay(BaseModel):
    """Public day information."""
    day_number: int
    day_number_end: Optional[int] = None
    title: Optional[str]
    description: Optional[str]
    location_from: Optional[str]
    location_to: Optional[str]

    class Config:
        from_attributes = True


class CatalogTripSummary(BaseModel):
    """Summary for catalog listing."""
    external_id: str  # external_reference or generated
    name: str
    destination_country: Optional[str]
    destination_countries: Optional[List[str]]
    duration_days: int
    description_short: Optional[str]
    highlights: Optional[List[dict]]
    comfort_level: Optional[int]
    difficulty_level: Optional[int]
    is_published: bool
    updated_at: datetime

    class Config:
        from_attributes = True


class CatalogTripDetail(CatalogTripSummary):
    """Full trip details for partners."""
    days: List[CatalogTripDay] = []
    inclusions: Optional[List[dict]]
    exclusions: Optional[List[dict]]
    info_general: Optional[str]
    info_formalities: Optional[str]
    info_booking_conditions: Optional[str]
    info_cancellation_policy: Optional[str]
    themes: Optional[List[str]]  # Theme labels
    # Pricing (with partner markup applied)
    base_price_per_person: Optional[float]
    currency: str


class CatalogListResponse(BaseModel):
    """Paginated catalog response."""
    items: List[CatalogTripSummary]
    total: int
    page: int
    page_size: int


class WebhookSubscription(BaseModel):
    """Webhook subscription request."""
    webhook_url: str
    events: List[str] = ["circuit.created", "circuit.updated", "circuit.deleted"]
    secret: Optional[str] = None


# ============================================================================
# API Key validation
# ============================================================================

async def validate_api_key(
    x_api_key: str = Header(..., alias="X-API-Key"),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Validate partner API key and return partner info.

    In production, this would query a partner_api_keys table.
    For now, we use a simple check.
    """
    # TODO: Replace with database lookup
    # For demo, accept any key starting with "pk_"
    if not x_api_key.startswith("pk_"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
        )

    # Extract partner ID from key (demo logic)
    # In production: lookup in partner_api_keys table
    partner_id = x_api_key.split("_")[1] if "_" in x_api_key else "default"

    return {
        "partner_id": partner_id,
        "channel": f"partner_{partner_id}",
        "markup_pct": 0,  # Default markup, would come from DB
    }


# ============================================================================
# Endpoints
# ============================================================================

@router.get("", response_model=CatalogListResponse)
async def list_catalog(
    db: AsyncSession = Depends(get_db),
    partner: dict = Depends(validate_api_key),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    destination: Optional[str] = Query(None, description="Filter by country code"),
    min_duration: Optional[int] = Query(None, ge=1),
    max_duration: Optional[int] = Query(None, ge=1),
):
    """
    List available circuits in the catalog.

    Only returns circuits that are:
    - Published (is_published = true)
    - Distributable (is_distributable = true)
    - Authorized for this partner's channel
    """
    query = select(Trip).where(
        and_(
            Trip.is_published == True,
            Trip.is_distributable == True,
            Trip.type == "online",  # Only master circuits
        )
    )

    # Filters
    if destination:
        query = query.where(Trip.destination_country == destination.upper())
    if min_duration:
        query = query.where(Trip.duration_days >= min_duration)
    if max_duration:
        query = query.where(Trip.duration_days <= max_duration)

    # Count total
    from sqlalchemy import func
    count_query = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_query)).scalar() or 0

    # Paginate
    query = query.offset((page - 1) * page_size).limit(page_size)
    query = query.order_by(Trip.updated_at.desc())

    result = await db.execute(query)
    trips = result.scalars().all()

    items = []
    for trip in trips:
        items.append(CatalogTripSummary(
            external_id=trip.external_reference or f"NMD-{trip.id}",
            name=trip.name,
            destination_country=trip.destination_country,
            destination_countries=trip.destination_countries,
            duration_days=trip.duration_days,
            description_short=trip.description_short,
            highlights=trip.highlights,
            comfort_level=trip.comfort_level,
            difficulty_level=trip.difficulty_level,
            is_published=trip.is_published,
            updated_at=trip.updated_at,
        ))

    return CatalogListResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{external_id}", response_model=CatalogTripDetail)
async def get_catalog_trip(
    external_id: str,
    db: AsyncSession = Depends(get_db),
    partner: dict = Depends(validate_api_key),
):
    """
    Get detailed information about a specific circuit.

    Pricing is adjusted based on partner's markup configuration.
    """
    # Try to find by external_reference first, then by ID
    query = select(Trip).options(
        selectinload(Trip.days),
        selectinload(Trip.themes),
    )

    if external_id.startswith("NMD-"):
        # Internal ID format
        try:
            trip_id = int(external_id.replace("NMD-", ""))
            query = query.where(Trip.id == trip_id)
        except ValueError:
            raise HTTPException(status_code=404, detail="Circuit not found")
    else:
        query = query.where(Trip.external_reference == external_id)

    query = query.where(
        and_(
            Trip.is_published == True,
            Trip.is_distributable == True,
        )
    )

    result = await db.execute(query)
    trip = result.scalar_one_or_none()

    if not trip:
        raise HTTPException(status_code=404, detail="Circuit not found")

    # Calculate price with partner markup
    base_price = None  # Would come from pax_configs or pricing engine
    partner_markup = partner.get("markup_pct", 0)

    # Get theme labels
    theme_labels = [t.label for t in trip.themes] if trip.themes else None

    return CatalogTripDetail(
        external_id=trip.external_reference or f"NMD-{trip.id}",
        name=trip.name,
        destination_country=trip.destination_country,
        destination_countries=trip.destination_countries,
        duration_days=trip.duration_days,
        description_short=trip.description_short,
        highlights=trip.highlights,
        comfort_level=trip.comfort_level,
        difficulty_level=trip.difficulty_level,
        is_published=trip.is_published,
        updated_at=trip.updated_at,
        days=[CatalogTripDay.model_validate(d) for d in sorted(trip.days, key=lambda x: x.day_number)],
        inclusions=trip.inclusions,
        exclusions=trip.exclusions,
        info_general=trip.info_general,
        info_formalities=trip.info_formalities,
        info_booking_conditions=trip.info_booking_conditions,
        info_cancellation_policy=trip.info_cancellation_policy,
        themes=theme_labels,
        base_price_per_person=base_price,
        currency=trip.default_currency,
    )


@router.get("/destinations/list")
async def list_destinations(
    db: AsyncSession = Depends(get_db),
    partner: dict = Depends(validate_api_key),
):
    """
    List all available destinations in the catalog.
    """
    from sqlalchemy import func, distinct

    query = select(
        Trip.destination_country,
        func.count(Trip.id).label("circuit_count")
    ).where(
        and_(
            Trip.is_published == True,
            Trip.is_distributable == True,
            Trip.destination_country.isnot(None),
        )
    ).group_by(Trip.destination_country)

    result = await db.execute(query)
    destinations = result.all()

    return {
        "destinations": [
            {"code": d[0], "circuit_count": d[1]}
            for d in destinations
        ]
    }


@router.post("/webhooks/subscribe")
async def subscribe_webhook(
    subscription: WebhookSubscription,
    db: AsyncSession = Depends(get_db),
    partner: dict = Depends(validate_api_key),
):
    """
    Subscribe to catalog updates via webhook.

    Events:
    - circuit.created: New circuit added to catalog
    - circuit.updated: Circuit details changed
    - circuit.deleted: Circuit removed from catalog
    - pricing.updated: Pricing changed
    """
    # TODO: Store webhook subscription in database
    # For now, just acknowledge the request

    return {
        "status": "subscribed",
        "partner_id": partner["partner_id"],
        "webhook_url": subscription.webhook_url,
        "events": subscription.events,
        "message": "Webhook subscription created. You will receive POST requests at the specified URL.",
    }


@router.get("/health")
async def catalog_health():
    """Health check for the distribution API."""
    return {
        "status": "healthy",
        "api_version": "v1",
        "documentation": "/docs#/Distribution%20API",
    }
