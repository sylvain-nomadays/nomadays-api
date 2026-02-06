"""
Formula and Item management endpoints.
"""

from typing import List, Optional
from decimal import Decimal

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.api.deps import DbSession, CurrentUser, CurrentTenant
from app.models.trip import TripDay
from app.models.formula import Formula, Condition
from app.models.item import Item, ItemSeason

router = APIRouter()


# ============ SCHEMAS ============

# Item Schemas
class ItemSeasonCreate(BaseModel):
    season_name: str
    valid_from: Optional[str] = None
    valid_to: Optional[str] = None
    cost_multiplier: Optional[float] = None
    cost_override: Optional[float] = None


class ItemCreate(BaseModel):
    name: str
    cost_nature_id: Optional[int] = None
    supplier_id: Optional[int] = None
    rate_catalog_id: Optional[int] = None
    contract_rate_id: Optional[int] = None
    currency: str = "EUR"
    unit_cost: float = 0.0
    pricing_method: str = "quotation"
    pricing_value: Optional[float] = None
    ratio_categories: str = "adult"
    ratio_per: int = 1
    ratio_type: str = "ratio"
    times_type: str = "fixed"
    times_value: int = 1
    sort_order: int = 0
    seasons: List[ItemSeasonCreate] = []


class ItemUpdate(BaseModel):
    name: Optional[str] = None
    cost_nature_id: Optional[int] = None
    supplier_id: Optional[int] = None
    rate_catalog_id: Optional[int] = None
    contract_rate_id: Optional[int] = None
    currency: Optional[str] = None
    unit_cost: Optional[float] = None
    pricing_method: Optional[str] = None
    pricing_value: Optional[float] = None
    ratio_categories: Optional[str] = None
    ratio_per: Optional[int] = None
    ratio_type: Optional[str] = None
    times_type: Optional[str] = None
    times_value: Optional[int] = None
    sort_order: Optional[int] = None


class ItemResponse(BaseModel):
    id: int
    formula_id: int
    name: str
    cost_nature_id: Optional[int]
    supplier_id: Optional[int]
    rate_catalog_id: Optional[int]
    contract_rate_id: Optional[int]
    currency: str
    unit_cost: float
    pricing_method: str
    pricing_value: Optional[float]
    ratio_categories: str
    ratio_per: int
    ratio_type: str
    times_type: str
    times_value: int
    sort_order: int

    class Config:
        from_attributes = True


# Formula Schemas
class ConditionCreate(BaseModel):
    field: str
    operator: str
    value: str
    action: str = "show"


class FormulaCreate(BaseModel):
    name: str
    description_html: Optional[str] = None
    service_day_start: Optional[int] = None
    service_day_end: Optional[int] = None
    sort_order: int = 0
    conditions: List[ConditionCreate] = []


class FormulaUpdate(BaseModel):
    name: Optional[str] = None
    description_html: Optional[str] = None
    service_day_start: Optional[int] = None
    service_day_end: Optional[int] = None
    sort_order: Optional[int] = None


class ConditionResponse(BaseModel):
    id: int
    field: str
    operator: str
    value: str
    action: str

    class Config:
        from_attributes = True


class FormulaResponse(BaseModel):
    id: int
    trip_day_id: int
    name: str
    description_html: Optional[str]
    service_day_start: Optional[int]
    service_day_end: Optional[int]
    sort_order: int
    items: List[ItemResponse] = []
    conditions: List[ConditionResponse] = []

    class Config:
        from_attributes = True


# ============ FORMULA ENDPOINTS ============

@router.post("/days/{day_id}/formulas", response_model=FormulaResponse, status_code=status.HTTP_201_CREATED)
async def create_formula(
    day_id: int,
    data: FormulaCreate,
    db: DbSession,
    tenant: CurrentTenant,
    user: CurrentUser,
):
    """
    Create a new formula in a trip day.
    """
    # Verify day exists and belongs to tenant
    result = await db.execute(
        select(TripDay).where(TripDay.id == day_id, TripDay.tenant_id == tenant.id)
    )
    day = result.scalar_one_or_none()

    if not day:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Trip day not found",
        )

    formula = Formula(
        tenant_id=tenant.id,
        trip_day_id=day_id,
        name=data.name,
        description_html=data.description_html,
        service_day_start=data.service_day_start,
        service_day_end=data.service_day_end,
        sort_order=data.sort_order,
    )
    db.add(formula)
    await db.flush()

    # Add conditions
    for cond_data in data.conditions:
        condition = Condition(
            tenant_id=tenant.id,
            formula_id=formula.id,
            field=cond_data.field,
            operator=cond_data.operator,
            value=cond_data.value,
            action=cond_data.action,
        )
        db.add(condition)

    await db.commit()

    # Reload with relations
    result = await db.execute(
        select(Formula)
        .where(Formula.id == formula.id)
        .options(
            selectinload(Formula.items),
            selectinload(Formula.conditions),
        )
    )
    formula = result.scalar_one()

    return FormulaResponse.model_validate(formula)


