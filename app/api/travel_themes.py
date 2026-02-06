"""
Travel Theme management endpoints.
Configurable travel themes/categories per tenant (hiking, equestrian, family, luxury...).
"""

from typing import List, Optional

from fastapi import APIRouter, HTTPException, status, Query
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload

from app.api.deps import DbSession, CurrentUser, CurrentTenant
from app.models.travel_theme import TravelTheme, DEFAULT_TRAVEL_THEMES

router = APIRouter()


# Schemas
class TravelThemeCreate(BaseModel):
    """Schema for creating a travel theme."""
    code: str
    label: str
    label_en: Optional[str] = None
    icon: Optional[str] = None
    color: Optional[str] = None
    description: Optional[str] = None
    is_active: bool = True
    sort_order: int = 0


class TravelThemeUpdate(BaseModel):
    """Schema for updating a travel theme."""
    code: Optional[str] = None
    label: Optional[str] = None
    label_en: Optional[str] = None
    icon: Optional[str] = None
    color: Optional[str] = None
    description: Optional[str] = None
    is_active: Optional[bool] = None
    sort_order: Optional[int] = None


class TravelThemeResponse(BaseModel):
    """Travel theme response."""
    id: int
    code: str
    label: str
    label_en: Optional[str]
    icon: Optional[str]
    color: Optional[str]
    description: Optional[str]
    is_active: bool
    sort_order: int

    class Config:
        from_attributes = True


class TravelThemeListResponse(BaseModel):
    """Paginated list response."""
    items: List[TravelThemeResponse]
    total: int


# Endpoints
@router.get("", response_model=TravelThemeListResponse)
async def list_travel_themes(
    db: DbSession,
    tenant: CurrentTenant,
    include_inactive: bool = False,
):
    """
    List all travel themes for the current tenant.
    """
    query = select(TravelTheme).where(TravelTheme.tenant_id == tenant.id)

    if not include_inactive:
        query = query.where(TravelTheme.is_active == True)

    query = query.order_by(TravelTheme.sort_order, TravelTheme.label)

    result = await db.execute(query)
    themes = result.scalars().all()

    return TravelThemeListResponse(
        items=[TravelThemeResponse.model_validate(t) for t in themes],
        total=len(themes),
    )


@router.post("", response_model=TravelThemeResponse, status_code=status.HTTP_201_CREATED)
async def create_travel_theme(
    data: TravelThemeCreate,
    db: DbSession,
    tenant: CurrentTenant,
    user: CurrentUser,
):
    """
    Create a new travel theme.
    """
    # Check if code already exists for this tenant
    existing = await db.execute(
        select(TravelTheme).where(
            TravelTheme.tenant_id == tenant.id,
            TravelTheme.code == data.code
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Theme with code '{data.code}' already exists",
        )

    theme = TravelTheme(
        tenant_id=tenant.id,
        **data.model_dump(),
    )
    db.add(theme)
    await db.commit()
    await db.refresh(theme)

    return TravelThemeResponse.model_validate(theme)


@router.get("/{theme_id}", response_model=TravelThemeResponse)
async def get_travel_theme(
    theme_id: int,
    db: DbSession,
    tenant: CurrentTenant,
):
    """
    Get a travel theme by ID.
    """
    result = await db.execute(
        select(TravelTheme).where(
            TravelTheme.id == theme_id,
            TravelTheme.tenant_id == tenant.id
        )
    )
    theme = result.scalar_one_or_none()

    if not theme:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Travel theme not found",
        )

    return TravelThemeResponse.model_validate(theme)


@router.patch("/{theme_id}", response_model=TravelThemeResponse)
async def update_travel_theme(
    theme_id: int,
    data: TravelThemeUpdate,
    db: DbSession,
    tenant: CurrentTenant,
    user: CurrentUser,
):
    """
    Update a travel theme.
    """
    result = await db.execute(
        select(TravelTheme).where(
            TravelTheme.id == theme_id,
            TravelTheme.tenant_id == tenant.id
        )
    )
    theme = result.scalar_one_or_none()

    if not theme:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Travel theme not found",
        )

    # Check code uniqueness if changing
    if data.code and data.code != theme.code:
        existing = await db.execute(
            select(TravelTheme).where(
                TravelTheme.tenant_id == tenant.id,
                TravelTheme.code == data.code,
                TravelTheme.id != theme_id
            )
        )
        if existing.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Theme with code '{data.code}' already exists",
            )

    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(theme, field, value)

    await db.commit()
    await db.refresh(theme)

    return TravelThemeResponse.model_validate(theme)


@router.delete("/{theme_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_travel_theme(
    theme_id: int,
    db: DbSession,
    tenant: CurrentTenant,
    user: CurrentUser,
):
    """
    Delete a travel theme.
    Note: This will remove the theme from all trips that use it.
    """
    result = await db.execute(
        select(TravelTheme).where(
            TravelTheme.id == theme_id,
            TravelTheme.tenant_id == tenant.id
        )
    )
    theme = result.scalar_one_or_none()

    if not theme:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Travel theme not found",
        )

    await db.delete(theme)
    await db.commit()


@router.post("/seed-defaults", response_model=TravelThemeListResponse)
async def seed_default_themes(
    db: DbSession,
    tenant: CurrentTenant,
    user: CurrentUser,
):
    """
    Seed the default travel themes for this tenant.
    Only creates themes that don't already exist (by code).
    """
    # Get existing codes
    result = await db.execute(
        select(TravelTheme.code).where(TravelTheme.tenant_id == tenant.id)
    )
    existing_codes = set(row[0] for row in result.all())

    created = []
    for idx, theme_data in enumerate(DEFAULT_TRAVEL_THEMES):
        if theme_data["code"] not in existing_codes:
            theme = TravelTheme(
                tenant_id=tenant.id,
                code=theme_data["code"],
                label=theme_data["label"],
                label_en=theme_data.get("label_en"),
                icon=theme_data.get("icon"),
                sort_order=idx,
                is_active=True,
            )
            db.add(theme)
            created.append(theme)

    await db.commit()

    # Refresh all created themes
    for theme in created:
        await db.refresh(theme)

    return TravelThemeListResponse(
        items=[TravelThemeResponse.model_validate(t) for t in created],
        total=len(created),
    )


@router.post("/reorder", response_model=TravelThemeListResponse)
async def reorder_themes(
    db: DbSession,
    tenant: CurrentTenant,
    user: CurrentUser,
    theme_ids: List[int],
):
    """
    Reorder travel themes by providing the IDs in the desired order.
    """
    # Get all themes for this tenant
    result = await db.execute(
        select(TravelTheme).where(TravelTheme.tenant_id == tenant.id)
    )
    themes = {t.id: t for t in result.scalars().all()}

    # Update sort order based on position in list
    for order, theme_id in enumerate(theme_ids):
        if theme_id in themes:
            themes[theme_id].sort_order = order

    await db.commit()

    # Return updated list
    result = await db.execute(
        select(TravelTheme)
        .where(TravelTheme.tenant_id == tenant.id)
        .order_by(TravelTheme.sort_order)
    )
    updated_themes = result.scalars().all()

    return TravelThemeListResponse(
        items=[TravelThemeResponse.model_validate(t) for t in updated_themes],
        total=len(updated_themes),
    )
