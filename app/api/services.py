"""
Transversal services (trip-level formulas) management endpoints.

These are formulas linked directly to a trip (not to a specific day),
used for recurring services like guides, drivers, meals, allowances, etc.
"""

from typing import List, Optional

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.api.deps import DbSession, CurrentUser, CurrentTenant
from app.api.formulas import FormulaResponse, ItemResponse
from app.models.trip import Trip
from app.models.formula import Formula

router = APIRouter()


# ============ SCHEMAS ============

class TransversalFormulaCreate(BaseModel):
    name: str
    description_html: Optional[str] = None
    service_day_start: Optional[int] = None
    service_day_end: Optional[int] = None
    sort_order: int = 0
    block_type: str = "service"
    condition_id: Optional[int] = None


class TransversalFormulaUpdate(BaseModel):
    name: Optional[str] = None
    description_html: Optional[str] = None
    service_day_start: Optional[int] = None
    service_day_end: Optional[int] = None
    sort_order: Optional[int] = None
    block_type: Optional[str] = None
    condition_id: Optional[int] = None


# ============ TRANSVERSAL FORMULA ENDPOINTS ============

@router.get("/trips/{trip_id}/services", response_model=List[FormulaResponse])
async def list_transversal_formulas(
    trip_id: int,
    db: DbSession,
    tenant: CurrentTenant,
):
    """
    List all transversal formulas for a trip.
    """
    # Verify trip exists and belongs to tenant
    result = await db.execute(
        select(Trip).where(Trip.id == trip_id, Trip.tenant_id == tenant.id)
    )
    trip = result.scalar_one_or_none()
    if not trip:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Trip not found",
        )

    result = await db.execute(
        select(Formula)
        .where(
            Formula.trip_id == trip_id,
            Formula.is_transversal.is_(True),
            Formula.tenant_id == tenant.id,
        )
        .options(
            selectinload(Formula.items),
            selectinload(Formula.children).selectinload(Formula.items),
        )
        .order_by(Formula.sort_order)
    )
    formulas = result.scalars().all()

    return [FormulaResponse.model_validate(f) for f in formulas]


@router.post("/trips/{trip_id}/services", response_model=FormulaResponse, status_code=status.HTTP_201_CREATED)
async def create_transversal_formula(
    trip_id: int,
    data: TransversalFormulaCreate,
    db: DbSession,
    tenant: CurrentTenant,
    user: CurrentUser,
):
    """
    Create a new transversal formula for a trip.
    """
    # Verify trip exists and belongs to tenant
    result = await db.execute(
        select(Trip).where(Trip.id == trip_id, Trip.tenant_id == tenant.id)
    )
    trip = result.scalar_one_or_none()
    if not trip:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Trip not found",
        )

    formula = Formula(
        tenant_id=tenant.id,
        trip_id=trip_id,
        trip_day_id=None,
        is_transversal=True,
        name=data.name,
        description_html=data.description_html,
        service_day_start=data.service_day_start,
        service_day_end=data.service_day_end,
        sort_order=data.sort_order,
        block_type=data.block_type,
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
            selectinload(Formula.items),
            selectinload(Formula.children).selectinload(Formula.items),
        )
    )
    formula = result.scalar_one()

    return FormulaResponse.model_validate(formula)


@router.patch("/trips/{trip_id}/services/{formula_id}", response_model=FormulaResponse)
async def update_transversal_formula(
    trip_id: int,
    formula_id: int,
    data: TransversalFormulaUpdate,
    db: DbSession,
    tenant: CurrentTenant,
    user: CurrentUser,
):
    """
    Update a transversal formula.
    """
    result = await db.execute(
        select(Formula)
        .where(
            Formula.id == formula_id,
            Formula.trip_id == trip_id,
            Formula.is_transversal.is_(True),
            Formula.tenant_id == tenant.id,
        )
        .options(
            selectinload(Formula.items),
            selectinload(Formula.children).selectinload(Formula.items),
        )
    )
    formula = result.scalar_one_or_none()

    if not formula:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Transversal formula not found",
        )

    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(formula, field, value)

    await db.commit()
    await db.refresh(formula)

    return FormulaResponse.model_validate(formula)


@router.delete("/trips/{trip_id}/services/{formula_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_transversal_formula(
    trip_id: int,
    formula_id: int,
    db: DbSession,
    tenant: CurrentTenant,
    user: CurrentUser,
):
    """
    Delete a transversal formula and all its items.
    """
    result = await db.execute(
        select(Formula).where(
            Formula.id == formula_id,
            Formula.trip_id == trip_id,
            Formula.is_transversal.is_(True),
            Formula.tenant_id == tenant.id,
        )
    )
    formula = result.scalar_one_or_none()

    if not formula:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Transversal formula not found",
        )

    await db.delete(formula)
    await db.commit()
