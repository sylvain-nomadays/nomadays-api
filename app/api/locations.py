"""
Location management endpoints.
Locations are used to categorize products by destination (Chiang Mai, Bangkok, etc.)
"""

from typing import List, Optional
from decimal import Decimal

from fastapi import APIRouter, HTTPException, status, Query
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload

from app.api.deps import DbSession, CurrentUser, CurrentTenant
from app.models.location import Location
from app.models.content import ContentEntity, ContentTranslation

router = APIRouter()


# ============================================================================
# Schemas
# ============================================================================

class LocationCreate(BaseModel):
    """Create a new location."""
    name: str
    slug: Optional[str] = None
    location_type: str = "city"  # city, region, country, area, neighborhood
    parent_id: Optional[int] = None
    country_code: Optional[str] = None
    lat: Optional[float] = None
    lng: Optional[float] = None
    google_place_id: Optional[str] = None
    description: Optional[str] = None
    sort_order: int = 0


class LocationUpdate(BaseModel):
    """Update a location."""
    name: Optional[str] = None
    slug: Optional[str] = None
    location_type: Optional[str] = None
    parent_id: Optional[int] = None
    country_code: Optional[str] = None
    lat: Optional[float] = None
    lng: Optional[float] = None
    google_place_id: Optional[str] = None
    description: Optional[str] = None
    sort_order: Optional[int] = None
    is_active: Optional[bool] = None


class LocationResponse(BaseModel):
    """Location response."""
    id: int
    tenant_id: str
    name: str
    slug: Optional[str] = None
    location_type: str
    parent_id: Optional[int] = None
    country_code: Optional[str] = None
    lat: Optional[float] = None
    lng: Optional[float] = None
    google_place_id: Optional[str] = None
    description: Optional[str] = None
    content_id: Optional[int] = None
    sort_order: int = 0
    is_active: bool = True
    # Counts
    accommodation_count: int = 0

    class Config:
        from_attributes = True


class LocationListResponse(BaseModel):
    """Paginated list response."""
    items: List[LocationResponse]
    total: int
    page: int
    page_size: int


# ============================================================================
# Helper Functions
# ============================================================================

async def _auto_link_content(db, tenant_id, location: Location) -> Optional[int]:
    """
    Auto-link a Location to a ContentEntity of type 'destination'
    by matching Location.name with ContentTranslation.title (case-insensitive).

    Returns the content entity id if linked, None otherwise.
    """
    # Find ContentEntity of type 'destination' that has a translation with matching title
    # and no location_id yet
    result = await db.execute(
        select(ContentEntity)
        .join(ContentTranslation, ContentTranslation.entity_id == ContentEntity.id)
        .where(
            ContentEntity.tenant_id == tenant_id,
            ContentEntity.entity_type == "destination",
            ContentEntity.location_id.is_(None),
            func.lower(ContentTranslation.title) == func.lower(location.name),
        )
        .limit(1)
    )
    content = result.scalar_one_or_none()

    if content:
        content.location_id = location.id
        return content.id

    return None


def location_to_response(location: Location, accommodation_count: int = 0) -> dict:
    """Convert Location model to response dict."""
    return {
        "id": location.id,
        "tenant_id": str(location.tenant_id),
        "name": location.name,
        "slug": location.slug,
        "location_type": location.location_type,
        "parent_id": location.parent_id,
        "country_code": location.country_code,
        "lat": float(location.lat) if location.lat else None,
        "lng": float(location.lng) if location.lng else None,
        "google_place_id": location.google_place_id,
        "description": location.description,
        "content_id": location.content_id,
        "sort_order": location.sort_order,
        "is_active": location.is_active,
        "accommodation_count": accommodation_count,
    }


# ============================================================================
# Endpoints
# ============================================================================

@router.get("", response_model=LocationListResponse)
async def list_locations(
    db: DbSession,
    tenant: CurrentTenant,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    location_type: Optional[str] = None,
    country_code: Optional[str] = None,
    parent_id: Optional[int] = None,
    search: Optional[str] = None,
    is_active: Optional[bool] = None,
):
    """
    List locations for the current tenant.
    Supports filtering by type, country, parent, and search.
    """
    # Base query
    query = select(Location).where(Location.tenant_id == tenant.id)

    # Filters
    if location_type:
        query = query.where(Location.location_type == location_type)
    if country_code:
        query = query.where(Location.country_code == country_code)
    if parent_id is not None:
        query = query.where(Location.parent_id == parent_id)
    if search:
        query = query.where(Location.name.ilike(f"%{search}%"))
    if is_active is not None:
        query = query.where(Location.is_active == is_active)

    # Count total
    count_query = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_query)).scalar()

    # Pagination and ordering
    query = query.order_by(Location.sort_order, Location.name)
    query = query.offset((page - 1) * page_size).limit(page_size)

    result = await db.execute(query)
    locations = result.scalars().all()

    return LocationListResponse(
        items=[location_to_response(loc) for loc in locations],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post("", response_model=LocationResponse, status_code=status.HTTP_201_CREATED)
async def create_location(
    data: LocationCreate,
    db: DbSession,
    tenant: CurrentTenant,
    user: CurrentUser,
):
    """Create a new location."""
    # Auto-capitalize name (e.g. "bangkok" → "Bangkok", "chiang mai" → "Chiang Mai")
    name = data.name.strip().title()

    # Generate slug if not provided
    slug = data.slug
    if not slug:
        slug = name.lower().replace(" ", "-").replace("'", "")

    location = Location(
        tenant_id=tenant.id,
        name=name,
        slug=slug,
        location_type=data.location_type,
        parent_id=data.parent_id,
        country_code=data.country_code,
        lat=Decimal(str(data.lat)) if data.lat else None,
        lng=Decimal(str(data.lng)) if data.lng else None,
        google_place_id=data.google_place_id,
        description=data.description,
        sort_order=data.sort_order,
    )

    db.add(location)
    await db.commit()
    await db.refresh(location)

    # Auto-link to ContentEntity destination with same name
    content_id = await _auto_link_content(db, tenant.id, location)
    if content_id:
        await db.commit()

    return location_to_response(location)


@router.get("/{location_id}", response_model=LocationResponse)
async def get_location(
    location_id: int,
    db: DbSession,
    tenant: CurrentTenant,
):
    """Get a specific location."""
    result = await db.execute(
        select(Location).where(
            Location.id == location_id,
            Location.tenant_id == tenant.id,
        )
    )
    location = result.scalar_one_or_none()

    if not location:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Location not found",
        )

    return location_to_response(location)


