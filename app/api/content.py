"""
Content Article management endpoints.

Supports multi-language SEO content:
- ContentEntity: Main entities (attractions, destinations, activities, etc.)
- ContentTranslation: Per-language content
- ContentPhoto: Photos with optimized variants
- ContentTag: Hierarchical tags
- ContentRelation: Links between entities
"""

from datetime import datetime
from typing import List, Optional, Dict, Any
from uuid import UUID

from fastapi import APIRouter, HTTPException, status, Query, UploadFile, File, Form
from pydantic import BaseModel, Field
from sqlalchemy import select, func, or_, and_
from sqlalchemy.orm import selectinload

from app.api.deps import DbSession, CurrentUser, CurrentTenant, TenantId
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

router = APIRouter()


# ============================================================================
# Schemas - aligned with frontend types
# ============================================================================

class ContentTranslationBase(BaseModel):
    """Base translation schema."""
    language_code: str = Field(..., min_length=2, max_length=2)
    title: str = Field(..., min_length=1, max_length=255)
    slug: str = Field(..., min_length=1, max_length=255)
    meta_title: Optional[str] = Field(None, max_length=70)
    meta_description: Optional[str] = Field(None, max_length=170)
    excerpt: Optional[str] = Field(None, max_length=500)
    content_markdown: Optional[str] = None
    content_html: Optional[str] = None
    is_primary: bool = False


class ContentTranslationCreate(ContentTranslationBase):
    """Create a translation."""
    pass


class ContentTranslationUpdate(BaseModel):
    """Update a translation."""
    title: Optional[str] = Field(None, max_length=255)
    slug: Optional[str] = Field(None, max_length=255)
    meta_title: Optional[str] = Field(None, max_length=70)
    meta_description: Optional[str] = Field(None, max_length=170)
    excerpt: Optional[str] = Field(None, max_length=500)
    content_markdown: Optional[str] = None
    content_html: Optional[str] = None
    is_primary: Optional[bool] = None


class ContentTranslationResponse(ContentTranslationBase):
    """Translation response."""
    id: str  # UUID as string
    entity_id: str
    word_count: Optional[int] = None
    reading_time_minutes: Optional[int] = None
    ai_generation_status: Optional[str] = None
    ai_generated_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class ContentPhotoResponse(BaseModel):
    """Photo response."""
    id: str
    url: str
    thumbnail_url: Optional[str] = None
    url_avif: Optional[str] = None
    url_webp: Optional[str] = None
    caption_json: Optional[Dict[str, str]] = None
    alt_text_json: Optional[Dict[str, str]] = None
    is_cover: bool = False
    sort_order: int = 0
    width: Optional[int] = None
    height: Optional[int] = None

    class Config:
        from_attributes = True


class ContentTagResponse(BaseModel):
    """Tag response."""
    id: str
    slug: str
    labels: Dict[str, str]  # Renamed from labels_json
    color: Optional[str] = None
    icon: Optional[str] = None

    class Config:
        from_attributes = True


class ContentRelationResponse(BaseModel):
    """Relation response."""
    id: str
    relation_type: str
    sort_order: int = 0
    is_bidirectional: bool = False
    target: Optional["ContentEntityBrief"] = None

    class Config:
        from_attributes = True


class LocationBrief(BaseModel):
    """Brief location info."""
    id: int
    name: str
    country_code: Optional[str] = None
    city: Optional[str] = None

    class Config:
        from_attributes = True


class ContentEntityBrief(BaseModel):
    """Brief entity info for relations."""
    id: str
    entity_type: str
    status: str
    cover_image_url: Optional[str] = None
    translations: Optional[List[ContentTranslationResponse]] = None

    class Config:
        from_attributes = True


# Update forward reference
ContentRelationResponse.model_rebuild()


class ContentEntityCreate(BaseModel):
    """Create a content entity."""
    entity_type: str = Field(..., description="attraction, destination, activity, accommodation, eating, region")
    status: str = "draft"
    # Location
    location_id: Optional[int] = None
    lat: Optional[float] = None
    lng: Optional[float] = None
    google_place_id: Optional[str] = None
    address: Optional[str] = None
    # Hierarchy
    parent_id: Optional[str] = None  # UUID as string
    # Linked entities
    supplier_id: Optional[int] = None
    accommodation_id: Optional[int] = None
    # Rating
    rating: Optional[float] = Field(None, ge=0, le=5)
    internal_priority: int = 0
    # Cover image
    cover_image_url: Optional[str] = None
    cover_image_alt: Optional[str] = None
    # Flags
    is_featured: bool = False
    # Initial translation (optional)
    translations: Optional[List[ContentTranslationCreate]] = None
    # Tags
    tag_ids: Optional[List[str]] = None


class ContentEntityUpdate(BaseModel):
    """Update a content entity."""
    entity_type: Optional[str] = None
    status: Optional[str] = None
    location_id: Optional[int] = None
    lat: Optional[float] = None
    lng: Optional[float] = None
    google_place_id: Optional[str] = None
    address: Optional[str] = None
    parent_id: Optional[str] = None
    supplier_id: Optional[int] = None
    accommodation_id: Optional[int] = None
    rating: Optional[float] = Field(None, ge=0, le=5)
    internal_priority: Optional[int] = None
    canonical_url: Optional[str] = None
    meta_robots: Optional[str] = None
    cover_image_url: Optional[str] = None
    cover_image_alt: Optional[str] = None
    is_featured: Optional[bool] = None
    tag_ids: Optional[List[str]] = None


class ContentEntityResponse(BaseModel):
    """Full entity response with relations."""
    id: str
    tenant_id: str
    entity_type: str
    status: str
    # Location
    location_id: Optional[int] = None
    location: Optional[LocationBrief] = None
    lat: Optional[float] = None
    lng: Optional[float] = None
    google_place_id: Optional[str] = None
    address: Optional[str] = None
    # Hierarchy
    parent_id: Optional[str] = None
    # Linked entities
    supplier_id: Optional[int] = None
    accommodation_id: Optional[int] = None
    # Rating
    rating: Optional[float] = None
    rating_count: int = 0
    internal_priority: int = 0
    # SEO
    canonical_url: Optional[str] = None
    meta_robots: str = "index,follow"
    # Cover
    cover_image_url: Optional[str] = None
    cover_image_alt: Optional[str] = None
    # AI
    ai_generation_status: Optional[str] = None
    ai_generated_at: Optional[datetime] = None
    # Flags
    is_featured: bool = False
    view_count: int = 0
    # Relations
    translations: List[ContentTranslationResponse] = []
    photos: List[ContentPhotoResponse] = []
    tags: List[ContentTagResponse] = []
    relations: List[ContentRelationResponse] = []
    # Timestamps
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    published_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class ContentEntityListItem(BaseModel):
    """Brief entity for list views."""
    id: str
    entity_type: str
    status: str
    cover_image_url: Optional[str] = None
    location: Optional[LocationBrief] = None
    rating: Optional[float] = None
    is_featured: bool = False
    view_count: int = 0
    translations: List[ContentTranslationResponse] = []
    tags: List[ContentTagResponse] = []
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class ContentSearchResponse(BaseModel):
    """Paginated search response."""
    items: List[ContentEntityListItem]
    total: int
    page: int
    page_size: int
    has_more: bool


