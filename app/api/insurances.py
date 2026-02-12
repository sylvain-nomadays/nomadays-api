"""
Trip insurance management endpoints — Chapka Explorer integration (READY, not connected).
Minimal CRUD for tracking travel insurance quotes and policies per dossier.
"""

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Optional, List

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select, func

from app.api.deps import CurrentUser, CurrentTenant, DbSession
from app.models.trip_insurance import TripInsurance

router = APIRouter()


# ============================================================================
# Schemas
# ============================================================================

class InsuranceCreate(BaseModel):
    dossier_id: uuid.UUID
    insurance_type: str  # assistance, annulation, multirisques
    provider: str = "chapka"
    policy_number: Optional[str] = None
    premium_amount: Optional[Decimal] = None
    commission_pct: Decimal = Decimal("25.00")
    currency: str = "EUR"
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    pax_count: Optional[int] = None
    notes: Optional[str] = None


class InsuranceUpdate(BaseModel):
    insurance_type: Optional[str] = None
    policy_number: Optional[str] = None
    premium_amount: Optional[Decimal] = None
    commission_pct: Optional[Decimal] = None
    currency: Optional[str] = None
    status: Optional[str] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    pax_count: Optional[int] = None
    notes: Optional[str] = None


class InsuranceResponse(BaseModel):
    id: int
    dossier_id: uuid.UUID
    invoice_id: Optional[int] = None
    insurance_type: str
    provider: str
    policy_number: Optional[str] = None
    premium_amount: Optional[Decimal] = None
    commission_pct: Decimal
    commission_amount: Optional[Decimal] = None
    currency: str
    status: str
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    pax_count: Optional[int] = None
    notes: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class InsuranceListResponse(BaseModel):
    items: List[InsuranceResponse]
    total: int


# ============================================================================
# Endpoints
# ============================================================================

@router.get("", response_model=InsuranceListResponse)
async def list_insurances(
    db: DbSession,
    tenant: CurrentTenant,
    dossier_id: Optional[uuid.UUID] = None,
    status_filter: Optional[str] = Query(None, alias="status"),
):
    """List trip insurances, optionally filtered by dossier."""
    query = select(TripInsurance).where(TripInsurance.tenant_id == tenant.id)
    count_query = select(func.count()).select_from(TripInsurance).where(TripInsurance.tenant_id == tenant.id)

    if dossier_id:
        query = query.where(TripInsurance.dossier_id == dossier_id)
        count_query = count_query.where(TripInsurance.dossier_id == dossier_id)

    if status_filter:
        query = query.where(TripInsurance.status == status_filter)
        count_query = count_query.where(TripInsurance.status == status_filter)

    query = query.order_by(TripInsurance.created_at.desc())

    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    result = await db.execute(query)
    items = result.scalars().all()

    return InsuranceListResponse(
        items=[InsuranceResponse.model_validate(i) for i in items],
        total=total,
    )


@router.post("", response_model=InsuranceResponse, status_code=status.HTTP_201_CREATED)
async def create_insurance(
    data: InsuranceCreate,
    db: DbSession,
    tenant: CurrentTenant,
):
    """Create a new trip insurance record."""
    if data.insurance_type not in ("assistance", "annulation", "multirisques"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid insurance type. Must be: assistance, annulation, or multirisques",
        )

    # Calculate commission amount
    commission_amount = None
    if data.premium_amount is not None:
        commission_amount = (data.premium_amount * data.commission_pct / Decimal("100")).quantize(Decimal("0.01"))

    insurance = TripInsurance(
        tenant_id=tenant.id,
        dossier_id=data.dossier_id,
        insurance_type=data.insurance_type,
        provider=data.provider,
        policy_number=data.policy_number,
        premium_amount=data.premium_amount,
        commission_pct=data.commission_pct,
        commission_amount=commission_amount,
        currency=data.currency,
        status="quoted",
        start_date=data.start_date,
        end_date=data.end_date,
        pax_count=data.pax_count,
        notes=data.notes,
    )
    db.add(insurance)
    await db.commit()
    await db.refresh(insurance)

    return InsuranceResponse.model_validate(insurance)


@router.get("/{insurance_id}", response_model=InsuranceResponse)
async def get_insurance(
    insurance_id: int,
    db: DbSession,
    tenant: CurrentTenant,
):
    """Get a trip insurance record."""
    result = await db.execute(
        select(TripInsurance)
        .where(TripInsurance.id == insurance_id, TripInsurance.tenant_id == tenant.id)
    )
    insurance = result.scalar_one_or_none()
    if not insurance:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Insurance not found")

    return InsuranceResponse.model_validate(insurance)


@router.patch("/{insurance_id}", response_model=InsuranceResponse)
async def update_insurance(
    insurance_id: int,
    data: InsuranceUpdate,
    db: DbSession,
    tenant: CurrentTenant,
):
    """Update a trip insurance record."""
    result = await db.execute(
        select(TripInsurance)
        .where(TripInsurance.id == insurance_id, TripInsurance.tenant_id == tenant.id)
    )
    insurance = result.scalar_one_or_none()
    if not insurance:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Insurance not found")

    update_data = data.model_dump(exclude_unset=True)

    for field, value in update_data.items():
        setattr(insurance, field, value)

    # Recalculate commission if premium or percentage changed
    if insurance.premium_amount is not None:
        insurance.commission_amount = (
            insurance.premium_amount * insurance.commission_pct / Decimal("100")
        ).quantize(Decimal("0.01"))

    await db.commit()
    await db.refresh(insurance)

    return InsuranceResponse.model_validate(insurance)


@router.delete("/{insurance_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_insurance(
    insurance_id: int,
    db: DbSession,
    tenant: CurrentTenant,
):
    """Delete a trip insurance record (only quoted status)."""
    result = await db.execute(
        select(TripInsurance)
        .where(TripInsurance.id == insurance_id, TripInsurance.tenant_id == tenant.id)
    )
    insurance = result.scalar_one_or_none()
    if not insurance:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Insurance not found")

    if insurance.status != "quoted":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only quoted insurances can be deleted",
        )

    await db.delete(insurance)
    await db.commit()
