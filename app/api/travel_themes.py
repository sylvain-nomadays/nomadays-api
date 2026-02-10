"""
Travel Theme management endpoints.
Fixed 12 travel themes — seeded per tenant, read-only for users.
"""

from typing import List, Optional

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select

from app.api.deps import DbSession, CurrentUser, CurrentTenant
from app.models.travel_theme import TravelTheme, DEFAULT_TRAVEL_THEMES

router = APIRouter()


# Schemas
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
    """List response."""
    items: List[TravelThemeResponse]
    total: int


# Endpoints
@router.get("", response_model=TravelThemeListResponse)
async def list_travel_themes(
    db: DbSession,
    tenant: CurrentTenant,
):
    """
    List all travel themes for the current tenant.
    Themes are fixed (12 pre-defined) and auto-seeded.
    """
    query = (
        select(TravelTheme)
        .where(TravelTheme.tenant_id == tenant.id, TravelTheme.is_active == True)
        .order_by(TravelTheme.sort_order, TravelTheme.label)
    )

    result = await db.execute(query)
    themes = result.scalars().all()

    # Auto-seed if no themes exist for this tenant
    if not themes:
        themes = await _seed_themes(db, tenant)

    return TravelThemeListResponse(
        items=[TravelThemeResponse.model_validate(t) for t in themes],
        total=len(themes),
    )


@router.post("/seed-defaults", response_model=TravelThemeListResponse)
async def seed_default_themes(
    db: DbSession,
    tenant: CurrentTenant,
    user: CurrentUser,
):
    """
    Seed/reset the 12 default travel themes for this tenant.
    Creates missing themes (by code). Does not modify existing ones.
    """
    themes = await _seed_themes(db, tenant)

    return TravelThemeListResponse(
        items=[TravelThemeResponse.model_validate(t) for t in themes],
        total=len(themes),
    )


async def _seed_themes(db: DbSession, tenant) -> list:
    """Internal: seed default themes for a tenant."""
    # Get existing codes
    result = await db.execute(
        select(TravelTheme.code).where(TravelTheme.tenant_id == tenant.id)
    )
    existing_codes = set(row[0] for row in result.all())

    created_any = False
    for idx, theme_data in enumerate(DEFAULT_TRAVEL_THEMES):
        if theme_data["code"] not in existing_codes:
            theme = TravelTheme(
                tenant_id=tenant.id,
                code=theme_data["code"],
                label=theme_data["label"],
                label_en=theme_data.get("label_en"),
                icon=theme_data.get("icon"),
                color=theme_data.get("color"),
                description=theme_data.get("description"),
                sort_order=idx,
                is_active=True,
            )
            db.add(theme)
            created_any = True

    if created_any:
        await db.commit()

    # Return all themes
    result = await db.execute(
        select(TravelTheme)
        .where(TravelTheme.tenant_id == tenant.id, TravelTheme.is_active == True)
        .order_by(TravelTheme.sort_order, TravelTheme.label)
    )
    return list(result.scalars().all())