class ContentTagCreate(BaseModel):
    """Create a tag."""
    slug: str = Field(..., min_length=1, max_length=100)
    labels_json: Dict[str, str]
    descriptions_json: Optional[Dict[str, str]] = None
    parent_id: Optional[str] = None
    color: Optional[str] = None
    icon: Optional[str] = None
    sort_order: int = 0


class ContentTagUpdate(BaseModel):
    """Update a tag."""
    slug: Optional[str] = None
    labels_json: Optional[Dict[str, str]] = None
    descriptions_json: Optional[Dict[str, str]] = None
    parent_id: Optional[str] = None
    color: Optional[str] = None
    icon: Optional[str] = None
    sort_order: Optional[int] = None
    is_active: Optional[bool] = None


class ContentRelationCreate(BaseModel):
    """Create a relation between entities."""
    target_entity_id: str
    relation_type: str = Field(..., description="part_of, near, related, see_also, includes")
    sort_order: int = 0
    is_bidirectional: bool = False


# ============================================================================
# Helper functions
# ============================================================================

def entity_to_response(entity: ContentEntity, include_relations: bool = True) -> dict:
    """Convert entity model to response dict."""
    data = {
        "id": str(entity.id),
        "tenant_id": str(entity.tenant_id),
        "entity_type": entity.entity_type,
        "status": entity.status,
        "location_id": entity.location_id,
        "lat": float(entity.lat) if entity.lat else None,
        "lng": float(entity.lng) if entity.lng else None,
        "google_place_id": entity.google_place_id,
        "address": entity.address,
        "parent_id": str(entity.parent_id) if entity.parent_id else None,
        "supplier_id": entity.supplier_id,
        "accommodation_id": entity.accommodation_id,
        "rating": float(entity.rating) if entity.rating else None,
        "rating_count": entity.rating_count or 0,
        "internal_priority": entity.internal_priority or 0,
        "canonical_url": entity.canonical_url,
        "meta_robots": entity.meta_robots or "index,follow",
        "cover_image_url": entity.cover_image_url,
        "cover_image_alt": entity.cover_image_alt,
        "ai_generation_status": entity.ai_generation_status,
        "ai_generated_at": entity.ai_generated_at,
        "is_featured": entity.is_featured or False,
        "view_count": entity.view_count or 0,
        "created_at": entity.created_at,
        "updated_at": entity.updated_at,
        "published_at": entity.published_at,
    }

    # Add translations
    data["translations"] = [
        {
            "id": str(t.id),
            "entity_id": str(t.entity_id),
            "language_code": t.language_code,
            "title": t.title,
            "slug": t.slug,
            "meta_title": t.meta_title,
            "meta_description": t.meta_description,
            "excerpt": t.excerpt,
            "content_markdown": t.content_markdown,
            "content_html": t.content_html,
            "is_primary": t.is_primary or False,
            "word_count": t.word_count,
            "reading_time_minutes": t.reading_time_minutes,
            "ai_generation_status": t.ai_generation_status,
            "ai_generated_at": t.ai_generated_at,
            "created_at": t.created_at,
            "updated_at": t.updated_at,
        }
        for t in entity.translations
    ]

    # Add photos
    data["photos"] = [
        {
            "id": str(p.id),
            "url": p.url,
            "thumbnail_url": p.thumbnail_url,
            "url_avif": p.url_avif,
            "url_webp": p.url_webp,
            "caption_json": p.caption_json,
            "alt_text_json": p.alt_text_json,
            "is_cover": p.is_cover or False,
            "sort_order": p.sort_order or 0,
            "width": p.width,
            "height": p.height,
        }
        for p in entity.photos
    ]

    # Add tags
    data["tags"] = [
        {
            "id": str(t.id),
            "slug": t.slug,
            "labels": t.labels_json,
            "color": t.color,
            "icon": t.icon,
        }
        for t in entity.tags
    ]

    # Add relations if requested
    if include_relations:
        data["relations"] = []
        for r in entity.relations_from:
            rel_data = {
                "id": str(r.id),
                "relation_type": r.relation_type,
                "sort_order": r.sort_order or 0,
                "is_bidirectional": r.is_bidirectional or False,
                "target": None,
            }
            # Include target entity brief if loaded
            if r.target_entity:
                target = r.target_entity
                rel_data["target"] = {
                    "id": str(target.id),
                    "entity_type": target.entity_type,
                    "status": target.status,
                    "cover_image_url": target.cover_image_url,
                    "translations": [
                        {
                            "id": str(t.id),
                            "entity_id": str(t.entity_id),
                            "language_code": t.language_code,
                            "title": t.title,
                            "slug": t.slug,
                            "meta_title": t.meta_title,
                            "meta_description": t.meta_description,
                            "excerpt": t.excerpt,
                            "content_markdown": None,  # Don't include full content
                            "content_html": None,
                            "is_primary": t.is_primary or False,
                            "word_count": t.word_count,
                            "reading_time_minutes": t.reading_time_minutes,
                            "ai_generation_status": t.ai_generation_status,
                            "ai_generated_at": t.ai_generated_at,
                            "created_at": t.created_at,
                            "updated_at": t.updated_at,
                        }
                        for t in target.translations
                    ] if target.translations else [],
                }
            data["relations"].append(rel_data)

    # Add location if loaded
    if entity.location:
        data["location"] = {
            "id": entity.location.id,
            "name": entity.location.name,
            "country_code": entity.location.country_code,
            "city": entity.location.name,
        }

    return data


def entity_to_list_item(entity: ContentEntity) -> dict:
    """Convert entity to list item dict."""
    return {
        "id": str(entity.id),
        "entity_type": entity.entity_type,
        "status": entity.status,
        "cover_image_url": entity.cover_image_url,
        "rating": float(entity.rating) if entity.rating else None,
        "is_featured": entity.is_featured or False,
        "view_count": entity.view_count or 0,
        "created_at": entity.created_at,
        "updated_at": entity.updated_at,
        "location": {
            "id": entity.location.id,
            "name": entity.location.name,
            "country_code": entity.location.country_code,
            "city": entity.location.name,
        } if entity.location else None,
        "translations": [
            {
                "id": str(t.id),
                "entity_id": str(t.entity_id),
                "language_code": t.language_code,
                "title": t.title,
                "slug": t.slug,
                "meta_title": t.meta_title,
                "meta_description": t.meta_description,
                "excerpt": t.excerpt,
                "content_markdown": None,  # Don't include in list
                "content_html": None,
                "is_primary": t.is_primary or False,
                "word_count": t.word_count,
                "reading_time_minutes": t.reading_time_minutes,
                "ai_generation_status": t.ai_generation_status,
                "ai_generated_at": t.ai_generated_at,
                "created_at": t.created_at,
                "updated_at": t.updated_at,
            }
            for t in entity.translations
        ],
        "tags": [
            {
                "id": str(t.id),
                "slug": t.slug,
                "labels": t.labels_json,
                "color": t.color,
                "icon": t.icon,
            }
            for t in entity.tags
        ],
    }


