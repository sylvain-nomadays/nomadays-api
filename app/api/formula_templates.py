"""
Formula template management endpoints.

Template formulas are reusable blocks (is_template=True) that can be
copied into circuits and kept in sync via versioning.
"""

from typing import List, Optional
from datetime import datetime

from fastapi import APIRouter, HTTPException, status, Query
from pydantic import BaseModel
from sqlalchemy import select, func, update
from sqlalchemy.orm import selectinload

from app.api.deps import DbSession, CurrentUser, CurrentTenant
from app.models.formula import Formula
from app.models.item import Item, ItemPriceTier
from app.api.formulas import (
    _duplicate_formula,
    FormulaResponse,
    ItemResponse,
)

router = APIRouter(prefix="/formula-templates", tags=["Formula Templates"])


# ============ SCHEMAS ============

class FormulaTemplateListItem(BaseModel):
    id: int
    name: str
    description_html: Optional[str] = None
    block_type: str
    template_category: Optional[str] = None
    template_tags: Optional[list] = None
    template_location_id: Optional[int] = None
    template_country_code: Optional[str] = None
    template_version: int = 1
    items_count: int = 0
    children_count: int = 0
    usage_count: int = 0
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class FormulaTemplateCreate(BaseModel):
    name: str
    description_html: Optional[str] = None
    block_type: str = "activity"
    template_category: Optional[str] = None
    template_tags: Optional[list] = None
    template_location_id: Optional[int] = None
    template_country_code: Optional[str] = None


class FormulaTemplateUpdate(BaseModel):
    name: Optional[str] = None
    description_html: Optional[str] = None
    template_category: Optional[str] = None
    template_tags: Optional[list] = None
    template_location_id: Optional[int] = None
    template_country_code: Optional[str] = None


class FormulaTemplateUsageItem(BaseModel):
    formula_id: int
    trip_id: Optional[int] = None
    trip_name: Optional[str] = None
    source_version: Optional[int] = None
    template_version: int = 1
    status: str  # 'in_sync' | 'template_updated'

    class Config:
        from_attributes = True


class FormulaTemplateUsageResponse(BaseModel):
    template_id: int
    template_version: int
    usages: List[FormulaTemplateUsageItem] = []


class PropagateRequest(BaseModel):
    formula_ids: List[int]


class PropagateResponse(BaseModel):
    updated: int = 0
    errors: List[str] = []


# ============ HELPER ============

def _formula_eager_options():
    """Standard eager-load chain for formula templates."""
    return [
        selectinload(Formula.items).selectinload(Item.price_tiers),
        selectinload(Formula.children).selectinload(Formula.items).selectinload(Item.price_tiers),
    ]


# ============ ENDPOINTS ============

@router.get("", response_model=List[FormulaTemplateListItem])
async def list_formula_templates(
    db: DbSession,
    tenant: CurrentTenant,
    user: CurrentUser,
    category: Optional[str] = None,
    country_code: Optional[str] = None,
    search: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
):
    """List all formula templates for this tenant."""
    query = (
        select(Formula)
        .where(
            Formula.tenant_id == tenant.id,
            Formula.is_template == True,  # noqa: E712
            Formula.parent_block_id.is_(None),  # Only top-level templates
        )
        .order_by(Formula.updated_at.desc())
    )

    if category:
        query = query.where(Formula.template_category == category)
    if country_code:
        query = query.where(Formula.template_country_code == country_code)
    if search:
        query = query.where(Formula.name.ilike(f"%{search}%"))

    # Pagination
    query = query.offset((page - 1) * page_size).limit(page_size)

    # Eager-load items and children for count
    query = query.options(*_formula_eager_options())

    result = await db.execute(query)
    templates = result.scalars().all()

    # Build response with counts
    items = []
    for t in templates:
        # Count usages (formulas pointing to this template)
        usage_result = await db.execute(
            select(func.count(Formula.id)).where(
                Formula.template_source_id == t.id,
                Formula.tenant_id == tenant.id,
                Formula.is_template == False,  # noqa: E712
            )
        )
        usage_count = usage_result.scalar() or 0

        items.append(FormulaTemplateListItem(
            id=t.id,
            name=t.name,
            description_html=t.description_html,
            block_type=t.block_type,
            template_category=t.template_category,
            template_tags=t.template_tags,
            template_location_id=t.template_location_id,
            template_country_code=t.template_country_code,
            template_version=t.template_version,
            items_count=len(t.items or []),
            children_count=len(t.children or []),
            usage_count=usage_count,
            created_at=t.created_at,
            updated_at=t.updated_at,
        ))

    return items