@router.get("/days/{day_id}/formulas", response_model=List[FormulaResponse])
async def list_formulas(
    day_id: int,
    db: DbSession,
    tenant: CurrentTenant,
):
    """
    List all formulas in a trip day.
    """
    result = await db.execute(
        select(Formula)
        .where(Formula.trip_day_id == day_id, Formula.tenant_id == tenant.id)
        .options(
            selectinload(Formula.items),
            selectinload(Formula.conditions),
        )
        .order_by(Formula.sort_order)
    )
    formulas = result.scalars().all()

    return [FormulaResponse.model_validate(f) for f in formulas]


@router.patch("/formulas/{formula_id}", response_model=FormulaResponse)
async def update_formula(
    formula_id: int,
    data: FormulaUpdate,
    db: DbSession,
    tenant: CurrentTenant,
    user: CurrentUser,
):
    """
    Update a formula.
    """
    result = await db.execute(
        select(Formula)
        .where(Formula.id == formula_id, Formula.tenant_id == tenant.id)
        .options(
            selectinload(Formula.items),
            selectinload(Formula.conditions),
        )
    )
    formula = result.scalar_one_or_none()

    if not formula:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Formula not found",
        )

    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(formula, field, value)

    await db.commit()
    await db.refresh(formula)

    return FormulaResponse.model_validate(formula)


@router.delete("/formulas/{formula_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_formula(
    formula_id: int,
    db: DbSession,
    tenant: CurrentTenant,
    user: CurrentUser,
):
    """
    Delete a formula and all its items.
    """
    result = await db.execute(
        select(Formula).where(Formula.id == formula_id, Formula.tenant_id == tenant.id)
    )
    formula = result.scalar_one_or_none()

    if not formula:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Formula not found",
        )

    await db.delete(formula)
    await db.commit()


# ============ ITEM ENDPOINTS ============

@router.post("/formulas/{formula_id}/items", response_model=ItemResponse, status_code=status.HTTP_201_CREATED)
async def create_item(
    formula_id: int,
    data: ItemCreate,
    db: DbSession,
    tenant: CurrentTenant,
    user: CurrentUser,
):
    """
    Create a new item in a formula.
    """
    # Verify formula exists
    result = await db.execute(
        select(Formula).where(Formula.id == formula_id, Formula.tenant_id == tenant.id)
    )
    formula = result.scalar_one_or_none()

    if not formula:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Formula not found",
        )

    item = Item(
        tenant_id=tenant.id,
        formula_id=formula_id,
        name=data.name,
        cost_nature_id=data.cost_nature_id,
        supplier_id=data.supplier_id,
        rate_catalog_id=data.rate_catalog_id,
        contract_rate_id=data.contract_rate_id,
        currency=data.currency,
        unit_cost=Decimal(str(data.unit_cost)),
        pricing_method=data.pricing_method,
        pricing_value=Decimal(str(data.pricing_value)) if data.pricing_value else None,
        ratio_categories=data.ratio_categories,
        ratio_per=data.ratio_per,
        ratio_type=data.ratio_type,
        times_type=data.times_type,
        times_value=data.times_value,
        sort_order=data.sort_order,
    )
    db.add(item)
    await db.flush()

    # Add seasons
    for season_data in data.seasons:
        from datetime import datetime
        season = ItemSeason(
            tenant_id=tenant.id,
            item_id=item.id,
            season_name=season_data.season_name,
            valid_from=datetime.fromisoformat(season_data.valid_from).date() if season_data.valid_from else None,
            valid_to=datetime.fromisoformat(season_data.valid_to).date() if season_data.valid_to else None,
            cost_multiplier=Decimal(str(season_data.cost_multiplier)) if season_data.cost_multiplier else None,
            cost_override=Decimal(str(season_data.cost_override)) if season_data.cost_override else None,
        )
        db.add(season)

    await db.commit()
    await db.refresh(item)

    return ItemResponse.model_validate(item)


