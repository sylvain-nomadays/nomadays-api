"""
Day template management endpoints.

Day templates are TripDay records within a dedicated "template library" Trip
per tenant (type='template'). They contain multiple formula blocks that can
be inserted into circuit days as a group.
"""

from typing import List, Optional
from datetime import datetime

from fastapi import APIRouter, HTTPException, status, Query
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload

from app.api.deps import DbSession, CurrentUser, CurrentTenant
from app.models.trip import Trip, TripDay
from app.models.formula import Formula
from app.models.item import Item, ItemPriceTier
from app.api.formulas import _duplicate_formula, FormulaResponse

router = APIRouter(prefix="/day-templates", tags=["Day Templates"])

# Name of the hidden trip that holds day templates for each tenant
TEMPLATE_LIBRARY_NAME = "__template_library__"


# ============ SCHEMAS ============

class DayTemplateListItem(BaseModel):
    id: int
    title: Optional[str] = None
    description: Optional[str] = None
    day_number: int = 1
    location_from: Optional[str] = None
    location_to: Optional[str] = None
    template_version: int = 1
    template_tags: Optional[list] = None
    formulas_count: int = 0
    breakfast_included: bool = False
    lunch_included: bool = False
    dinner_included: bool = False
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class DayTemplateDetail(DayTemplateListItem):
    formulas: List[FormulaResponse] = []


class DayTemplateCreate(BaseModel):
    title: str
    description: Optional[str] = None
    location_from: Optional[str] = None
    location_to: Optional[str] = None
    location_id: Optional[int] = None
    template_tags: Optional[list] = None
    breakfast_included: bool = False
    lunch_included: bool = False
    dinner_included: bool = False


class DayTemplateUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    location_from: Optional[str] = None
    location_to: Optional[str] = None
    location_id: Optional[int] = None
    template_tags: Optional[list] = None
    breakfast_included: Optional[bool] = None
    lunch_included: Optional[bool] = None
    dinner_included: Optional[bool] = None


# ============ HELPERS ============

async def _get_or_create_template_library(db: DbSession, tenant_id: int) -> Trip:
    """Get or create the hidden trip that holds day templates for a tenant."""
    result = await db.execute(
        select(Trip).where(
            Trip.tenant_id == tenant_id,
            Trip.name == TEMPLATE_LIBRARY_NAME,
            Trip.type == "template",
        )
    )
    library = result.scalar_one_or_none()

    if not library:
        library = Trip(
            tenant_id=tenant_id,
            name=TEMPLATE_LIBRARY_NAME,
            type="template",
            status="template",
            destination_country="XX",
            default_currency="EUR",
        )
        db.add(library)
        await db.flush()

    return library


def _formula_eager_options():
    """Standard eager-load chain for day template formulas."""
    return [
        selectinload(TripDay.formulas)
        .selectinload(Formula.items)
        .selectinload(Item.price_tiers),
        selectinload(TripDay.formulas)
        .selectinload(Formula.children)
        .selectinload(Formula.items)
        .selectinload(Item.price_tiers),
    ]


# ============ ENDPOINTS ============

@router.get("", response_model=List[DayTemplateListItem])
async def list_day_templates(
    db: DbSession,
    tenant: CurrentTenant,
    user: CurrentUser,
    search: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
):
    """List all day templates for this tenant."""
    query = (
        select(TripDay)
        .where(
            TripDay.tenant_id == tenant.id,
            TripDay.is_template == True,  # noqa: E712
        )
        .options(selectinload(TripDay.formulas))
        .order_by(TripDay.updated_at.desc())
    )

    if search:
        query = query.where(TripDay.title.ilike(f"%{search}%"))

    query = query.offset((page - 1) * page_size).limit(page_size)

    result = await db.execute(query)
    days = result.scalars().all()

    return [
        DayTemplateListItem(
            id=d.id,
            title=d.title,
            description=d.description,
            day_number=d.day_number,
            location_from=d.location_from,
            location_to=d.location_to,
            template_version=d.template_version,
            template_tags=d.template_tags,
            formulas_count=len(d.formulas or []),
            breakfast_included=d.breakfast_included,
            lunch_included=d.lunch_included,
            dinner_included=d.dinner_included,
            created_at=d.created_at,
            updated_at=d.updated_at,
        )
        for d in days
    ]