@router.get("/{template_id}", response_model=FormulaResponse)
async def get_formula_template(
    template_id: int,
    db: DbSession,
    tenant: CurrentTenant,
    user: CurrentUser,
):
    """Get a single formula template with all its items and children."""
    result = await db.execute(
        select(Formula)
        .where(
            Formula.id == template_id,
            Formula.tenant_id == tenant.id,
            Formula.is_template == True,  # noqa: E712
        )
        .options(*_formula_eager_options())
    )
    template = result.scalar_one_or_none()

    if not template:
        raise HTTPException(status_code=404, detail="Template not found")

    return template


@router.post("", response_model=FormulaResponse, status_code=status.HTTP_201_CREATED)
async def create_formula_template(
    data: FormulaTemplateCreate,
    db: DbSession,
    tenant: CurrentTenant,
    user: CurrentUser,
):
    """Create a new formula template from scratch."""
    new_template = Formula(
        tenant_id=tenant.id,
        trip_day_id=None,
        trip_id=None,
        name=data.name,
        description_html=data.description_html,
        block_type=data.block_type,
        is_template=True,
        template_version=1,
        template_category=data.template_category,
        template_tags=data.template_tags,
        template_location_id=data.template_location_id,
        template_country_code=data.template_country_code,
        sort_order=0,
    )
    db.add(new_template)
    await db.flush()
    await db.commit()

    # Reload with relationships
    result = await db.execute(
        select(Formula)
        .where(Formula.id == new_template.id)
        .options(*_formula_eager_options())
    )
    return result.scalar_one()


@router.patch("/{template_id}", response_model=FormulaResponse)
async def update_formula_template(
    template_id: int,
    data: FormulaTemplateUpdate,
    db: DbSession,
    tenant: CurrentTenant,
    user: CurrentUser,
):
    """Update a formula template metadata. Increments template_version."""
    result = await db.execute(
        select(Formula)
        .where(
            Formula.id == template_id,
            Formula.tenant_id == tenant.id,
            Formula.is_template == True,  # noqa: E712
        )
        .options(*_formula_eager_options())
    )
    template = result.scalar_one_or_none()

    if not template:
        raise HTTPException(status_code=404, detail="Template not found")

    # Apply updates
    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(template, field, value)

    # Increment version on any metadata update
    template.template_version += 1

    await db.flush()
    await db.commit()
    await db.refresh(template)

    return template


@router.delete("/{template_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_formula_template(
    template_id: int,
    db: DbSession,
    tenant: CurrentTenant,
    user: CurrentUser,
):
    """Delete a formula template. Unlinks all usages (sets template_source_id=NULL)."""
    result = await db.execute(
        select(Formula)
        .where(
            Formula.id == template_id,
            Formula.tenant_id == tenant.id,
            Formula.is_template == True,  # noqa: E712
        )
    )
    template = result.scalar_one_or_none()

    if not template:
        raise HTTPException(status_code=404, detail="Template not found")

    # Unlink all usages first
    await db.execute(
        update(Formula)
        .where(Formula.template_source_id == template_id)
        .values(template_source_id=None, template_source_version=None)
    )

    # Delete the template (cascade deletes items and children)
    await db.delete(template)
    await db.commit()


@router.post("/from-formula/{formula_id}", response_model=FormulaResponse, status_code=status.HTTP_201_CREATED)
async def save_formula_as_template(
    formula_id: int,
    db: DbSession,
    tenant: CurrentTenant,
    user: CurrentUser,
    name: Optional[str] = Query(None, description="Override the template name"),
    category: Optional[str] = Query(None, description="Template category"),
):
    """
    Save an existing circuit formula as a reusable template.

    Deep-copies the formula (with items, children, price tiers) and marks it
    as a template (is_template=True).
    """
    # Load source formula with items and children
    result = await db.execute(
        select(Formula)
        .where(
            Formula.id == formula_id,
            Formula.tenant_id == tenant.id,
        )
        .options(*_formula_eager_options())
    )
    source = result.scalar_one_or_none()

    if not source:
        raise HTTPException(status_code=404, detail="Formula not found")

    # Duplicate as template
    new_template = await _duplicate_formula(
        db=db,
        tenant_id=tenant.id,
        source_formula=source,
        target_day_id=None,
        sort_order=0,
        as_template=True,
    )

    # Override name/category if provided
    if name:
        new_template.name = name
    if category:
        new_template.template_category = category
    elif not new_template.template_category:
        # Auto-detect category from block_type
        new_template.template_category = source.block_type

    await db.flush()
    await db.commit()

    # Reload with relationships
    result = await db.execute(
        select(Formula)
        .where(Formula.id == new_template.id)
        .options(*_formula_eager_options())
    )
    return result.scalar_one()