# ============================================================================
# Endpoints - Content Entities
# ============================================================================

@router.get("/entities", response_model=ContentSearchResponse)
async def search_entities(
    db: DbSession,
    tenant_id: TenantId,
    search: Optional[str] = Query(None, description="Search in titles and excerpts"),
    entity_type: Optional[str] = Query(None, description="Filter by entity type"),
    status: Optional[str] = Query(None, description="Filter by status"),
    language_code: str = Query("fr", description="Preferred language for search"),
    parent_id: Optional[str] = Query(None, description="Filter by parent entity"),
    is_featured: Optional[bool] = Query(None, description="Filter featured only"),
    tag_ids: Optional[str] = Query(None, description="Comma-separated tag IDs"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """
    Search and filter content entities.
    """
    # Base query with eager loading
    query = (
        select(ContentEntity)
        .where(ContentEntity.tenant_id == tenant_id)
        .options(
            selectinload(ContentEntity.translations),
            selectinload(ContentEntity.tags),
            selectinload(ContentEntity.location),
        )
    )

    # Apply filters
    if entity_type:
        query = query.where(ContentEntity.entity_type == entity_type)

    if status:
        query = query.where(ContentEntity.status == status)

    if parent_id:
        query = query.where(ContentEntity.parent_id == UUID(parent_id))

    if is_featured is not None:
        query = query.where(ContentEntity.is_featured == is_featured)

    # Search in translations
    if search:
        # Subquery to find entities with matching translations
        search_term = f"%{search}%"
        translation_subquery = (
            select(ContentTranslation.entity_id)
            .where(
                and_(
                    ContentTranslation.language_code == language_code,
                    or_(
                        ContentTranslation.title.ilike(search_term),
                        ContentTranslation.excerpt.ilike(search_term),
                    )
                )
            )
        )
        query = query.where(ContentEntity.id.in_(translation_subquery))

    # Tag filter
    if tag_ids:
        tag_id_list = [UUID(tid.strip()) for tid in tag_ids.split(",")]
        # Subquery to find entities with all specified tags
        tag_subquery = (
            select(content_entity_tags.c.entity_id)
            .where(content_entity_tags.c.tag_id.in_(tag_id_list))
            .group_by(content_entity_tags.c.entity_id)
            .having(func.count(content_entity_tags.c.tag_id) == len(tag_id_list))
        )
        query = query.where(ContentEntity.id.in_(tag_subquery))

    # Count total
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    # Order and paginate
    query = (
        query
        .order_by(ContentEntity.is_featured.desc(), ContentEntity.updated_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )

    result = await db.execute(query)
    entities = result.scalars().all()

    return {
        "items": [entity_to_list_item(e) for e in entities],
        "total": total,
        "page": page,
        "page_size": page_size,
        "has_more": (page * page_size) < total,
    }


@router.get("/entities/{entity_id}", response_model=ContentEntityResponse)
async def get_entity(
    entity_id: str,
    db: DbSession,
    tenant_id: TenantId,
):
    """
    Get a single content entity with all relations.
    """
    query = (
        select(ContentEntity)
        .where(
            ContentEntity.id == UUID(entity_id),
            ContentEntity.tenant_id == tenant_id,
        )
        .options(
            selectinload(ContentEntity.translations),
            selectinload(ContentEntity.photos),
            selectinload(ContentEntity.tags),
            selectinload(ContentEntity.location),
            selectinload(ContentEntity.relations_from).selectinload(
                ContentRelation.target_entity
            ).selectinload(ContentEntity.translations),
        )
    )

    result = await db.execute(query)
    entity = result.scalar_one_or_none()

    if not entity:
        raise HTTPException(status_code=404, detail="Content entity not found")

    return entity_to_response(entity)


@router.post("/entities", response_model=ContentEntityResponse, status_code=201)
async def create_entity(
    data: ContentEntityCreate,
    db: DbSession,
    tenant_id: TenantId,
    user: CurrentUser,
):
    """
    Create a new content entity.
    """
    # Validate entity type
    try:
        ContentEntityType(data.entity_type)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid entity_type. Must be one of: {[e.value for e in ContentEntityType]}"
        )

    # Create entity
    entity = ContentEntity(
        tenant_id=tenant_id,
        entity_type=data.entity_type,
        status=data.status or "draft",
        location_id=data.location_id,
        lat=data.lat,
        lng=data.lng,
        google_place_id=data.google_place_id,
        address=data.address,
        parent_id=UUID(data.parent_id) if data.parent_id else None,
        supplier_id=data.supplier_id,
        accommodation_id=data.accommodation_id,
        rating=data.rating,
        internal_priority=data.internal_priority,
        cover_image_url=data.cover_image_url,
        cover_image_alt=data.cover_image_alt,
        is_featured=data.is_featured,
        created_by=user.id,
        updated_by=user.id,
    )

    db.add(entity)
    await db.flush()

    # Create translations if provided
    if data.translations:
        for t_data in data.translations:
            translation = ContentTranslation(
                entity_id=entity.id,
                language_code=t_data.language_code,
                title=t_data.title,
                slug=t_data.slug,
                meta_title=t_data.meta_title,
                meta_description=t_data.meta_description,
                excerpt=t_data.excerpt,
                content_markdown=t_data.content_markdown,
                content_html=t_data.content_html,
                is_primary=t_data.is_primary,
            )
            db.add(translation)

    # Add tags if provided
    if data.tag_ids:
        for tag_id in data.tag_ids:
            await db.execute(
                content_entity_tags.insert().values(
                    entity_id=entity.id,
                    tag_id=UUID(tag_id),
                )
            )

    await db.commit()

    # Reload with relations
    return await get_entity(str(entity.id), db, tenant_id)


@router.patch("/entities/{entity_id}", response_model=ContentEntityResponse)
async def update_entity(
    entity_id: str,
    data: ContentEntityUpdate,
    db: DbSession,
    tenant_id: TenantId,
    user: CurrentUser,
):
    """
    Update a content entity.
    """
    result = await db.execute(
        select(ContentEntity).where(
            ContentEntity.id == UUID(entity_id),
            ContentEntity.tenant_id == tenant_id,
        )
    )
    entity = result.scalar_one_or_none()

    if not entity:
        raise HTTPException(status_code=404, detail="Content entity not found")

    # Update fields
    update_data = data.model_dump(exclude_unset=True)

    for field, value in update_data.items():
        if field == "tag_ids":
            continue  # Handle separately
        if field == "parent_id" and value:
            value = UUID(value)
        setattr(entity, field, value)

    entity.updated_by = user.id

    # Update status timestamp
    if data.status == "published" and entity.published_at is None:
        entity.published_at = datetime.utcnow()

    # Update tags if provided
    if data.tag_ids is not None:
        # Remove existing tags
        await db.execute(
            content_entity_tags.delete().where(
                content_entity_tags.c.entity_id == entity.id
            )
        )
        # Add new tags
        for tag_id in data.tag_ids:
            await db.execute(
                content_entity_tags.insert().values(
                    entity_id=entity.id,
                    tag_id=UUID(tag_id),
                )
            )

    await db.commit()

    return await get_entity(entity_id, db, tenant_id)


@router.delete("/entities/{entity_id}", status_code=204)
async def delete_entity(
    entity_id: str,
    db: DbSession,
    tenant_id: TenantId,
):
    """
    Delete a content entity (cascades to translations, photos, relations).
    """
    result = await db.execute(
        select(ContentEntity).where(
            ContentEntity.id == UUID(entity_id),
            ContentEntity.tenant_id == tenant_id,
        )
    )
    entity = result.scalar_one_or_none()

    if not entity:
        raise HTTPException(status_code=404, detail="Content entity not found")

    await db.delete(entity)
    await db.commit()


# ============================================================================
# Endpoints - Translations
# ============================================================================

@router.get("/entities/{entity_id}/translations", response_model=List[ContentTranslationResponse])
async def get_translations(
    entity_id: str,
    db: DbSession,
    tenant_id: TenantId,
):
    """
    Get all translations for an entity.
    """
    # Verify entity exists and belongs to tenant
    entity_result = await db.execute(
        select(ContentEntity.id).where(
            ContentEntity.id == UUID(entity_id),
            ContentEntity.tenant_id == tenant_id,
        )
    )
    if not entity_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Content entity not found")

    result = await db.execute(
        select(ContentTranslation).where(ContentTranslation.entity_id == UUID(entity_id))
    )
    translations = result.scalars().all()

    return [
        {
            "id": str(t.id),
            "entity_id": str(t.entity_id),
            "language_code": t.language_code,
            "title": t.title,
            "slug": t.slug,
            "meta_title": t.meta_title,
            "meta_description": t.meta_description,
            "excerpt": t.excerpt,
            "content_markdown": t.content_markdown,
            "content_html": t.content_html,
            "is_primary": t.is_primary or False,
            "word_count": t.word_count,
            "reading_time_minutes": t.reading_time_minutes,
            "ai_generation_status": t.ai_generation_status,
            "ai_generated_at": t.ai_generated_at,
            "created_at": t.created_at,
            "updated_at": t.updated_at,
        }
        for t in translations
    ]


@router.post("/entities/{entity_id}/translations", response_model=ContentTranslationResponse, status_code=201)
async def create_translation(
    entity_id: str,
    data: ContentTranslationCreate,
    db: DbSession,
    tenant_id: TenantId,
):
    """
    Create a new translation for an entity.
    """
    # Verify entity exists
    entity_result = await db.execute(
        select(ContentEntity.id).where(
            ContentEntity.id == UUID(entity_id),
            ContentEntity.tenant_id == tenant_id,
        )
    )
    if not entity_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Content entity not found")

    # Check if translation already exists for this language
    existing = await db.execute(
        select(ContentTranslation).where(
            ContentTranslation.entity_id == UUID(entity_id),
            ContentTranslation.language_code == data.language_code,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=400,
            detail=f"Translation for language '{data.language_code}' already exists"
        )

    translation = ContentTranslation(
        entity_id=UUID(entity_id),
        language_code=data.language_code,
        title=data.title,
        slug=data.slug,
        meta_title=data.meta_title,
        meta_description=data.meta_description,
        excerpt=data.excerpt,
        content_markdown=data.content_markdown,
        content_html=data.content_html,
        is_primary=data.is_primary,
    )

    db.add(translation)
    await db.commit()
    await db.refresh(translation)

    return {
        "id": str(translation.id),
        "entity_id": str(translation.entity_id),
        "language_code": translation.language_code,
        "title": translation.title,
        "slug": translation.slug,
        "meta_title": translation.meta_title,
        "meta_description": translation.meta_description,
        "excerpt": translation.excerpt,
        "content_markdown": translation.content_markdown,
        "content_html": translation.content_html,
        "is_primary": translation.is_primary or False,
        "word_count": translation.word_count,
        "reading_time_minutes": translation.reading_time_minutes,
        "ai_generation_status": translation.ai_generation_status,
        "ai_generated_at": translation.ai_generated_at,
        "created_at": translation.created_at,
        "updated_at": translation.updated_at,
    }


@router.patch("/entities/{entity_id}/translations/{language_code}", response_model=ContentTranslationResponse)
async def update_translation(
    entity_id: str,
    language_code: str,
    data: ContentTranslationUpdate,
    db: DbSession,
    tenant_id: TenantId,
):
    """
    Update a translation.
    """
    # Verify entity belongs to tenant
    entity_result = await db.execute(
        select(ContentEntity.id).where(
            ContentEntity.id == UUID(entity_id),
            ContentEntity.tenant_id == tenant_id,
        )
    )
    if not entity_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Content entity not found")

    result = await db.execute(
        select(ContentTranslation).where(
            ContentTranslation.entity_id == UUID(entity_id),
            ContentTranslation.language_code == language_code,
        )
    )
    translation = result.scalar_one_or_none()

    if not translation:
        raise HTTPException(status_code=404, detail="Translation not found")

    # Update fields
    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(translation, field, value)

    await db.commit()
    await db.refresh(translation)

    return {
        "id": str(translation.id),
        "entity_id": str(translation.entity_id),
        "language_code": translation.language_code,
        "title": translation.title,
        "slug": translation.slug,
        "meta_title": translation.meta_title,
        "meta_description": translation.meta_description,
        "excerpt": translation.excerpt,
        "content_markdown": translation.content_markdown,
        "content_html": translation.content_html,
        "is_primary": translation.is_primary or False,
        "word_count": translation.word_count,
        "reading_time_minutes": translation.reading_time_minutes,
        "ai_generation_status": translation.ai_generation_status,
        "ai_generated_at": translation.ai_generated_at,
        "created_at": translation.created_at,
        "updated_at": translation.updated_at,
    }


@router.delete("/entities/{entity_id}/translations/{language_code}", status_code=204)
async def delete_translation(
    entity_id: str,
    language_code: str,
    db: DbSession,
    tenant_id: TenantId,
):
    """
    Delete a translation.
    """
    # Verify entity belongs to tenant
    entity_result = await db.execute(
        select(ContentEntity.id).where(
            ContentEntity.id == UUID(entity_id),
            ContentEntity.tenant_id == tenant_id,
        )
    )
    if not entity_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Content entity not found")

    result = await db.execute(
        select(ContentTranslation).where(
            ContentTranslation.entity_id == UUID(entity_id),
            ContentTranslation.language_code == language_code,
        )
    )
    translation = result.scalar_one_or_none()

    if not translation:
        raise HTTPException(status_code=404, detail="Translation not found")

    await db.delete(translation)
    await db.commit()


# ============================================================================
# Endpoints - Tags
# ============================================================================

@router.get("/tags", response_model=List[ContentTagResponse])
async def get_tags(
    db: DbSession,
    tenant_id: TenantId,
    active_only: bool = Query(True),
):
    """
    Get all tags for the tenant.
    """
    query = select(ContentTag).where(ContentTag.tenant_id == tenant_id)

    if active_only:
        query = query.where(ContentTag.is_active == True)

    query = query.order_by(ContentTag.sort_order)

    result = await db.execute(query)
    tags = result.scalars().all()

    return [
        {
            "id": str(t.id),
            "slug": t.slug,
            "labels": t.labels_json,
            "color": t.color,
            "icon": t.icon,
        }
        for t in tags
    ]


@router.post("/tags", response_model=ContentTagResponse, status_code=201)
async def create_tag(
    data: ContentTagCreate,
    db: DbSession,
    tenant_id: TenantId,
):
    """
    Create a new tag.
    """
    tag = ContentTag(
        tenant_id=tenant_id,
        slug=data.slug,
        labels_json=data.labels_json,
        descriptions_json=data.descriptions_json,
        parent_id=UUID(data.parent_id) if data.parent_id else None,
        color=data.color,
        icon=data.icon,
        sort_order=data.sort_order,
    )

    db.add(tag)
    await db.commit()
    await db.refresh(tag)

    return {
        "id": str(tag.id),
        "slug": tag.slug,
        "labels": tag.labels_json,
        "color": tag.color,
        "icon": tag.icon,
    }


@router.patch("/tags/{tag_id}", response_model=ContentTagResponse)
async def update_tag(
    tag_id: str,
    data: ContentTagUpdate,
    db: DbSession,
    tenant_id: TenantId,
):
    """
    Update a tag.
    """
    result = await db.execute(
        select(ContentTag).where(
            ContentTag.id == UUID(tag_id),
            ContentTag.tenant_id == tenant_id,
        )
    )
    tag = result.scalar_one_or_none()

    if not tag:
        raise HTTPException(status_code=404, detail="Tag not found")

    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        if field == "parent_id" and value:
            value = UUID(value)
        setattr(tag, field, value)

    await db.commit()
    await db.refresh(tag)

    return {
        "id": str(tag.id),
        "slug": tag.slug,
        "labels": tag.labels_json,
        "color": tag.color,
        "icon": tag.icon,
    }


@router.delete("/tags/{tag_id}", status_code=204)
async def delete_tag(
    tag_id: str,
    db: DbSession,
    tenant_id: TenantId,
):
    """
    Delete a tag.
    """
    result = await db.execute(
        select(ContentTag).where(
            ContentTag.id == UUID(tag_id),
            ContentTag.tenant_id == tenant_id,
        )
    )
    tag = result.scalar_one_or_none()

    if not tag:
        raise HTTPException(status_code=404, detail="Tag not found")

    await db.delete(tag)
    await db.commit()


# ============================================================================
# Endpoints - Relations
# ============================================================================

@router.get("/entities/{entity_id}/relations", response_model=List[ContentRelationResponse])
async def get_relations(
    entity_id: str,
    db: DbSession,
    tenant_id: TenantId,
):
    """
    Get all relations for an entity (outgoing).
    """
    # Verify entity belongs to tenant
    entity_result = await db.execute(
        select(ContentEntity.id).where(
            ContentEntity.id == UUID(entity_id),
            ContentEntity.tenant_id == tenant_id,
        )
    )
    if not entity_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Content entity not found")

    result = await db.execute(
        select(ContentRelation)
        .where(ContentRelation.source_entity_id == UUID(entity_id))
        .options(
            selectinload(ContentRelation.target_entity).selectinload(ContentEntity.translations)
        )
        .order_by(ContentRelation.sort_order)
    )
    relations = result.scalars().all()

    response = []
    for r in relations:
        rel_data = {
            "id": str(r.id),
            "relation_type": r.relation_type,
            "sort_order": r.sort_order or 0,
            "is_bidirectional": r.is_bidirectional or False,
            "target": None,
        }
        if r.target_entity:
            target = r.target_entity
            rel_data["target"] = {
                "id": str(target.id),
                "entity_type": target.entity_type,
                "status": target.status,
                "cover_image_url": target.cover_image_url,
                "translations": [
                    {
                        "id": str(t.id),
                        "entity_id": str(t.entity_id),
                        "language_code": t.language_code,
                        "title": t.title,
                        "slug": t.slug,
                        "excerpt": t.excerpt,
                        "is_primary": t.is_primary or False,
                    }
                    for t in target.translations
                ] if target.translations else [],
            }
        response.append(rel_data)

    return response


@router.post("/entities/{entity_id}/relations", response_model=ContentRelationResponse, status_code=201)
async def create_relation(
    entity_id: str,
    data: ContentRelationCreate,
    db: DbSession,
    tenant_id: TenantId,
    user: CurrentUser,
):
    """
    Create a relation between two entities.
    """
    # Verify source entity belongs to tenant
    source_result = await db.execute(
        select(ContentEntity).where(
            ContentEntity.id == UUID(entity_id),
            ContentEntity.tenant_id == tenant_id,
        )
    )
    source = source_result.scalar_one_or_none()
    if not source:
        raise HTTPException(status_code=404, detail="Source entity not found")

    # Verify target entity exists and belongs to same tenant
    target_result = await db.execute(
        select(ContentEntity).where(
            ContentEntity.id == UUID(data.target_entity_id),
            ContentEntity.tenant_id == tenant_id,
        )
        .options(selectinload(ContentEntity.translations))
    )
    target = target_result.scalar_one_or_none()
    if not target:
        raise HTTPException(status_code=404, detail="Target entity not found")

    # Validate relation type
    try:
        ContentRelationType(data.relation_type)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid relation_type. Must be one of: {[e.value for e in ContentRelationType]}"
        )

    relation = ContentRelation(
        tenant_id=tenant_id,
        source_entity_id=UUID(entity_id),
        target_entity_id=UUID(data.target_entity_id),
        relation_type=data.relation_type,
        sort_order=data.sort_order,
        is_bidirectional=data.is_bidirectional,
        created_by=user.id,
    )

    db.add(relation)
    await db.commit()
    await db.refresh(relation)

    return {
        "id": str(relation.id),
        "relation_type": relation.relation_type,
        "sort_order": relation.sort_order or 0,
        "is_bidirectional": relation.is_bidirectional or False,
        "target": {
            "id": str(target.id),
            "entity_type": target.entity_type,
            "status": target.status,
            "cover_image_url": target.cover_image_url,
            "translations": [
                {
                    "id": str(t.id),
                    "entity_id": str(t.entity_id),
                    "language_code": t.language_code,
                    "title": t.title,
                    "slug": t.slug,
                    "excerpt": t.excerpt,
                    "is_primary": t.is_primary or False,
                }
                for t in target.translations
            ] if target.translations else [],
        },
    }


@router.delete("/entities/{entity_id}/relations/{relation_id}", status_code=204)
async def delete_relation(
    entity_id: str,
    relation_id: str,
    db: DbSession,
    tenant_id: TenantId,
):
    """
    Delete a relation.
    """
    result = await db.execute(
        select(ContentRelation).where(
            ContentRelation.id == UUID(relation_id),
            ContentRelation.source_entity_id == UUID(entity_id),
            ContentRelation.tenant_id == tenant_id,
        )
    )
    relation = result.scalar_one_or_none()

    if not relation:
        raise HTTPException(status_code=404, detail="Relation not found")

    await db.delete(relation)
    await db.commit()


# ============================================================================
# Endpoints - Search and Discovery
# ============================================================================

@router.get("/search")
async def search_content(
    db: DbSession,
    tenant_id: TenantId,
    q: str = Query(..., min_length=2, description="Search query"),
    types: Optional[str] = Query(None, description="Comma-separated entity types"),
    language: str = Query("fr", description="Language code"),
    limit: int = Query(10, ge=1, le=50),
):
    """
    Quick search across all content.
    """
    search_term = f"%{q}%"

    # Build query
    query = (
        select(ContentEntity)
        .where(ContentEntity.tenant_id == tenant_id)
        .join(ContentTranslation)
        .where(
            ContentTranslation.language_code == language,
            or_(
                ContentTranslation.title.ilike(search_term),
                ContentTranslation.excerpt.ilike(search_term),
            )
        )
        .options(selectinload(ContentEntity.translations))
        .limit(limit)
    )

    if types:
        type_list = [t.strip() for t in types.split(",")]
        query = query.where(ContentEntity.entity_type.in_(type_list))

    result = await db.execute(query)
    entities = result.scalars().unique().all()

    return [entity_to_list_item(e) for e in entities]


@router.get("/nearby")
async def get_nearby_content(
    db: DbSession,
    tenant_id: TenantId,
    lat: float = Query(..., description="Latitude"),
    lng: float = Query(..., description="Longitude"),
    radius: float = Query(50, description="Radius in km"),
    types: Optional[str] = Query(None, description="Comma-separated entity types"),
    limit: int = Query(20, ge=1, le=100),
):
    """
    Get content near a geographic point.
    Uses Haversine formula approximation.
    """
    # Haversine approximation (works for small distances)
    # 1 degree latitude ≈ 111 km
    # 1 degree longitude ≈ 111 km * cos(latitude)
    import math

    lat_diff = radius / 111.0
    lng_diff = radius / (111.0 * math.cos(math.radians(lat)))

    query = (
        select(ContentEntity)
        .where(
            ContentEntity.tenant_id == tenant_id,
            ContentEntity.lat.isnot(None),
            ContentEntity.lng.isnot(None),
            ContentEntity.lat.between(lat - lat_diff, lat + lat_diff),
            ContentEntity.lng.between(lng - lng_diff, lng + lng_diff),
        )
        .options(
            selectinload(ContentEntity.translations),
            selectinload(ContentEntity.tags),
        )
        .limit(limit)
    )

    if types:
        type_list = [t.strip() for t in types.split(",")]
        query = query.where(ContentEntity.entity_type.in_(type_list))

    result = await db.execute(query)
    entities = result.scalars().all()

    return [entity_to_list_item(e) for e in entities]


# ============================================================================
# Endpoints - SEO Analysis (Post-Import)
# ============================================================================

class SEOAlert(BaseModel):
    """Individual SEO alert."""
    type: str  # meta_title, meta_description, content, structure, links
    severity: str  # error, warning, info
    message: str
    suggestion: Optional[str] = None
    location: Optional[str] = None


class SEOSectionAnalysis(BaseModel):
    """Analysis of a specific content section."""
    section_type: str  # meta_title, meta_description, intro, heading, paragraph
    content_preview: str  # First 100 chars
    score: int  # 0-100
    issues: List[SEOAlert]
    suggestions: List[str]


class SEOStructureCheck(BaseModel):
    """Check of content structure."""
    has_hook_intro: bool
    has_practical_info: bool
    has_subheadings: bool
    has_cta_blocks: bool
    has_internal_links: bool
    missing_sections: List[str]


class SEOAnalysisResult(BaseModel):
    """Complete SEO analysis result."""
    entity_id: str
    language_code: str
    overall_score: int
    sections: List[SEOSectionAnalysis]
    structure_check: SEOStructureCheck
    word_count: int
    reading_time_minutes: int
    keyword_suggestions: List[str]
    alerts: List[SEOAlert]


@router.post("/entities/{entity_id}/analyze-seo", response_model=SEOAnalysisResult)
async def analyze_content_seo(
    entity_id: str,
    db: DbSession,
    tenant_id: TenantId,
    language_code: str = Query("fr", description="Language to analyze"),
):
    """
    Analyze SEO quality of an imported content entity.

    This endpoint is called AFTER import to provide detailed SEO feedback.
    Analysis covers:
    - Meta title and description optimization
    - Content structure (headings, paragraphs)
    - Internal links presence
    - Reading metrics
    - Section-by-section feedback
    """
    import re

    # Get entity with translation
    result = await db.execute(
        select(ContentEntity)
        .where(
            ContentEntity.id == UUID(entity_id),
            ContentEntity.tenant_id == tenant_id,
        )
        .options(selectinload(ContentEntity.translations))
    )
    entity = result.scalar_one_or_none()

    if not entity:
        raise HTTPException(status_code=404, detail="Content entity not found")

    # Find translation for requested language
    translation = next(
        (t for t in entity.translations if t.language_code == language_code),
        None
    )

    if not translation:
        raise HTTPException(
            status_code=404,
            detail=f"No translation found for language '{language_code}'"
        )

    # Perform analysis
    alerts: List[SEOAlert] = []
    sections: List[SEOSectionAnalysis] = []

    # === Meta Title Analysis ===
    meta_title = translation.meta_title or translation.title or ""
    meta_title_len = len(meta_title)
    meta_title_issues = []
    meta_title_suggestions = []

    if meta_title_len == 0:
        meta_title_issues.append(SEOAlert(
            type="meta_title",
            severity="error",
            message="Meta title manquant",
            suggestion="Ajoutez un meta title de 50-60 caractères"
        ))
    elif meta_title_len < 30:
        meta_title_issues.append(SEOAlert(
            type="meta_title",
            severity="warning",
            message=f"Meta title trop court ({meta_title_len} caractères)",
            suggestion="Allongez le title à 50-60 caractères pour maximiser l'impact"
        ))
    elif meta_title_len > 60:
        meta_title_issues.append(SEOAlert(
            type="meta_title",
            severity="warning",
            message=f"Meta title trop long ({meta_title_len} caractères)",
            suggestion="Raccourcissez à 60 caractères max pour éviter la troncature Google"
        ))

    sections.append(SEOSectionAnalysis(
        section_type="meta_title",
        content_preview=meta_title[:100],
        score=100 if 30 <= meta_title_len <= 60 else (70 if meta_title_len > 0 else 0),
        issues=meta_title_issues,
        suggestions=meta_title_suggestions
    ))
    alerts.extend(meta_title_issues)

    # === Meta Description Analysis ===
    meta_desc = translation.meta_description or ""
    meta_desc_len = len(meta_desc)
    meta_desc_issues = []

    if meta_desc_len == 0:
        meta_desc_issues.append(SEOAlert(
            type="meta_description",
            severity="error",
            message="Meta description manquante",
            suggestion="Ajoutez une description de 120-160 caractères"
        ))
    elif meta_desc_len < 70:
        meta_desc_issues.append(SEOAlert(
            type="meta_description",
            severity="warning",
            message=f"Meta description trop courte ({meta_desc_len} caractères)",
            suggestion="Enrichissez la description (120-160 caractères idéal)"
        ))
    elif meta_desc_len > 160:
        meta_desc_issues.append(SEOAlert(
            type="meta_description",
            severity="warning",
            message=f"Meta description trop longue ({meta_desc_len} caractères)",
            suggestion="Réduisez à 160 caractères pour éviter la troncature"
        ))

    sections.append(SEOSectionAnalysis(
        section_type="meta_description",
        content_preview=meta_desc[:100],
        score=100 if 120 <= meta_desc_len <= 160 else (70 if meta_desc_len > 0 else 0),
        issues=meta_desc_issues,
        suggestions=[]
    ))
    alerts.extend(meta_desc_issues)

    # === Content Analysis ===
    content = translation.content_markdown or ""
    word_count = len(content.split()) if content else 0
    reading_time = max(1, word_count // 200)

    # Count headings
    h2_count = len(re.findall(r'^##\s', content, re.MULTILINE))
    h3_count = len(re.findall(r'^###\s', content, re.MULTILINE))
    heading_count = h2_count + h3_count

    # Check structure
    has_hook_intro = len(content.split('\n\n')[0]) > 100 if content else False
    has_practical_info = any(keyword in content.lower() for keyword in [
        'horaire', 'tarif', 'prix', 'accès', 'transport', 'ouverture',
        'hours', 'price', 'access', 'opening'
    ])
    has_subheadings = heading_count >= 2
    has_cta = '[nous contacter]' in content.lower() or '[devis]' in content.lower() or '[contact]' in content.lower()

    # Count internal links (markdown links)
    internal_links = re.findall(r'\[([^\]]+)\]\(content:', content)
    has_internal_links = len(internal_links) > 0

    # Content length issues
    content_issues = []
    if word_count < 300:
        content_issues.append(SEOAlert(
            type="content",
            severity="warning",
            message=f"Contenu court ({word_count} mots)",
            suggestion="Enrichissez le contenu (minimum 500 mots recommandé pour SEO)"
        ))

    if heading_count < 2:
        content_issues.append(SEOAlert(
            type="structure",
            severity="warning",
            message="Peu de sous-titres (H2/H3)",
            suggestion="Ajoutez des sous-titres pour structurer le contenu"
        ))

    if not has_internal_links:
        content_issues.append(SEOAlert(
            type="links",
            severity="info",
            message="Aucun lien interne détecté",
            suggestion="Ajoutez 3-5 liens vers d'autres contenus liés"
        ))

    sections.append(SEOSectionAnalysis(
        section_type="content",
        content_preview=content[:100] if content else "",
        score=min(100, 50 + (word_count // 20)),
        issues=content_issues,
        suggestions=[]
    ))
    alerts.extend(content_issues)

    # === Structure Check ===
    missing_sections = []
    if not has_hook_intro:
        missing_sections.append("Introduction accrocheuse (hook)")
    if not has_practical_info:
        missing_sections.append("Informations pratiques")
    if not has_subheadings:
        missing_sections.append("Sous-titres structurants")
    if not has_cta:
        missing_sections.append("Appel à l'action (CTA)")
    if not has_internal_links:
        missing_sections.append("Liens internes")

    structure_check = SEOStructureCheck(
        has_hook_intro=has_hook_intro,
        has_practical_info=has_practical_info,
        has_subheadings=has_subheadings,
        has_cta_blocks=has_cta,
        has_internal_links=has_internal_links,
        missing_sections=missing_sections
    )

    # === Overall Score Calculation ===
    # Weight: meta_title 15%, meta_desc 15%, content length 30%, structure 40%
    meta_title_score = 100 if 30 <= meta_title_len <= 60 else (70 if meta_title_len > 0 else 0)
    meta_desc_score = 100 if 120 <= meta_desc_len <= 160 else (70 if meta_desc_len > 0 else 0)
    content_score = min(100, 50 + (word_count // 20))
    structure_score = 100 - (len(missing_sections) * 20)

    overall_score = int(
        meta_title_score * 0.15 +
        meta_desc_score * 0.15 +
        content_score * 0.30 +
        structure_score * 0.40
    )

    # Keyword suggestions based on entity type
    keyword_suggestions = []
    if entity.entity_type == "destination":
        keyword_suggestions = ["voyage", "visiter", "que faire", "guide", "itinéraire"]
    elif entity.entity_type == "attraction":
        keyword_suggestions = ["visiter", "horaires", "tarifs", "conseils", "photos"]
    elif entity.entity_type == "accommodation":
        keyword_suggestions = ["hôtel", "réserver", "avis", "chambres", "prix"]

    return SEOAnalysisResult(
        entity_id=entity_id,
        language_code=language_code,
        overall_score=overall_score,
        sections=sections,
        structure_check=structure_check,
        word_count=word_count,
        reading_time_minutes=reading_time,
        keyword_suggestions=keyword_suggestions,
        alerts=alerts
    )


# ============================================================================
# Endpoints - CTA Blocks
# ============================================================================

from app.models.content import ContentCTABlock


class CTABlockCreate(BaseModel):
    """Create a CTA block."""
    cta_type: str = Field(..., description="quote_request or related_circuit")
    name: str = Field(..., min_length=1, max_length=255)
    title_json: Dict[str, str]
    description_json: Optional[Dict[str, str]] = None
    button_text_json: Dict[str, str]
    button_action: Optional[str] = None
    button_url: Optional[str] = None
    entity_types: Optional[List[str]] = None
    insert_position: str = "after_content"
    style: str = "card"
    background_color: Optional[str] = None
    text_color: Optional[str] = None
    icon: Optional[str] = None
    is_active: bool = True
    sort_order: int = 0


class CTABlockUpdate(BaseModel):
    """Update a CTA block."""
    name: Optional[str] = None
    title_json: Optional[Dict[str, str]] = None
    description_json: Optional[Dict[str, str]] = None
    button_text_json: Optional[Dict[str, str]] = None
    button_action: Optional[str] = None
    button_url: Optional[str] = None
    entity_types: Optional[List[str]] = None
    insert_position: Optional[str] = None
    style: Optional[str] = None
    background_color: Optional[str] = None
    text_color: Optional[str] = None
    icon: Optional[str] = None
    is_active: Optional[bool] = None
    sort_order: Optional[int] = None


class CTABlockResponse(BaseModel):
    """CTA block response."""
    id: str
    tenant_id: str
    cta_type: str
    name: str
    title_json: Dict[str, str]
    description_json: Optional[Dict[str, str]] = None
    button_text_json: Dict[str, str]
    button_action: Optional[str] = None
    button_url: Optional[str] = None
    entity_types: Optional[List[str]] = None
    insert_position: str
    style: str
    background_color: Optional[str] = None
    text_color: Optional[str] = None
    icon: Optional[str] = None
    is_active: bool
    sort_order: int
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


@router.get("/cta-blocks", response_model=List[CTABlockResponse])
async def get_cta_blocks(
    db: DbSession,
    tenant_id: TenantId,
    cta_type: Optional[str] = Query(None, description="Filter by type"),
    entity_type: Optional[str] = Query(None, description="Filter by entity type"),
    position: Optional[str] = Query(None, description="Filter by position"),
    active_only: bool = Query(True, description="Only active blocks"),
):
    """
    Get CTA blocks for the tenant.
    """
    query = select(ContentCTABlock).where(ContentCTABlock.tenant_id == tenant_id)

    if cta_type:
        query = query.where(ContentCTABlock.cta_type == cta_type)

    if position:
        query = query.where(ContentCTABlock.insert_position == position)

    if active_only:
        query = query.where(ContentCTABlock.is_active == True)

    # Filter by entity type (check if entity_type is in the array)
    if entity_type:
        query = query.where(
            ContentCTABlock.entity_types.contains([entity_type])
        )

    query = query.order_by(ContentCTABlock.sort_order)

    result = await db.execute(query)
    blocks = result.scalars().all()

    return [
        {
            "id": str(b.id),
            "tenant_id": str(b.tenant_id),
            "cta_type": b.cta_type,
            "name": b.name,
            "title_json": b.title_json,
            "description_json": b.description_json,
            "button_text_json": b.button_text_json,
            "button_action": b.button_action,
            "button_url": b.button_url,
            "entity_types": b.entity_types,
            "insert_position": b.insert_position,
            "style": b.style,
            "background_color": b.background_color,
            "text_color": b.text_color,
            "icon": b.icon,
            "is_active": b.is_active,
            "sort_order": b.sort_order,
            "created_at": b.created_at,
            "updated_at": b.updated_at,
        }
        for b in blocks
    ]


@router.post("/cta-blocks", response_model=CTABlockResponse, status_code=201)
async def create_cta_block(
    data: CTABlockCreate,
    db: DbSession,
    tenant_id: TenantId,
    user: CurrentUser,
):
    """
    Create a new CTA block.
    """
    block = ContentCTABlock(
        tenant_id=tenant_id,
        cta_type=data.cta_type,
        name=data.name,
        title_json=data.title_json,
        description_json=data.description_json,
        button_text_json=data.button_text_json,
        button_action=data.button_action,
        button_url=data.button_url,
        entity_types=data.entity_types,
        insert_position=data.insert_position,
        style=data.style,
        background_color=data.background_color,
        text_color=data.text_color,
        icon=data.icon,
        is_active=data.is_active,
        sort_order=data.sort_order,
    )

    db.add(block)
    await db.commit()
    await db.refresh(block)

    return {
        "id": str(block.id),
        "tenant_id": str(block.tenant_id),
        "cta_type": block.cta_type,
        "name": block.name,
        "title_json": block.title_json,
        "description_json": block.description_json,
        "button_text_json": block.button_text_json,
        "button_action": block.button_action,
        "button_url": block.button_url,
        "entity_types": block.entity_types,
        "insert_position": block.insert_position,
        "style": block.style,
        "background_color": block.background_color,
        "text_color": block.text_color,
        "icon": block.icon,
        "is_active": block.is_active,
        "sort_order": block.sort_order,
        "created_at": block.created_at,
        "updated_at": block.updated_at,
    }


@router.patch("/cta-blocks/{block_id}", response_model=CTABlockResponse)
async def update_cta_block(
    block_id: str,
    data: CTABlockUpdate,
    db: DbSession,
    tenant_id: TenantId,
):
    """
    Update a CTA block.
    """
    result = await db.execute(
        select(ContentCTABlock).where(
            ContentCTABlock.id == UUID(block_id),
            ContentCTABlock.tenant_id == tenant_id,
        )
    )
    block = result.scalar_one_or_none()

    if not block:
        raise HTTPException(status_code=404, detail="CTA block not found")

    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(block, field, value)

    await db.commit()
    await db.refresh(block)

    return {
        "id": str(block.id),
        "tenant_id": str(block.tenant_id),
        "cta_type": block.cta_type,
        "name": block.name,
        "title_json": block.title_json,
        "description_json": block.description_json,
        "button_text_json": block.button_text_json,
        "button_action": block.button_action,
        "button_url": block.button_url,
        "entity_types": block.entity_types,
        "insert_position": block.insert_position,
        "style": block.style,
        "background_color": block.background_color,
        "text_color": block.text_color,
        "icon": block.icon,
        "is_active": block.is_active,
        "sort_order": block.sort_order,
        "created_at": block.created_at,
        "updated_at": block.updated_at,
    }


@router.delete("/cta-blocks/{block_id}", status_code=204)
async def delete_cta_block(
    block_id: str,
    db: DbSession,
    tenant_id: TenantId,
):
    """
    Delete a CTA block.
    """
    result = await db.execute(
        select(ContentCTABlock).where(
            ContentCTABlock.id == UUID(block_id),
            ContentCTABlock.tenant_id == tenant_id,
        )
    )
    block = result.scalar_one_or_none()

    if not block:
        raise HTTPException(status_code=404, detail="CTA block not found")

    await db.delete(block)
    await db.commit()
