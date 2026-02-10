"""
Formula and Item management endpoints.
"""

from typing import List, Optional
from decimal import Decimal

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, model_validator
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.api.deps import DbSession, CurrentUser, CurrentTenant
from app.models.trip import TripDay
from app.models.formula import Formula
from app.models.condition import Condition
from app.models.item import Item, ItemSeason, ItemPriceTier
from app.models.cost_nature import CostNature

router = APIRouter()


# ============ SCHEMAS ============

# Price Tier Schemas
class ItemPriceTierCreate(BaseModel):
    pax_min: int
    pax_max: int
    unit_cost: float
    category_adjustments_json: Optional[dict] = None
    sort_order: int = 0


class ItemPriceTierResponse(BaseModel):
    id: int
    pax_min: int
    pax_max: int
    unit_cost: float
    category_adjustments_json: Optional[dict] = None
    sort_order: int = 0

    class Config:
        from_attributes = True


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
    payment_flow: Optional[str] = None  # booking, advance, purchase_order, payroll, manual
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
    condition_option_id: Optional[int] = None
    price_includes_vat: bool = True  # Default TTC (hébergements = majorité des items)
    sort_order: int = 0
    seasons: List[ItemSeasonCreate] = []
    # Price tiers (optional)
    tier_categories: Optional[str] = None
    price_tiers: List[ItemPriceTierCreate] = []


class ItemUpdate(BaseModel):
    name: Optional[str] = None
    cost_nature_id: Optional[int] = None
    payment_flow: Optional[str] = None
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
    condition_option_id: Optional[int] = None
    price_includes_vat: Optional[bool] = None
    sort_order: Optional[int] = None
    # Price tiers (None = no change, [] = remove all)
    tier_categories: Optional[str] = None
    price_tiers: Optional[List[ItemPriceTierCreate]] = None


class ItemResponse(BaseModel):
    id: int
    formula_id: int
    name: str
    cost_nature_id: Optional[int]
    cost_nature_code: Optional[str] = None
    payment_flow: Optional[str]
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
    condition_option_id: Optional[int] = None
    price_includes_vat: bool = True
    sort_order: int
    tier_categories: Optional[str] = None
    price_tiers: List[ItemPriceTierResponse] = []

    class Config:
        from_attributes = True

    @model_validator(mode="wrap")
    @classmethod
    def resolve_cost_nature_code(cls, values, handler):
        """Resolve cost_nature_code from the SQLAlchemy relationship when available."""
        result = handler(values)
        # If cost_nature_code wasn't set and we have access to the ORM object
        if result.cost_nature_code is None and hasattr(values, 'cost_nature') and values.cost_nature is not None:
            result.cost_nature_code = values.cost_nature.code
        return result


# Formula Schemas


class FormulaCreate(BaseModel):
    name: str
    description_html: Optional[str] = None
    service_day_start: Optional[int] = None
    service_day_end: Optional[int] = None
    sort_order: int = 0
    block_type: str = "activity"
    parent_block_id: Optional[int] = None
    condition_id: Optional[int] = None


class FormulaUpdate(BaseModel):
    name: Optional[str] = None
    description_html: Optional[str] = None
    service_day_start: Optional[int] = None
    service_day_end: Optional[int] = None
    sort_order: Optional[int] = None
    block_type: Optional[str] = None
    parent_block_id: Optional[int] = None
    trip_day_id: Optional[int] = None
    condition_id: Optional[int] = None