@router.patch("/{location_id}", response_model=LocationResponse)
async def update_location(
    location_id: int,
    data: LocationUpdate,
    db: DbSession,
    tenant: CurrentTenant,
    user: CurrentUser,
):
    """Update a location."""
    result = await db.execute(
        select(Location).where(
            Location.id == location_id,
            Location.tenant_id == tenant.id,
        )
    )
    location = result.scalar_one_or_none()

    if not location:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Location not found",
        )

    # Update fields
    update_data = data.model_dump(exclude_unset=True)

    # Auto-capitalize name
    if "name" in update_data and update_data["name"]:
        update_data["name"] = update_data["name"].strip().title()

    for field, value in update_data.items():
        if field in ["lat", "lng"] and value is not None:
            value = Decimal(str(value))
        setattr(location, field, value)

    await db.commit()
    await db.refresh(location)

    return location_to_response(location)


@router.delete("/{location_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_location(
    location_id: int,
    db: DbSession,
    tenant: CurrentTenant,
    user: CurrentUser,
):
    """Delete a location (soft delete)."""
    result = await db.execute(
        select(Location).where(
            Location.id == location_id,
            Location.tenant_id == tenant.id,
        )
    )
    location = result.scalar_one_or_none()

    if not location:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Location not found",
        )

    # Soft delete
    location.is_active = False
    await db.commit()


@router.get("/by-country/{country_code}", response_model=List[LocationResponse])
async def list_locations_by_country(
    country_code: str,
    db: DbSession,
    tenant: CurrentTenant,
    location_type: Optional[str] = None,
):
    """List all locations for a specific country."""
    query = select(Location).where(
        Location.tenant_id == tenant.id,
        Location.country_code == country_code.upper(),
        Location.is_active == True,
    )

    if location_type:
        query = query.where(Location.location_type == location_type)

    query = query.order_by(Location.sort_order, Location.name)

    result = await db.execute(query)
    locations = result.scalars().all()

    return [location_to_response(loc) for loc in locations]


# ============================================================================
# Content Sync
# ============================================================================

class SyncContentResponse(BaseModel):
    """Response for content sync operation."""
    linked: int
    details: List[dict]


@router.post("/sync-content", response_model=SyncContentResponse)
async def sync_content_locations(
    db: DbSession,
    tenant: CurrentTenant,
    user: CurrentUser,
):
    """
    Batch-link ContentEntity destinations to Locations by matching names.

    For each ContentEntity of type 'destination' without a location_id,
    search for a Location with the same name (case-insensitive).
    If found, set content.location_id = location.id.
    """
    # Get all destination content entities without a location_id
    content_result = await db.execute(
        select(ContentEntity, ContentTranslation.title)
        .join(ContentTranslation, ContentTranslation.entity_id == ContentEntity.id)
        .where(
            ContentEntity.tenant_id == tenant.id,
            ContentEntity.entity_type == "destination",
            ContentEntity.location_id.is_(None),
            ContentTranslation.is_primary == True,
        )
    )
    unlinked_contents = content_result.all()

    # Get all active locations for this tenant
    loc_result = await db.execute(
        select(Location).where(
            Location.tenant_id == tenant.id,
            Location.is_active == True,
        )
    )
    locations = loc_result.scalars().all()

    # Build a lookup map: lowercase name → Location
    location_map = {}
    for loc in locations:
        location_map[loc.name.lower()] = loc

    linked_count = 0
    details = []

    for content_entity, title in unlinked_contents:
        # Try matching by title (case-insensitive)
        matched_location = location_map.get(title.lower())

        if matched_location:
            content_entity.location_id = matched_location.id
            linked_count += 1
            details.append({
                "content_title": title,
                "location_name": matched_location.name,
                "location_id": matched_location.id,
            })

    if linked_count > 0:
        await db.commit()

    return SyncContentResponse(
        linked=linked_count,
        details=details,
    )