@router.get("/{template_id}", response_model=DayTemplateDetail)
async def get_day_template(
    template_id: int,
    db: DbSession,
    tenant: CurrentTenant,
    user: CurrentUser,
):
    """Get a single day template with all its formula blocks."""
    result = await db.execute(
        select(TripDay)
        .where(
            TripDay.id == template_id,
            TripDay.tenant_id == tenant.id,
            TripDay.is_template == True,  # noqa: E712
        )
        .options(*_formula_eager_options())
    )
    day = result.scalar_one_or_none()

    if not day:
        raise HTTPException(status_code=404, detail="Day template not found")

    return DayTemplateDetail(
        id=day.id,
        title=day.title,
        description=day.description,
        day_number=day.day_number,
        location_from=day.location_from,
        location_to=day.location_to,
        template_version=day.template_version,
        template_tags=day.template_tags,
        formulas_count=len(day.formulas or []),
        breakfast_included=day.breakfast_included,
        lunch_included=day.lunch_included,
        dinner_included=day.dinner_included,
        created_at=day.created_at,
        updated_at=day.updated_at,
        formulas=day.formulas,
    )


@router.post("", response_model=DayTemplateListItem, status_code=status.HTTP_201_CREATED)
async def create_day_template(
    data: DayTemplateCreate,
    db: DbSession,
    tenant: CurrentTenant,
    user: CurrentUser,
):
    """Create a new empty day template."""
    library = await _get_or_create_template_library(db, tenant.id)

    # Get next day_number for template library
    result = await db.execute(
        select(func.coalesce(func.max(TripDay.day_number), 0))
        .where(TripDay.trip_id == library.id)
    )
    next_day = (result.scalar() or 0) + 1

    new_day = TripDay(
        tenant_id=tenant.id,
        trip_id=library.id,
        day_number=next_day,
        title=data.title,
        description=data.description,
        location_from=data.location_from,
        location_to=data.location_to,
        location_id=data.location_id,
        is_template=True,
        template_version=1,
        template_tags=data.template_tags,
        breakfast_included=data.breakfast_included,
        lunch_included=data.lunch_included,
        dinner_included=data.dinner_included,
    )
    db.add(new_day)
    await db.flush()
    await db.commit()

    return DayTemplateListItem(
        id=new_day.id,
        title=new_day.title,
        description=new_day.description,
        day_number=new_day.day_number,
        location_from=new_day.location_from,
        location_to=new_day.location_to,
        template_version=new_day.template_version,
        template_tags=new_day.template_tags,
        formulas_count=0,
        breakfast_included=new_day.breakfast_included,
        lunch_included=new_day.lunch_included,
        dinner_included=new_day.dinner_included,
        created_at=new_day.created_at,
        updated_at=new_day.updated_at,
    )


@router.patch("/{template_id}", response_model=DayTemplateListItem)
async def update_day_template(
    template_id: int,
    data: DayTemplateUpdate,
    db: DbSession,
    tenant: CurrentTenant,
    user: CurrentUser,
):
    """Update a day template's metadata."""
    result = await db.execute(
        select(TripDay)
        .where(
            TripDay.id == template_id,
            TripDay.tenant_id == tenant.id,
            TripDay.is_template == True,  # noqa: E712
        )
        .options(selectinload(TripDay.formulas))
    )
    day = result.scalar_one_or_none()

    if not day:
        raise HTTPException(status_code=404, detail="Day template not found")

    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(day, field, value)

    day.template_version += 1

    await db.flush()
    await db.commit()
    await db.refresh(day)

    return DayTemplateListItem(
        id=day.id,
        title=day.title,
        description=day.description,
        day_number=day.day_number,
        location_from=day.location_from,
        location_to=day.location_to,
        template_version=day.template_version,
        template_tags=day.template_tags,
        formulas_count=len(day.formulas or []),
        breakfast_included=day.breakfast_included,
        lunch_included=day.lunch_included,
        dinner_included=day.dinner_included,
        created_at=day.created_at,
        updated_at=day.updated_at,
    )