class FormulaResponse(BaseModel):
    id: int
    trip_day_id: Optional[int] = None
    trip_id: Optional[int] = None
    is_transversal: bool = False
    name: str
    description_html: Optional[str]
    service_day_start: Optional[int]
    service_day_end: Optional[int]
    sort_order: int
    block_type: str = "activity"
    parent_block_id: Optional[int] = None
    condition_id: Optional[int] = None
    items: List["ItemResponse"] = []
    children: List["FormulaResponse"] = []

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
        block_type=data.block_type,
        parent_block_id=data.parent_block_id,
        condition_id=data.condition_id,
    )
    db.add(formula)
    await db.flush()
    await db.commit()

    # Reload with relations
    result = await db.execute(
        select(Formula)
        .where(Formula.id == formula.id)
        .options(
            selectinload(Formula.items).selectinload(Item.price_tiers),
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
            selectinload(Formula.items).selectinload(Item.price_tiers),
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
            selectinload(Formula.items).selectinload(Item.price_tiers),
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


# ============ BLOCK ENDPOINTS ============

@router.get("/days/{day_id}/blocks", response_model=List[FormulaResponse])
async def list_blocks(
    day_id: int,
    db: DbSession,
    tenant: CurrentTenant,
):
    """
    List all top-level blocks for a trip day, with children nested.
    Returns only parent blocks (parent_block_id IS NULL).
    Children are included via the 'children' relationship.
    """
    result = await db.execute(
        select(Formula)
        .where(
            Formula.trip_day_id == day_id,
            Formula.tenant_id == tenant.id,
            Formula.parent_block_id.is_(None),
        )
        .options(
            selectinload(Formula.items).selectinload(Item.price_tiers),
            selectinload(Formula.children).selectinload(Formula.items).selectinload(Item.price_tiers),
        )
        .order_by(Formula.sort_order)
    )
    blocks = result.scalars().all()
    return [FormulaResponse.model_validate(b) for b in blocks]


class BlockReorderRequest(BaseModel):
    block_ids: List[int]


@router.patch("/days/{day_id}/blocks/reorder")
async def reorder_blocks(
    day_id: int,
    data: BlockReorderRequest,
    db: DbSession,
    tenant: CurrentTenant,
    user: CurrentUser,
):
    """
    Update sort_order for top-level blocks within a day.
    """
    for idx, block_id in enumerate(data.block_ids):
        result = await db.execute(
            select(Formula).where(
                Formula.id == block_id,
                Formula.tenant_id == tenant.id,
                Formula.trip_day_id == day_id,
                Formula.parent_block_id.is_(None),
            )
        )
        formula = result.scalar_one_or_none()
        if formula:
            formula.sort_order = idx

    await db.commit()
    return {"status": "ok"}


class MoveBlockRequest(BaseModel):
    target_day_id: int
    sort_order: int = 0


@router.patch("/formulas/{formula_id}/move")
async def move_block(
    formula_id: int,
    data: MoveBlockRequest,
    db: DbSession,
    tenant: CurrentTenant,
    user: CurrentUser,
):
    """
    Move a block (and all its children) to another day.
    """
    result = await db.execute(
        select(Formula)
        .where(Formula.id == formula_id, Formula.tenant_id == tenant.id)
        .options(selectinload(Formula.children))
    )
    formula = result.scalar_one_or_none()

    if not formula:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Formula not found",
        )

    # Only allow moving top-level blocks
    if formula.parent_block_id is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot move a sub-formula. Move the parent block instead.",
        )

    # Verify target day belongs to same tenant
    result = await db.execute(
        select(TripDay).where(
            TripDay.id == data.target_day_id,
            TripDay.tenant_id == tenant.id,
        )
    )
    target_day = result.scalar_one_or_none()
    if not target_day:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Target day not found",
        )

    # Move block and all children to the new day
    formula.trip_day_id = data.target_day_id
    formula.sort_order = data.sort_order
    for child in formula.children:
        child.trip_day_id = data.target_day_id

    await db.commit()
    return {"status": "ok"}


# ============ DUPLICATE / COPY ENDPOINTS ============


async def _duplicate_formula(
    db: DbSession,
    tenant_id: int,
    source_formula: Formula,
    target_day_id: int,
    sort_order: int = 0,
) -> Formula:
    """
    Deep-copy a formula (with children and items) to a target day.
    Reuses the 2-pass pattern from _copy_trip_structure in trips.py.
    """
    # Create the new formula
    new_formula = Formula(
        tenant_id=tenant_id,
        trip_day_id=target_day_id,
        name=source_formula.name,
        description_html=source_formula.description_html,
        service_day_start=source_formula.service_day_start,
        service_day_end=source_formula.service_day_end,
        template_source_id=source_formula.id,
        sort_order=sort_order,
        block_type=source_formula.block_type,
        parent_block_id=None,
        condition_id=source_formula.condition_id,
    )
    db.add(new_formula)
    await db.flush()

    # Copy items
    for source_item in (source_formula.items or []):
        new_item = Item(
            tenant_id=tenant_id,
            formula_id=new_formula.id,
            name=source_item.name,
            cost_nature_id=source_item.cost_nature_id,
            payment_flow=source_item.payment_flow,
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
            condition_option_id=source_item.condition_option_id,
            price_includes_vat=source_item.price_includes_vat,
            tier_categories=source_item.tier_categories,
            sort_order=source_item.sort_order,
        )
        db.add(new_item)
        await db.flush()
        # Copy price tiers
        for tier in (source_item.price_tiers or []):
            db.add(ItemPriceTier(
                tenant_id=tenant_id, item_id=new_item.id,
                pax_min=tier.pax_min, pax_max=tier.pax_max,
                unit_cost=tier.unit_cost,
                category_adjustments_json=tier.category_adjustments_json,
                sort_order=tier.sort_order,
            ))

    # Copy children (pass 2)
    for source_child in (source_formula.children or []):
        new_child = Formula(
            tenant_id=tenant_id,
            trip_day_id=target_day_id,
            name=source_child.name,
            description_html=source_child.description_html,
            service_day_start=source_child.service_day_start,
            service_day_end=source_child.service_day_end,
            template_source_id=source_child.id,
            sort_order=source_child.sort_order,
            block_type=source_child.block_type,
            parent_block_id=new_formula.id,
        )
        db.add(new_child)
        await db.flush()

        # Copy child items
        for source_item in (source_child.items or []):
            new_item = Item(
                tenant_id=tenant_id,
                formula_id=new_child.id,
                name=source_item.name,
                cost_nature_id=source_item.cost_nature_id,
                payment_flow=source_item.payment_flow,
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
                condition_option_id=source_item.condition_option_id,
                price_includes_vat=source_item.price_includes_vat,
                tier_categories=source_item.tier_categories,
                sort_order=source_item.sort_order,
            )
            db.add(new_item)
            await db.flush()
            # Copy price tiers
            for tier in (source_item.price_tiers or []):
                db.add(ItemPriceTier(
                    tenant_id=tenant_id, item_id=new_item.id,
                    pax_min=tier.pax_min, pax_max=tier.pax_max,
                    unit_cost=tier.unit_cost,
                    category_adjustments_json=tier.category_adjustments_json,
                    sort_order=tier.sort_order,
                ))

    return new_formula


