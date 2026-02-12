"""
Location management endpoints.
Locations are used to categorize products by destination (Chiang Mai, Bangkok, etc.)
Includes photo upload and management for location illustrations.
"""

from typing import List, Optional, Dict
from decimal import Decimal
from datetime import datetime

from fastapi import APIRouter, HTTPException, status, Query, File, UploadFile, Form
from pydantic import BaseModel
from sqlalchemy import select, func, update as sa_update
from sqlalchemy.orm import selectinload

from app.api.deps import DbSession, CurrentUser, CurrentTenant
from app.models.location import Location
from app.models.location_photo import LocationPhoto
from app.models.content import ContentEntity, ContentTranslation
from app.services.storage import (
    upload_to_supabase_generic,
    delete_from_supabase,
    get_mime_type,
    get_supabase_client,
    BUCKET_NAME,
)
from app.services.image_processor import process_image_minimal, process_image

import logging

logger = logging.getLogger(__name__)

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


class LocationPhotoResponse(BaseModel):
    """Location photo response."""
    id: int
    location_id: int
    url: str
    thumbnail_url: Optional[str] = None
    url_avif: Optional[str] = None
    url_webp: Optional[str] = None
    url_medium: Optional[str] = None
    url_large: Optional[str] = None
    lqip_data_url: Optional[str] = None
    original_filename: Optional[str] = None
    file_size: Optional[int] = None
    mime_type: Optional[str] = None
    width: Optional[int] = None
    height: Optional[int] = None
    caption: Optional[str] = None
    alt_text: Optional[str] = None
    is_main: bool = False
    sort_order: int = 0
    created_at: Optional[str] = None

    class Config:
        from_attributes = True


class UpdateLocationPhotoRequest(BaseModel):
    """Update photo metadata."""
    caption: Optional[str] = None
    alt_text: Optional[str] = None
    is_main: Optional[bool] = None
    sort_order: Optional[int] = None


class ReorderLocationPhotosRequest(BaseModel):
    """Reorder photos by providing ordered list of photo IDs."""
    photo_ids: List[int]


class PhotosByIdsRequest(BaseModel):
    """Request photos for multiple location IDs."""
    location_ids: List[int]


class LocationListResponse(BaseModel):
    """Paginated list response."""
    items: List[LocationResponse]
    total: int
    page: int
    page_size: int


# ============================================================================
# Schemas — AI Destination Suggestions
# ============================================================================

class DestinationSuggestRequest(BaseModel):
    """Request to suggest destinations for a country via AI."""
    country_code: str  # ISO 2-letter code, e.g. "TH"
    count: int = 20  # 10-30


class SuggestedDestinationResponse(BaseModel):
    """A single suggested destination."""
    name: str
    location_type: str
    description_fr: str
    description_en: str
    sort_order: int
    country_code: str
    lat: Optional[float] = None
    lng: Optional[float] = None
    google_place_id: Optional[str] = None
    formatted_address: Optional[str] = None
    geocoding_success: bool = False


class DestinationSuggestResponse(BaseModel):
    """Response containing suggested destinations."""
    country_code: str
    country_name: str
    suggestions: List[SuggestedDestinationResponse]
    total: int


class BulkDestinationItem(BaseModel):
    """A single destination to create in bulk."""
    name: str
    location_type: str = "city"
    country_code: str
    description_fr: str
    description_en: str
    sort_order: int = 0
    lat: Optional[float] = None
    lng: Optional[float] = None
    google_place_id: Optional[str] = None


class BulkCreateDestinationsRequest(BaseModel):
    """Request to bulk-create destinations with content pages."""
    destinations: List[BulkDestinationItem]


class BulkCreateDestinationsResponse(BaseModel):
    """Response from bulk destination creation."""
    created: int
    locations: List[LocationResponse]
    content_entities_created: int


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


def _photo_to_response(photo: LocationPhoto) -> dict:
    """Convert LocationPhoto model to response dict."""
    return {
        "id": photo.id,
        "location_id": photo.location_id,
        "url": photo.url,
        "thumbnail_url": photo.thumbnail_url,
        "url_avif": photo.url_avif,
        "url_webp": photo.url_webp,
        "url_medium": photo.url_medium,
        "url_large": photo.url_large,
        "lqip_data_url": photo.lqip_data_url,
        "original_filename": photo.original_filename,
        "file_size": photo.file_size,
        "mime_type": photo.mime_type,
        "width": photo.width,
        "height": photo.height,
        "caption": photo.caption,
        "alt_text": photo.alt_text,
        "is_main": photo.is_main,
        "sort_order": photo.sort_order,
        "created_at": photo.created_at.isoformat() if photo.created_at else None,
    }