# ============ USAGE & SYNC ENDPOINTS ============

@router.get("/{template_id}/usage", response_model=FormulaTemplateUsageResponse)
async def get_template_usage(
    template_id: int,
    db: DbSession,
    tenant: CurrentTenant,
    user: CurrentUser,
):
    """
    List all circuit formulas that use this template, with sync status.
    """
    # Verify template exists
    result = await db.execute(
        select(Formula)
        .where(
            Formula.id == template_id,
            Formula.tenant_id == tenant.id,
            Formula.is_template == True,  # noqa: E712
        )
    )
    template = result.scalar_one_or_none()

    if not template:
        raise HTTPException(status_code=404, detail="Template not found")

    # Find all formulas linked to this template
    from app.models.trip import Trip, TripDay

    result = await db.execute(
        select(Formula, Trip.name.label("trip_name"), Trip.id.label("trip_id_val"))
        .outerjoin(TripDay, Formula.trip_day_id == TripDay.id)
        .outerjoin(Trip, TripDay.trip_id == Trip.id)
        .where(
            Formula.template_source_id == template_id,
            Formula.tenant_id == tenant.id,
            Formula.is_template == False,  # noqa: E712
        )
    )
    rows = result.all()

    usages = []
    for formula, trip_name, trip_id_val in rows:
        source_version = formula.template_source_version or 0
        sync_status = (
            "in_sync" if source_version >= template.template_version
            else "template_updated"
        )
        usages.append(FormulaTemplateUsageItem(
            formula_id=formula.id,
            trip_id=trip_id_val,
            trip_name=trip_name,
            source_version=source_version,
            template_version=template.template_version,
            status=sync_status,
        ))

    return FormulaTemplateUsageResponse(
        template_id=template_id,
        template_version=template.template_version,
        usages=usages,
    )


@router.post("/{template_id}/propagate", response_model=PropagateResponse)
async def propagate_template(
    template_id: int,
    data: PropagateRequest,
    db: DbSession,
    tenant: CurrentTenant,
    user: CurrentUser,
):
    """
    Propagate template changes to selected circuit formulas.
    Performs a pull-from-template on each formula_id in the list.
    """
    # Load template with items
    result = await db.execute(
        select(Formula)
        .where(
            Formula.id == template_id,
            Formula.tenant_id == tenant.id,
            Formula.is_template == True,  # noqa: E712
        )
        .options(*_formula_eager_options())
    )
    template = result.scalar_one_or_none()

    if not template:
        raise HTTPException(status_code=404, detail="Template not found")

    updated = 0
    errors = []

    for fid in data.formula_ids:
        try:
            await _pull_items_from_template(db, tenant.id, fid, template)
            updated += 1
        except Exception as e:
            errors.append(f"Formula {fid}: {str(e)}")

    await db.commit()

    return PropagateResponse(updated=updated, errors=errors)


# ============ INTERNAL HELPERS ============

async def _pull_items_from_template(
    db: DbSession,
    tenant_id: int,
    formula_id: int,
    template: Formula,
):
    """
    Replace a formula's items with the template's items (pull/sync).
    Used by both pull-from-template and propagate endpoints.
    """
    # Load target formula
    result = await db.execute(
        select(Formula)
        .where(
            Formula.id == formula_id,
            Formula.tenant_id == tenant_id,
            Formula.template_source_id == template.id,
        )
        .options(selectinload(Formula.items).selectinload(Item.price_tiers))
    )
    formula = result.scalar_one_or_none()

    if not formula:
        raise ValueError(f"Formula {formula_id} not found or not linked to template {template.id}")

    # Delete existing items
    for item in list(formula.items or []):
        await db.delete(item)
    await db.flush()

    # Copy items from template
    for source_item in (template.items or []):
        new_item = Item(
            tenant_id=tenant_id,
            formula_id=formula.id,
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
            category_prices_json=source_item.category_prices_json,
            sort_order=source_item.sort_order,
        )
        db.add(new_item)
        await db.flush()

        # Copy price tiers
        for tier in (source_item.price_tiers or []):
            db.add(ItemPriceTier(
                tenant_id=tenant_id,
                item_id=new_item.id,
                pax_min=tier.pax_min,
                pax_max=tier.pax_max,
                unit_cost=tier.unit_cost,
                category_adjustments_json=tier.category_adjustments_json,
                category_prices_json=tier.category_prices_json,
                sort_order=tier.sort_order,
            ))

    # Update formula metadata and description
    formula.name = template.name
    formula.description_html = template.description_html
    formula.template_source_version = template.template_version

    await db.flush()