@router.delete("/{template_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_day_template(
    template_id: int,
    db: DbSession,
    tenant: CurrentTenant,
    user: CurrentUser,
):
    """Delete a day template and all its formula blocks."""
    result = await db.execute(
        select(TripDay)
        .where(
            TripDay.id == template_id,
            TripDay.tenant_id == tenant.id,
            TripDay.is_template == True,  # noqa: E712
        )
    )
    day = result.scalar_one_or_none()

    if not day:
        raise HTTPException(status_code=404, detail="Day template not found")

    # Cascade deletes formulas and their items
    await db.delete(day)
    await db.commit()


@router.post("/{template_id}/insert-to/{target_day_id}", response_model=List[FormulaResponse])
async def insert_day_template_to_day(
    template_id: int,
    target_day_id: int,
    db: DbSession,
    tenant: CurrentTenant,
    user: CurrentUser,
):
    """
    Insert all formula blocks from a day template into a target circuit day.

    Each formula is deep-copied (with items and children) and linked back
    to the template formula via template_source_id for sync tracking.
    """
    # Load day template with formulas
    result = await db.execute(
        select(TripDay)
        .where(
            TripDay.id == template_id,
            TripDay.tenant_id == tenant.id,
            TripDay.is_template == True,  # noqa: E712
        )
        .options(
            selectinload(TripDay.formulas)
            .selectinload(Formula.items)
            .selectinload(Item.price_tiers),
            selectinload(TripDay.formulas)
            .selectinload(Formula.children)
            .selectinload(Formula.items)
            .selectinload(Item.price_tiers),
        )
    )
    day_template = result.scalar_one_or_none()

    if not day_template:
        raise HTTPException(status_code=404, detail="Day template not found")

    # Verify target day exists and belongs to tenant
    result = await db.execute(
        select(TripDay).where(
            TripDay.id == target_day_id,
            TripDay.tenant_id == tenant.id,
        )
    )
    target_day = result.scalar_one_or_none()

    if not target_day:
        raise HTTPException(status_code=404, detail="Target day not found")

    # Get max sort_order in target day
    result = await db.execute(
        select(func.coalesce(func.max(Formula.sort_order), -1))
        .where(Formula.trip_day_id == target_day_id)
    )
    max_sort = result.scalar() or -1

    # Copy each top-level formula from template to target day
    new_formulas = []
    top_level = [f for f in (day_template.formulas or []) if f.parent_block_id is None]

    for i, source_formula in enumerate(sorted(top_level, key=lambda f: f.sort_order)):
        new_formula = await _duplicate_formula(
            db=db,
            tenant_id=tenant.id,
            source_formula=source_formula,
            target_day_id=target_day_id,
            sort_order=max_sort + 1 + i,
            as_template=False,
        )
        new_formulas.append(new_formula)

    await db.flush()
    await db.commit()

    # Reload with relationships
    formula_ids = [f.id for f in new_formulas]
    if formula_ids:
        result = await db.execute(
            select(Formula)
            .where(Formula.id.in_(formula_ids))
            .options(
                selectinload(Formula.items).selectinload(Item.price_tiers),
                selectinload(Formula.children).selectinload(Formula.items).selectinload(Item.price_tiers),
            )
            .order_by(Formula.sort_order)
        )
        return list(result.scalars().all())

    return []
