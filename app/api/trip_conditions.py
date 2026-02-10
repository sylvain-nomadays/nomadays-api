"""
Trip-level condition activation and option selection.

Manages which conditions are active for a specific trip and which option is selected.
Example: Trip 123 → Condition "Langue guide" → selected_option "Français", is_active=True
"""

from typing import List, Optional

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.api.deps import DbSession, CurrentUser, CurrentTenant
from app.api.conditions import ConditionOptionResponse
from app.models.trip import Trip
from app.models.condition import Condition, ConditionOption, TripCondition

router = APIRouter()


# ============ SCHEMAS ============

class TripConditionCreate(BaseModel):
    condition_id: int
    is_active: bool = True
    selected_option_id: Optional[int] = None


class TripConditionUpdate(BaseModel):
    is_active: Optional[bool] = None
    selected_option_id: Optional[int] = None


class TripConditionResponse(BaseModel):
    id: int
    trip_id: int
    condition_id: int
    condition_name: str
    applies_to: str = "all"
    selected_option_id: Optional[int] = None
    selected_option_label: Optional[str] = None
    is_active: bool
    options: List[ConditionOptionResponse] = []

    class Config:
        from_attributes = True


def _build_response(tc: TripCondition) -> TripConditionResponse:
    """Build a TripConditionResponse from a loaded TripCondition entity."""
    condition = tc.condition
    return TripConditionResponse(
        id=tc.id,
        trip_id=tc.trip_id,
        condition_id=tc.condition_id,
        condition_name=condition.name if condition else "?",
        applies_to=condition.applies_to if condition else "all",
        selected_option_id=tc.selected_option_id,
        selected_option_label=tc.selected_option.label if tc.selected_option else None,
        is_active=tc.is_active,
        options=[
            ConditionOptionResponse.model_validate(opt)
            for opt in (condition.options if condition else [])
        ],
    )


# ============ ENDPOINTS ============

@router.get("/trips/{trip_id}/conditions", response_model=List[TripConditionResponse])
async def list_trip_conditions(
    trip_id: int,
    db: DbSession,
    tenant: CurrentTenant,
):
    """List all conditions activated for this trip, with their options."""
    # Verify trip
    result = await db.execute(
        select(Trip).where(Trip.id == trip_id, Trip.tenant_id == tenant.id)
    )
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Trip not found")

    result = await db.execute(
        select(TripCondition)
        .where(TripCondition.trip_id == trip_id, TripCondition.tenant_id == tenant.id)
        .options(
            selectinload(TripCondition.condition).selectinload(Condition.options),
            selectinload(TripCondition.selected_option),
        )
        .order_by(TripCondition.id)
    )
    trip_conditions = result.scalars().all()
    return [_build_response(tc) for tc in trip_conditions]


@router.post("/trips/{trip_id}/conditions", response_model=TripConditionResponse, status_code=status.HTTP_201_CREATED)
async def activate_condition(
    trip_id: int,
    data: TripConditionCreate,
    db: DbSession,
    tenant: CurrentTenant,
    user: CurrentUser,
):
    """Activate a condition for this trip."""
    # Verify trip
    result = await db.execute(
        select(Trip).where(Trip.id == trip_id, Trip.tenant_id == tenant.id)
    )
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Trip not found")

    # Verify condition exists
    result = await db.execute(
        select(Condition).where(Condition.id == data.condition_id, Condition.tenant_id == tenant.id)
    )
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Condition not found")

    # Check not already activated
    result = await db.execute(
        select(TripCondition).where(
            TripCondition.trip_id == trip_id,
            TripCondition.condition_id == data.condition_id,
        )
    )
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Condition already activated for this trip",
        )

    # Validate selected_option_id if provided
    if data.selected_option_id:
        result = await db.execute(
            select(ConditionOption).where(
                ConditionOption.id == data.selected_option_id,
                ConditionOption.condition_id == data.condition_id,
            )
        )
        if not result.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Selected option does not belong to this condition",
            )

    tc = TripCondition(
        tenant_id=tenant.id,
        trip_id=trip_id,
        condition_id=data.condition_id,
        selected_option_id=data.selected_option_id,
        is_active=data.is_active,
    )
    db.add(tc)
    await db.commit()

    # Reload with relations
    result = await db.execute(
        select(TripCondition)
        .where(TripCondition.id == tc.id)
        .options(
            selectinload(TripCondition.condition).selectinload(Condition.options),
            selectinload(TripCondition.selected_option),
        )
    )
    tc = result.scalar_one()
    return _build_response(tc)


@router.patch("/trips/{trip_id}/conditions/{tc_id}", response_model=TripConditionResponse)
async def update_trip_condition(
    trip_id: int,
    tc_id: int,
    data: TripConditionUpdate,
    db: DbSession,
    tenant: CurrentTenant,
    user: CurrentUser,
):
    """Update a trip condition: toggle is_active or change selected option."""
    result = await db.execute(
        select(TripCondition)
        .where(
            TripCondition.id == tc_id,
            TripCondition.trip_id == trip_id,
            TripCondition.tenant_id == tenant.id,
        )
        .options(
            selectinload(TripCondition.condition).selectinload(Condition.options),
            selectinload(TripCondition.selected_option),
        )
    )
    tc = result.scalar_one_or_none()
    if not tc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Trip condition not found")

    # Validate selected_option_id if being changed
    if data.selected_option_id is not None:
        if data.selected_option_id:
            result = await db.execute(
                select(ConditionOption).where(
                    ConditionOption.id == data.selected_option_id,
                    ConditionOption.condition_id == tc.condition_id,
                )
            )
            if not result.scalar_one_or_none():
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Selected option does not belong to this condition",
                )

    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(tc, field, value)

    await db.commit()

    # Reload
    result = await db.execute(
        select(TripCondition)
        .where(TripCondition.id == tc.id)
        .options(
            selectinload(TripCondition.condition).selectinload(Condition.options),
            selectinload(TripCondition.selected_option),
        )
    )
    tc = result.scalar_one()
    return _build_response(tc)


@router.delete("/trips/{trip_id}/conditions/{tc_id}", status_code=status.HTTP_204_NO_CONTENT)
async def deactivate_condition(
    trip_id: int,
    tc_id: int,
    db: DbSession,
    tenant: CurrentTenant,
    user: CurrentUser,
):
    """Remove a condition from this trip."""
    result = await db.execute(
        select(TripCondition).where(
            TripCondition.id == tc_id,
            TripCondition.trip_id == trip_id,
            TripCondition.tenant_id == tenant.id,
        )
    )
    tc = result.scalar_one_or_none()
    if not tc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Trip condition not found")

    await db.delete(tc)
    await db.commit()