class DuplicateBlockRequest(BaseModel):
    target_day_id: int
    sort_order: int = 0


@router.post("/formulas/{formula_id}/duplicate", response_model=FormulaResponse, status_code=status.HTTP_201_CREATED)
async def duplicate_block(
    formula_id: int,
    data: DuplicateBlockRequest,
    db: DbSession,
    tenant: CurrentTenant,
    user: CurrentUser,
):
    """
    Duplicate a top-level block (with children and items) to a target day.
    Cross-trip is allowed (e.g. copying from a template to a circuit).
    """
    # Load source formula with children and items
    result = await db.execute(
        select(Formula)
        .where(Formula.id == formula_id, Formula.tenant_id == tenant.id)
        .options(
            selectinload(Formula.items).selectinload(Item.price_tiers),
            selectinload(Formula.children).selectinload(Formula.items).selectinload(Item.price_tiers),
        )
    )
    source_formula = result.scalar_one_or_none()

    if not source_formula:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Formula not found",
        )

    # Only allow duplicating top-level blocks
    if source_formula.parent_block_id is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot duplicate a sub-formula. Duplicate the parent block instead.",
        )

    # Verify target day belongs to same tenant
    result = await db.execute(
        select(TripDay).where(
            TripDay.id == data.target_day_id,
            TripDay.tenant_id == tenant.id,
        )
    )
    target_day = result.scalar_one_or_none()
    if not target_day:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Target day not found",
        )

    new_formula = await _duplicate_formula(
        db, tenant.id, source_formula, data.target_day_id, data.sort_order
    )

    await db.commit()

    # Reload with relationships for response
    result = await db.execute(
        select(Formula)
        .where(Formula.id == new_formula.id)
        .options(
            selectinload(Formula.items).selectinload(Item.price_tiers),
            selectinload(Formula.children).selectinload(Formula.items).selectinload(Item.price_tiers),
        )
    )
    return result.scalar_one()


class CopyDayBlocksRequest(BaseModel):
    target_day_id: int


