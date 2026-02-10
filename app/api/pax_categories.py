"""
PAX category management endpoints.

Configurable traveler categories per tenant:
- Tourist: adult, teen, child, baby
- Staff: guide, driver, cook
- Leader: tour_leader (non-paying)
"""

from typing import List, Optional

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select

from app.api.deps import DbSession, CurrentUser, CurrentTenant
from app.models.pax_category import PaxCategory, DEFAULT_PAX_CATEGORIES

router = APIRouter()


# ============ SCHEMAS ============

class PaxCategoryCreate(BaseModel):
    code: str
    label: str
    group_type: str = "tourist"  # tourist, staff, leader
    age_min: Optional[int] = None
    age_max: Optional[int] = None
    counts_for_pricing: bool = True
    is_active: bool = True
    sort_order: int = 0


class PaxCategoryUpdate(BaseModel):
    label: Optional[str] = None
    group_type: Optional[str] = None
    age_min: Optional[int] = None
    age_max: Optional[int] = None
    counts_for_pricing: Optional[bool] = None
    is_active: Optional[bool] = None
    sort_order: Optional[int] = None


class PaxCategoryResponse(BaseModel):
    id: int
    code: str
    label: str
    group_type: str
    age_min: Optional[int] = None
    age_max: Optional[int] = None
    counts_for_pricing: bool
    is_active: bool
    is_system: bool
    sort_order: int

    class Config:
        from_attributes = True


# ============ ENDPOINTS ============

@router.get("", response_model=List[PaxCategoryResponse])
async def list_pax_categories(
    db: DbSession,
    tenant: CurrentTenant,
):
    """List all pax categories for the tenant, ordered by sort_order."""
    result = await db.execute(
        select(PaxCategory)
        .where(PaxCategory.tenant_id == tenant.id)
        .order_by(PaxCategory.sort_order, PaxCategory.code)
    )
    categories = result.scalars().all()
    return [PaxCategoryResponse.model_validate(c) for c in categories]


@router.post("", response_model=PaxCategoryResponse, status_code=status.HTTP_201_CREATED)
async def create_pax_category(
    data: PaxCategoryCreate,
    db: DbSession,
    tenant: CurrentTenant,
    user: CurrentUser,
):
    """Create a custom pax category."""
    # Check code uniqueness
    existing = await db.execute(
        select(PaxCategory).where(
            PaxCategory.tenant_id == tenant.id,
            PaxCategory.code == data.code,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"A pax category with code '{data.code}' already exists",
        )

    category = PaxCategory(
        tenant_id=tenant.id,
        code=data.code,
        label=data.label,
        group_type=data.group_type,
        age_min=data.age_min,
        age_max=data.age_max,
        counts_for_pricing=data.counts_for_pricing,
        is_active=data.is_active,
        is_system=False,  # Custom categories are never system
        sort_order=data.sort_order,
    )
    db.add(category)
    await db.commit()
    await db.refresh(category)
    return PaxCategoryResponse.model_validate(category)


@router.patch("/{category_id}", response_model=PaxCategoryResponse)
async def update_pax_category(
    category_id: int,
    data: PaxCategoryUpdate,
    db: DbSession,
    tenant: CurrentTenant,
    user: CurrentUser,
):
    """Update a pax category (label, age range, counts_for_pricing, etc.)."""
    result = await db.execute(
        select(PaxCategory).where(
            PaxCategory.id == category_id,
            PaxCategory.tenant_id == tenant.id,
        )
    )
    category = result.scalar_one_or_none()
    if not category:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pax category not found")

    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(category, field, value)

    await db.commit()
    await db.refresh(category)
    return PaxCategoryResponse.model_validate(category)


@router.delete("/{category_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_pax_category(
    category_id: int,
    db: DbSession,
    tenant: CurrentTenant,
    user: CurrentUser,
):
    """Delete a custom pax category. System categories cannot be deleted."""
    result = await db.execute(
        select(PaxCategory).where(
            PaxCategory.id == category_id,
            PaxCategory.tenant_id == tenant.id,
        )
    )
    category = result.scalar_one_or_none()
    if not category:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pax category not found")

    if category.is_system:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="System pax categories cannot be deleted",
        )

    await db.delete(category)
    await db.commit()


@router.post("/seed", response_model=List[PaxCategoryResponse], status_code=status.HTTP_201_CREATED)
async def seed_pax_categories(
    db: DbSession,
    tenant: CurrentTenant,
    user: CurrentUser,
):
    """Seed default pax categories for the tenant (skips existing codes)."""
    # Get existing codes
    result = await db.execute(
        select(PaxCategory.code).where(PaxCategory.tenant_id == tenant.id)
    )
    existing_codes = {row[0] for row in result.fetchall()}

    created = []
    for cat_data in DEFAULT_PAX_CATEGORIES:
        if cat_data["code"] in existing_codes:
            continue

        category = PaxCategory(
            tenant_id=tenant.id,
            code=cat_data["code"],
            label=cat_data["label"],
            group_type=cat_data["group_type"],
            age_min=cat_data["age_min"],
            age_max=cat_data["age_max"],
            counts_for_pricing=cat_data["counts_for_pricing"],
            is_system=cat_data["is_system"],
            sort_order=cat_data["sort_order"],
        )
        db.add(category)
        created.append(category)

    if created:
        await db.commit()
        for cat in created:
            await db.refresh(cat)

    # Return all categories
    result = await db.execute(
        select(PaxCategory)
        .where(PaxCategory.tenant_id == tenant.id)
        .order_by(PaxCategory.sort_order, PaxCategory.code)
    )
    all_cats = result.scalars().all()
    return [PaxCategoryResponse.model_validate(c) for c in all_cats]