def location_to_response(location: Location, accommodation_count: int = 0, photos: Optional[List[LocationPhoto]] = None) -> dict:
    """Convert Location model to response dict."""
    resp = {
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
    if photos is not None:
        resp["photos"] = [_photo_to_response(p) for p in photos]
    return resp


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


# ============================================================================
# AI Destination Suggestions (MUST be before /{location_id} routes)
# ============================================================================

@router.post("/suggest", response_model=DestinationSuggestResponse)
async def suggest_destinations(
    data: DestinationSuggestRequest,
    db: DbSession,
    tenant: CurrentTenant,
    user: CurrentUser,
):
    """
    Use Claude AI to suggest tourist destinations for a country,
    then geocode each one via Google Maps.

    Returns a list of suggestions for admin review before bulk creation.
    Typically takes ~15-20 seconds (Claude + parallel geocoding).
    """
    from app.services.destination_suggester import (
        get_destination_suggester,
        get_country_name,
    )

    country_code = data.country_code.upper()
    country_name = get_country_name(country_code)
    count = max(10, min(data.count, 30))

    try:
        suggester = get_destination_suggester()
        suggestions = await suggester.suggest(
            country_code=country_code,
            country_name=country_name,
            count=count,
        )
    except Exception as e:
        logger.error(f"Destination suggestion failed for {country_code}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"AI suggestion failed: {str(e)}",
        )

    try:
        response = DestinationSuggestResponse(
            country_code=country_code,
            country_name=country_name,
            suggestions=[
                SuggestedDestinationResponse(
                    name=s.name,
                    location_type=s.location_type,
                    description_fr=s.description_fr,
                    description_en=s.description_en,
                    sort_order=s.sort_order,
                    country_code=s.country_code,
                    lat=float(s.lat) if s.lat is not None else None,
                    lng=float(s.lng) if s.lng is not None else None,
                    google_place_id=s.google_place_id,
                    formatted_address=s.formatted_address,
                    geocoding_success=s.geocoding_success,
                )
                for s in suggestions
            ],
            total=len(suggestions),
        )
        logger.info(f"Returning {len(suggestions)} suggestions for {country_name}")
        return response
    except Exception as e:
        logger.error(f"Failed to build response for {country_code}: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Response serialization failed: {str(e)}",
        )


@router.post("/bulk-create", response_model=BulkCreateDestinationsResponse)
async def bulk_create_destinations(
    data: BulkCreateDestinationsRequest,
    db: DbSession,
    tenant: CurrentTenant,
    user: CurrentUser,
):
    """
    Bulk-create destinations from AI suggestions.

    For each destination:
    1. Creates a Location (name, slug, type, country_code, lat/lng, google_place_id)
    2. Creates a ContentEntity (type="destination", status="draft", linked to location)
    3. Creates ContentTranslation FR (is_primary=True, title, slug, excerpt)
    4. Creates ContentTranslation EN (title, slug, excerpt)

    The admin can then enrich content and upload/generate photos.
    """
    import uuid
    from app.services.destination_suggester import make_slug

    if not data.destinations:
        return BulkCreateDestinationsResponse(
            created=0,
            locations=[],
            content_entities_created=0,
        )

    created_locations = []
    content_entities_created = 0

    for item in data.destinations:
        # 1. Create Location
        name = item.name.strip().title()
        slug = make_slug(name)

        location = Location(
            tenant_id=tenant.id,
            name=name,
            slug=slug,
            location_type=item.location_type,
            country_code=item.country_code.upper(),
            lat=Decimal(str(item.lat)) if item.lat else None,
            lng=Decimal(str(item.lng)) if item.lng else None,
            google_place_id=item.google_place_id,
            description=item.description_fr,
            sort_order=item.sort_order,
        )
        db.add(location)
        await db.flush()  # Get location.id without committing

        # 2. Create ContentEntity (draft destination page)
        content_entity = ContentEntity(
            id=uuid.uuid4(),
            tenant_id=tenant.id,
            entity_type="destination",
            status="draft",
            location_id=location.id,
            lat=item.lat,
            lng=item.lng,
            google_place_id=item.google_place_id,
            created_by=user.id,
            updated_by=user.id,
        )
        db.add(content_entity)
        await db.flush()

        # 3. Create ContentTranslation FR (primary)
        trans_fr = ContentTranslation(
            id=uuid.uuid4(),
            entity_id=content_entity.id,
            language_code="fr",
            title=name,
            slug=slug,
            excerpt=item.description_fr,
            is_primary=True,
        )
        db.add(trans_fr)

        # 4. Create ContentTranslation EN
        trans_en = ContentTranslation(
            id=uuid.uuid4(),
            entity_id=content_entity.id,
            language_code="en",
            title=name,
            slug=slug,
            excerpt=item.description_en,
            is_primary=False,
        )
        db.add(trans_en)

        # Note: Location.content_id is BigInteger (legacy field, not FK to content_entities UUID)
        # The link is maintained via ContentEntity.location_id → Location.id instead.

        content_entities_created += 1
        created_locations.append(location)

    # Commit all at once (atomic transaction)
    await db.commit()

    # Refresh all locations to get final state
    for loc in created_locations:
        await db.refresh(loc)

    logger.info(
        f"Bulk created {len(created_locations)} locations + "
        f"{content_entities_created} content entities for tenant {tenant.id}"
    )

    return BulkCreateDestinationsResponse(
        created=len(created_locations),
        locations=[location_to_response(loc) for loc in created_locations],
        content_entities_created=content_entities_created,
    )


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


# ============================================================================
# Location Photos
# ============================================================================

@router.get("/{location_id}/photos", response_model=List[LocationPhotoResponse])
async def list_location_photos(
    location_id: int,
    db: DbSession,
    tenant: CurrentTenant,
):
    """List all photos for a location, ordered by sort_order."""
    # Verify location exists and belongs to tenant
    loc_result = await db.execute(
        select(Location).where(
            Location.id == location_id,
            Location.tenant_id == tenant.id,
        )
    )
    if not loc_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Location not found")

    result = await db.execute(
        select(LocationPhoto)
        .where(
            LocationPhoto.location_id == location_id,
            LocationPhoto.tenant_id == tenant.id,
        )
        .order_by(LocationPhoto.sort_order)
    )
    photos = result.scalars().all()

    return [_photo_to_response(p) for p in photos]


@router.post("/{location_id}/photos", response_model=LocationPhotoResponse)
async def upload_location_photo(
    location_id: int,
    file: UploadFile = File(...),
    caption: Optional[str] = Form(None),
    alt_text: Optional[str] = Form(None),
    is_main: bool = Form(False),
    db: DbSession = None,
    tenant: CurrentTenant = None,
    user: CurrentUser = None,
):
    """Upload a new photo for a location."""
    # Verify location exists and belongs to tenant
    loc_result = await db.execute(
        select(Location).where(
            Location.id == location_id,
            Location.tenant_id == tenant.id,
        )
    )
    location = loc_result.scalar_one_or_none()
    if not location:
        raise HTTPException(status_code=404, detail="Location not found")

    # Read file content
    file_content = await file.read()
    file_size = len(file_content)
    mime_type = file.content_type or get_mime_type(file.filename or "image.jpg")

    try:
        # Upload to Supabase Storage
        folder_path = f"photos/{tenant.id}/locations/{location_id}"
        storage_path, public_url = await upload_to_supabase_generic(
            file_content=file_content,
            original_filename=file.filename or "image.jpg",
            folder_path=folder_path,
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
        import logging
        logging.warning(f"Image processing failed for {storage_path}: {e}")

    # If this is set as main photo, unset existing main photos
    if is_main:
        await db.execute(
            sa_update(LocationPhoto)
            .where(
                LocationPhoto.location_id == location_id,
                LocationPhoto.is_main == True,
            )
            .values(is_main=False)
        )

    # Get next sort_order
    sort_result = await db.execute(
        select(LocationPhoto.sort_order)
        .where(LocationPhoto.location_id == location_id)
        .order_by(LocationPhoto.sort_order.desc())
        .limit(1)
    )
    max_sort = sort_result.scalar_one_or_none()
    next_sort = (max_sort or 0) + 1

    # Create photo record
    photo = LocationPhoto(
        tenant_id=tenant.id,
        location_id=location_id,
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
        alt_text=alt_text or location.name,
        is_main=is_main,
        sort_order=next_sort,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )

    db.add(photo)
    await db.commit()
    await db.refresh(photo)

    return _photo_to_response(photo)


@router.patch("/{location_id}/photos/{photo_id}", response_model=LocationPhotoResponse)
async def update_location_photo(
    location_id: int,
    photo_id: int,
    data: UpdateLocationPhotoRequest,
    db: DbSession,
    tenant: CurrentTenant,
    user: CurrentUser,
):
    """Update photo metadata (caption, alt_text, is_main, sort_order)."""
    # Find the photo
    result = await db.execute(
        select(LocationPhoto)
        .join(Location)
        .where(
            LocationPhoto.id == photo_id,
            LocationPhoto.location_id == location_id,
            Location.tenant_id == tenant.id,
        )
    )
    photo = result.scalar_one_or_none()

    if not photo:
        raise HTTPException(status_code=404, detail="Photo not found")

    # If setting as main, unset other main photos
    if data.is_main is True:
        await db.execute(
            sa_update(LocationPhoto)
            .where(
                LocationPhoto.location_id == location_id,
                LocationPhoto.is_main == True,
                LocationPhoto.id != photo_id,
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

    return _photo_to_response(photo)


@router.delete("/{location_id}/photos/{photo_id}")
async def delete_location_photo(
    location_id: int,
    photo_id: int,
    db: DbSession,
    tenant: CurrentTenant,
    user: CurrentUser,
):
    """Delete a photo from a location."""
    # Find the photo
    result = await db.execute(
        select(LocationPhoto)
        .join(Location)
        .where(
            LocationPhoto.id == photo_id,
            LocationPhoto.location_id == location_id,
            Location.tenant_id == tenant.id,
        )
    )
    photo = result.scalar_one_or_none()

    if not photo:
        raise HTTPException(status_code=404, detail="Photo not found")

    # Delete from storage
    try:
        await delete_from_supabase(photo.storage_path)
    except Exception as e:
        import logging
        logging.warning(f"Failed to delete from storage: {e}")

    # Delete from database
    await db.delete(photo)
    await db.commit()

    return {"message": "Photo deleted successfully"}


@router.post("/{location_id}/photos/reorder")
async def reorder_location_photos(
    location_id: int,
    data: ReorderLocationPhotosRequest,
    db: DbSession,
    tenant: CurrentTenant,
    user: CurrentUser,
):
    """Reorder photos by providing an ordered list of photo IDs."""
    # Verify location
    loc_result = await db.execute(
        select(Location).where(
            Location.id == location_id,
            Location.tenant_id == tenant.id,
        )
    )
    if not loc_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Location not found")

    # Update sort_order for each photo
    for index, photo_id in enumerate(data.photo_ids):
        await db.execute(
            sa_update(LocationPhoto)
            .where(
                LocationPhoto.id == photo_id,
                LocationPhoto.location_id == location_id,
            )
            .values(sort_order=index)
        )

    await db.commit()

    return {"message": "Photos reordered successfully"}


# ============================================================================
# Batch Photos (for circuit editor)
# ============================================================================

@router.post("/photos-by-ids")
async def get_photos_by_location_ids(
    data: PhotosByIdsRequest,
    db: DbSession,
    tenant: CurrentTenant,
):
    """
    Get photos for multiple locations in a single request.
    Used by the circuit editor to load all location photos at once.

    Returns a dict: { location_id: [photo1, photo2, ...] }
    """
    if not data.location_ids:
        return {}

    result = await db.execute(
        select(LocationPhoto)
        .where(
            LocationPhoto.tenant_id == tenant.id,
            LocationPhoto.location_id.in_(data.location_ids),
        )
        .order_by(LocationPhoto.location_id, LocationPhoto.sort_order)
    )
    photos = result.scalars().all()

    # Group by location_id
    grouped: Dict[int, list] = {lid: [] for lid in data.location_ids}
    for photo in photos:
        if photo.location_id in grouped:
            grouped[photo.location_id].append(_photo_to_response(photo))

    return grouped


# ============================================================================
# AI Photo Generation
# ============================================================================

class GenerateLocationPhotoRequest(BaseModel):
    """Request to generate a location photo via AI."""
    prompt: Optional[str] = None
    negative_prompt: Optional[str] = None
    quality: str = "high"  # "high" or "fast"
    scene_type: Optional[str] = None  # temple, beach, mountain, city, etc.
    style: Optional[str] = None  # photorealistic, cinematic, etc.


@router.post("/{location_id}/photos/generate-ai", response_model=LocationPhotoResponse)
async def generate_location_photo_ai(
    location_id: int,
    data: GenerateLocationPhotoRequest,
    db: DbSession,
    tenant: CurrentTenant,
    user: CurrentUser,
):
    """
    Generate a photo for a location using Vertex AI (Imagen 3).

    If no prompt is provided, one is automatically built from the location's
    name, type, country, and description.
    """
    from app.services.vertex_ai import ImageGenerationService, get_image_generation_service
    from app.services.circuit_image_generator import (
        COUNTRY_DESTINATIONS,
        SCENE_KEYWORDS,
        DEFAULT_SCENE,
        slugify,
        upload_seo_image,
    )

    # Verify location exists and belongs to tenant
    loc_result = await db.execute(
        select(Location).where(
            Location.id == location_id,
            Location.tenant_id == tenant.id,
        )
    )
    location = loc_result.scalar_one_or_none()
    if not location:
        raise HTTPException(status_code=404, detail="Location not found")

    # Build prompt if not provided
    if data.prompt:
        prompt = data.prompt
        negative_prompt = data.negative_prompt or (
            "blurry, low quality, distorted, ugly, watermark, text, logo, "
            "fictional place, imaginary location, AI artifacts, unrealistic colors"
        )
    else:
        # Auto-build prompt from location metadata
        destination_name = COUNTRY_DESTINATIONS.get(
            (location.country_code or "").upper(), ""
        )
        if not destination_name:
            destination_name = (location.country_code or "destination").lower()

        # Determine scene type from location type, description, or explicit param
        scene_type = data.scene_type
        style = data.style or "photorealistic"

        if not scene_type:
            # Try to infer from location description
            text = f"{location.name} {location.description or ''}".lower()
            best_scene = None
            best_score = 0
            for _scene_name, scene_info in SCENE_KEYWORDS.items():
                score = sum(1 for kw in scene_info["keywords"] if kw in text)
                if score > best_score:
                    best_score = score
                    best_scene = scene_info

            if best_scene and best_score > 0:
                scene_type = best_scene["scene_type"]
                style = data.style or best_scene["style"]
                time_of_day = best_scene["time_of_day"]
            else:
                scene = DEFAULT_SCENE
                scene_type = scene["scene_type"]
                time_of_day = scene["time_of_day"]
        else:
            time_of_day = "golden hour"

        # Build style description
        style_map = {
            "cinematic": "cinematic lighting, movie scene quality, dramatic atmosphere",
            "photorealistic": "ultra realistic, high resolution, professional DSLR photo quality",
            "dramatic": "dramatic lighting, epic scale, awe-inspiring composition",
            "documentary": "authentic documentary style, natural lighting, candid atmosphere",
            "vibrant": "vibrant saturated colors, energetic composition, lively atmosphere",
            "aerial view": "aerial drone perspective, bird's eye view, sweeping landscape",
        }
        style_desc = style_map.get(style, "professional photography, high quality")

        location_desc = f"{location.name}, {destination_name.replace('-', ' ').title()}"

        prompt = f"""Photorealistic image of the real existing place {location_desc},
exactly as it looks in reality, famous landmark photography,
{time_of_day} lighting, {style_desc},
accurate representation of the actual location,
travel magazine quality, National Geographic style,
stunning composition, high dynamic range,
professional travel photography, no watermarks, no people"""

        if location.description and len(location.description) > 20:
            context = location.description[:400].strip()
            prompt += f",\nscene details: {context}"

        negative_prompt = (
            "blurry, low quality, distorted, ugly, "
            "watermark, text, logo, signature, overlay, "
            "oversaturated, overexposed, underexposed, "
            "fictional place, imaginary location, fantasy architecture, "
            "AI artifacts, unrealistic colors, impossible geometry, "
            "tourists crowds, modern vehicles in foreground, "
            "stock photo watermark, frame, border, "
            "invented buildings, non-existing landmarks"
        )

    # Initialize Vertex AI service
    if data.quality == "fast":
        image_service = ImageGenerationService(
            model_name=ImageGenerationService.MODEL_IMAGEN_3_FAST
        )
    else:
        image_service = get_image_generation_service()

    # Generate image
    logger.info(
        f"Generating AI photo for location {location_id} ({location.name}): "
        f"prompt={prompt[:100]}..."
    )

    try:
        images = await image_service.generate_image(
            prompt=prompt,
            negative_prompt=negative_prompt,
            number_of_images=1,
            aspect_ratio="16:9",
            guidance_scale=8.0,
        )
    except Exception as e:
        logger.error(f"Vertex AI generation failed for location {location_id}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"AI image generation failed: {str(e)}"
        )

    if not images:
        raise HTTPException(
            status_code=500,
            detail="AI image generation returned no image"
        )

    raw_bytes = image_service.get_image_bytes(images[0])

    # Process image → thumbnail + LQIP for immediate use
    thumbnail_url = None
    lqip_data_url = None
    width = None
    height = None

    try:
        thumbnail_data, medium_data, lqip_data_url, width, height = process_image_minimal(raw_bytes)
    except Exception as e:
        logger.warning(f"Image processing failed: {e}")
        thumbnail_data = None

    # Upload main image to Supabase
    import uuid as uuid_mod
    file_ext = "png"
    unique_name = f"{uuid_mod.uuid4().hex}.{file_ext}"
    folder_path = f"photos/{tenant.id}/locations/{location_id}"
    storage_path = f"{folder_path}/{unique_name}"

    try:
        client = get_supabase_client()
        client.storage.from_(BUCKET_NAME).upload(
            path=storage_path,
            file=raw_bytes,
            file_options={
                "content-type": "image/png",
                "cache-control": "31536000",
            },
        )
        public_url = client.storage.from_(BUCKET_NAME).get_public_url(storage_path)
    except Exception as e:
        logger.error(f"Upload failed for location {location_id}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Image upload failed: {str(e)}"
        )

    # Upload thumbnail
    if thumbnail_data:
        try:
            thumb_path = f"{folder_path}/{uuid_mod.uuid4().hex}_thumbnail.jpg"
            client.storage.from_(BUCKET_NAME).upload(
                path=thumb_path,
                file=thumbnail_data,
                file_options={
                    "content-type": "image/jpeg",
                    "cache-control": "31536000",
                },
            )
            thumbnail_url = client.storage.from_(BUCKET_NAME).get_public_url(thumb_path)
        except Exception as e:
            logger.warning(f"Thumbnail upload failed: {e}")

    # If this is the first photo, set as main
    count_result = await db.execute(
        select(func.count())
        .select_from(LocationPhoto)
        .where(LocationPhoto.location_id == location_id)
    )
    existing_count = count_result.scalar() or 0
    is_main = existing_count == 0

    # Get next sort_order
    sort_result = await db.execute(
        select(LocationPhoto.sort_order)
        .where(LocationPhoto.location_id == location_id)
        .order_by(LocationPhoto.sort_order.desc())
        .limit(1)
    )
    max_sort = sort_result.scalar_one_or_none()
    next_sort = (max_sort or 0) + 1

    # Create photo record
    photo = LocationPhoto(
        tenant_id=tenant.id,
        location_id=location_id,
        storage_path=storage_path,
        url=public_url,
        thumbnail_url=thumbnail_url,
        lqip_data_url=lqip_data_url,
        original_filename=f"ai-generated-{location.name.lower().replace(' ', '-')}.png",
        file_size=len(raw_bytes),
        mime_type="image/png",
        width=width,
        height=height,
        caption=None,
        alt_text=location.name,
        is_main=is_main,
        sort_order=next_sort,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )

    db.add(photo)
    await db.commit()
    await db.refresh(photo)

    logger.info(
        f"AI photo generated for location {location_id} ({location.name}): "
        f"photo_id={photo.id}, url={public_url}"
    )

    return _photo_to_response(photo)