@router.post("/days/{source_day_id}/copy-blocks", response_model=List[FormulaResponse], status_code=status.HTTP_201_CREATED)
async def copy_day_blocks(
    source_day_id: int,
    data: CopyDayBlocksRequest,
    db: DbSession,
    tenant: CurrentTenant,
    user: CurrentUser,
):
    """
    Copy all top-level blocks from a source day to a target day.
    Useful for importing an entire day from a template or another circuit.
    """
    # Verify source day
    result = await db.execute(
        select(TripDay).where(
            TripDay.id == source_day_id,
            TripDay.tenant_id == tenant.id,
        )
    )
    source_day = result.scalar_one_or_none()
    if not source_day:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Source day not found",
        )

    # Verify target day
    result = await db.execute(
        select(TripDay).where(
            TripDay.id == data.target_day_id,
            TripDay.tenant_id == tenant.id,
        )
    )
    target_day = result.scalar_one_or_none()
    if not target_day:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Target day not found",
        )

    # Load all top-level blocks from source day
    result = await db.execute(
        select(Formula)
        .where(
            Formula.trip_day_id == source_day_id,
            Formula.tenant_id == tenant.id,
            Formula.parent_block_id.is_(None),
        )
        .options(
            selectinload(Formula.items).selectinload(Item.price_tiers),
            selectinload(Formula.children).selectinload(Formula.items).selectinload(Item.price_tiers),
        )
        .order_by(Formula.sort_order)
    )
    source_blocks = result.scalars().all()

    new_formula_ids = []
    for idx, source_block in enumerate(source_blocks):
        new_formula = await _duplicate_formula(
            db, tenant.id, source_block, data.target_day_id, sort_order=idx
        )
        new_formula_ids.append(new_formula.id)

    await db.commit()

    # Reload all new formulas for response
    result = await db.execute(
        select(Formula)
        .where(Formula.id.in_(new_formula_ids))
        .options(
            selectinload(Formula.items).selectinload(Item.price_tiers),
            selectinload(Formula.children).selectinload(Formula.items).selectinload(Item.price_tiers),
        )
        .order_by(Formula.sort_order)
    )
    return result.scalars().all()


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

    # Resolve price_includes_vat from CostNature default if not explicitly set
    # (The frontend sends it explicitly, but API callers may omit it)
    price_includes_vat = data.price_includes_vat
    if data.cost_nature_id:
        cn_result = await db.execute(
            select(CostNature).where(
                CostNature.id == data.cost_nature_id,
                CostNature.tenant_id == tenant.id,
            )
        )
        cost_nature = cn_result.scalar_one_or_none()
        if cost_nature and price_includes_vat == True:
            # Only override the default if user didn't explicitly change it
            # Default in schema is True, so if it's True we use cost_nature default
            price_includes_vat = cost_nature.vat_recoverable_default

    item = Item(
        tenant_id=tenant.id,
        formula_id=formula_id,
        name=data.name,
        cost_nature_id=data.cost_nature_id,
        payment_flow=data.payment_flow,
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
        condition_option_id=data.condition_option_id,
        price_includes_vat=price_includes_vat,
        tier_categories=data.tier_categories,
        sort_order=data.sort_order,
    )
    db.add(item)
    await db.flush()

    # Add price tiers
    for tier_data in data.price_tiers:
        tier = ItemPriceTier(
            tenant_id=tenant.id,
            item_id=item.id,
            pax_min=tier_data.pax_min,
            pax_max=tier_data.pax_max,
            unit_cost=Decimal(str(tier_data.unit_cost)),
            category_adjustments_json=tier_data.category_adjustments_json,
            sort_order=tier_data.sort_order,
        )
        db.add(tier)

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

    # Extract price_tiers before generic field update
    price_tiers_data = update_data.pop("price_tiers", None)

    # Handle Decimal conversions
    if "unit_cost" in update_data:
        update_data["unit_cost"] = Decimal(str(update_data["unit_cost"]))
    if "pricing_value" in update_data and update_data["pricing_value"] is not None:
        update_data["pricing_value"] = Decimal(str(update_data["pricing_value"]))

    for field, value in update_data.items():
        setattr(item, field, value)

    # Handle price tiers (replace-all strategy)
    if price_tiers_data is not None:
        # Delete existing tiers
        existing_tiers = await db.execute(
            select(ItemPriceTier).where(
                ItemPriceTier.item_id == item.id,
                ItemPriceTier.tenant_id == tenant.id,
            )
        )
        for old_tier in existing_tiers.scalars().all():
            await db.delete(old_tier)
        await db.flush()

        # Create new tiers
        for tier_data in price_tiers_data:
            tier = ItemPriceTier(
                tenant_id=tenant.id,
                item_id=item.id,
                pax_min=tier_data["pax_min"],
                pax_max=tier_data["pax_max"],
                unit_cost=Decimal(str(tier_data["unit_cost"])),
                category_adjustments_json=tier_data.get("category_adjustments_json"),
                sort_order=tier_data.get("sort_order", 0),
            )
            db.add(tier)

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
        .options(selectinload(Item.seasons), selectinload(Item.price_tiers))
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
        payment_flow=source_item.payment_flow,
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
        condition_option_id=source_item.condition_option_id,
        price_includes_vat=source_item.price_includes_vat,
        tier_categories=source_item.tier_categories,
        sort_order=source_item.sort_order + 1,
    )
    db.add(new_item)
    await db.flush()

    # Copy price tiers
    for tier in (source_item.price_tiers or []):
        new_tier = ItemPriceTier(
            tenant_id=tenant.id,
            item_id=new_item.id,
            pax_min=tier.pax_min,
            pax_max=tier.pax_max,
            unit_cost=tier.unit_cost,
            category_adjustments_json=tier.category_adjustments_json,
            sort_order=tier.sort_order,
        )
        db.add(new_tier)

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
