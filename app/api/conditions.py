"""
Tenant-level condition management endpoints.

Conditions are global templates with options/values, reusable across all circuits.
Examples: "Guide language" with options Français/Anglais/Allemand/Espagnol
"""

from typing import List, Optional

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.api.deps import DbSession, CurrentUser, CurrentTenant
from app.models.condition import Condition, ConditionOption

router = APIRouter()


# ============ SCHEMAS ============

class ConditionOptionCreate(BaseModel):
    label: str
    sort_order: int = 0


class ConditionOptionResponse(BaseModel):
    id: int
    condition_id: int
    label: str
    sort_order: int

    class Config:
        from_attributes = True


class ConditionOptionUpdate(BaseModel):
    label: Optional[str] = None
    sort_order: Optional[int] = None


class ConditionCreate(BaseModel):
    name: str
    description: Optional[str] = None
    applies_to: str = "all"  # 'all', 'accommodation', 'service', 'accompaniment'
    options: List[ConditionOptionCreate] = []


class ConditionUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    applies_to: Optional[str] = None


class ConditionResponse(BaseModel):
    id: int
    name: str
    description: Optional[str] = None
    applies_to: str = "all"
    options: List[ConditionOptionResponse] = []

    class Config:
        from_attributes = True


# ============ CONDITION CRUD ============

@router.get("", response_model=List[ConditionResponse])
async def list_conditions(
    db: DbSession,
    tenant: CurrentTenant,
):
    """List all conditions for the tenant (with their options)."""
    result = await db.execute(
        select(Condition)
        .where(Condition.tenant_id == tenant.id)
        .options(selectinload(Condition.options))
        .order_by(Condition.name)
    )
    conditions = result.scalars().all()
    return [ConditionResponse.model_validate(c) for c in conditions]


@router.post("", response_model=ConditionResponse, status_code=status.HTTP_201_CREATED)
async def create_condition(
    data: ConditionCreate,
    db: DbSession,
    tenant: CurrentTenant,
    user: CurrentUser,
):
    """Create a new condition with initial options."""
    condition = Condition(
        tenant_id=tenant.id,
        name=data.name,
        description=data.description,
        applies_to=data.applies_to,
    )
    db.add(condition)
    await db.flush()

    # Create initial options
    for i, opt in enumerate(data.options):
        option = ConditionOption(
            tenant_id=tenant.id,
            condition_id=condition.id,
            label=opt.label,
            sort_order=opt.sort_order if opt.sort_order else i,
        )
        db.add(option)

    await db.commit()

    # Reload with options
    result = await db.execute(
        select(Condition)
        .where(Condition.id == condition.id)
        .options(selectinload(Condition.options))
    )
    condition = result.scalar_one()
    return ConditionResponse.model_validate(condition)


@router.get("/{condition_id}", response_model=ConditionResponse)
async def get_condition(
    condition_id: int,
    db: DbSession,
    tenant: CurrentTenant,
):
    """Get a condition with its options."""
    result = await db.execute(
        select(Condition)
        .where(Condition.id == condition_id, Condition.tenant_id == tenant.id)
        .options(selectinload(Condition.options))
    )
    condition = result.scalar_one_or_none()
    if not condition:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Condition not found")
    return ConditionResponse.model_validate(condition)


@router.patch("/{condition_id}", response_model=ConditionResponse)
async def update_condition(
    condition_id: int,
    data: ConditionUpdate,
    db: DbSession,
    tenant: CurrentTenant,
    user: CurrentUser,
):
    """Update condition name/description."""
    result = await db.execute(
        select(Condition)
        .where(Condition.id == condition_id, Condition.tenant_id == tenant.id)
        .options(selectinload(Condition.options))
    )
    condition = result.scalar_one_or_none()
    if not condition:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Condition not found")

    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(condition, field, value)

    await db.commit()
    await db.refresh(condition)
    return ConditionResponse.model_validate(condition)


@router.delete("/{condition_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_condition(
    condition_id: int,
    db: DbSession,
    tenant: CurrentTenant,
    user: CurrentUser,
):
    """Delete a condition and all its options. Cascades to trip_conditions."""
    result = await db.execute(
        select(Condition).where(Condition.id == condition_id, Condition.tenant_id == tenant.id)
    )
    condition = result.scalar_one_or_none()
    if not condition:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Condition not found")

    await db.delete(condition)
    await db.commit()


# ============ OPTION CRUD ============

@router.post("/{condition_id}/options", response_model=ConditionOptionResponse, status_code=status.HTTP_201_CREATED)
async def add_option(
    condition_id: int,
    data: ConditionOptionCreate,
    db: DbSession,
    tenant: CurrentTenant,
    user: CurrentUser,
):
    """Add an option to a condition."""
    result = await db.execute(
        select(Condition).where(Condition.id == condition_id, Condition.tenant_id == tenant.id)
    )
    condition = result.scalar_one_or_none()
    if not condition:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Condition not found")

    option = ConditionOption(
        tenant_id=tenant.id,
        condition_id=condition_id,
        label=data.label,
        sort_order=data.sort_order,
    )
    db.add(option)
    await db.commit()
    await db.refresh(option)
    return ConditionOptionResponse.model_validate(option)


@router.patch("/{condition_id}/options/{option_id}", response_model=ConditionOptionResponse)
async def update_option(
    condition_id: int,
    option_id: int,
    data: ConditionOptionUpdate,
    db: DbSession,
    tenant: CurrentTenant,
    user: CurrentUser,
):
    """Update an option's label or sort_order."""
    result = await db.execute(
        select(ConditionOption).where(
            ConditionOption.id == option_id,
            ConditionOption.condition_id == condition_id,
            ConditionOption.tenant_id == tenant.id,
        )
    )
    option = result.scalar_one_or_none()
    if not option:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Option not found")

    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(option, field, value)

    await db.commit()
    await db.refresh(option)
    return ConditionOptionResponse.model_validate(option)


@router.delete("/{condition_id}/options/{option_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_option(
    condition_id: int,
    option_id: int,
    db: DbSession,
    tenant: CurrentTenant,
    user: CurrentUser,
):
    """Delete an option. Items referencing it will have condition_option_id set to NULL."""
    result = await db.execute(
        select(ConditionOption).where(
            ConditionOption.id == option_id,
            ConditionOption.condition_id == condition_id,
            ConditionOption.tenant_id == tenant.id,
        )
    )
    option = result.scalar_one_or_none()
    if not option:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Option not found")

    await db.delete(option)
    await db.commit()