@router.get("/formulas/{formula_id}/items", response_model=List[ItemResponse])
async def list_items(
    formula_id: int,
    db: DbSession,
    tenant: CurrentTenant,
):
    """
    List all items in a formula.
    """
    result = await db.execute(
        select(Item)
        .where(Item.formula_id == formula_id, Item.tenant_id == tenant.id)
        .order_by(Item.sort_order)
    )
    items = result.scalars().all()

    return [ItemResponse.model_validate(i) for i in items]


@router.get("/items/{item_id}", response_model=ItemResponse)
async def get_item(
    item_id: int,
    db: DbSession,
    tenant: CurrentTenant,
):
    """
    Get a single item.
    """
    result = await db.execute(
        select(Item).where(Item.id == item_id, Item.tenant_id == tenant.id)
    )
    item = result.scalar_one_or_none()

    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Item not found",
        )

    return ItemResponse.model_validate(item)


@router.patch("/items/{item_id}", response_model=ItemResponse)
async def update_item(
    item_id: int,
    data: ItemUpdate,
    db: DbSession,
    tenant: CurrentTenant,
    user: CurrentUser,
):
    """
    Update an item.
    """
    result = await db.execute(
        select(Item).where(Item.id == item_id, Item.tenant_id == tenant.id)
    )
    item = result.scalar_one_or_none()

    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Item not found",
        )

    update_data = data.model_dump(exclude_unset=True)

    # Handle Decimal conversions
    if "unit_cost" in update_data:
        update_data["unit_cost"] = Decimal(str(update_data["unit_cost"]))
    if "pricing_value" in update_data and update_data["pricing_value"] is not None:
        update_data["pricing_value"] = Decimal(str(update_data["pricing_value"]))

    for field, value in update_data.items():
        setattr(item, field, value)

    await db.commit()
    await db.refresh(item)

    return ItemResponse.model_validate(item)


@router.delete("/items/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_item(
    item_id: int,
    db: DbSession,
    tenant: CurrentTenant,
    user: CurrentUser,
):
    """
    Delete an item.
    """
    result = await db.execute(
        select(Item).where(Item.id == item_id, Item.tenant_id == tenant.id)
    )
    item = result.scalar_one_or_none()

    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Item not found",
        )

    await db.delete(item)
    await db.commit()


@router.post("/items/{item_id}/duplicate", response_model=ItemResponse)
async def duplicate_item(
    item_id: int,
    db: DbSession,
    tenant: CurrentTenant,
    user: CurrentUser,
    target_formula_id: Optional[int] = None,
):
    """
    Duplicate an item, optionally to a different formula.
    """
    result = await db.execute(
        select(Item)
        .where(Item.id == item_id, Item.tenant_id == tenant.id)
        .options(selectinload(Item.seasons))
    )
    source_item = result.scalar_one_or_none()

    if not source_item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Item not found",
        )

    # Verify target formula if specified
    formula_id = target_formula_id or source_item.formula_id
    if target_formula_id:
        result = await db.execute(
            select(Formula).where(Formula.id == target_formula_id, Formula.tenant_id == tenant.id)
        )
        if not result.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Target formula not found",
            )

    # Create duplicate
    new_item = Item(
        tenant_id=tenant.id,
        formula_id=formula_id,
        name=f"{source_item.name} (copie)",
        cost_nature_id=source_item.cost_nature_id,
        supplier_id=source_item.supplier_id,
        rate_catalog_id=source_item.rate_catalog_id,
        contract_rate_id=source_item.contract_rate_id,
        currency=source_item.currency,
        unit_cost=source_item.unit_cost,
        pricing_method=source_item.pricing_method,
        pricing_value=source_item.pricing_value,
        ratio_categories=source_item.ratio_categories,
        ratio_per=source_item.ratio_per,
        ratio_type=source_item.ratio_type,
        times_type=source_item.times_type,
        times_value=source_item.times_value,
        sort_order=source_item.sort_order + 1,
    )
    db.add(new_item)
    await db.flush()

    # Copy seasons
    for season in source_item.seasons:
        new_season = ItemSeason(
            tenant_id=tenant.id,
            item_id=new_item.id,
            season_name=season.season_name,
            valid_from=season.valid_from,
            valid_to=season.valid_to,
            cost_multiplier=season.cost_multiplier,
            cost_override=season.cost_override,
        )
        db.add(new_season)

    await db.commit()
    await db.refresh(new_item)

    return ItemResponse.model_validate(new_item)
