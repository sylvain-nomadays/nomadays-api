"""
Forex hedge management endpoints — Kantox integration (READY, not connected).
Minimal CRUD for tracking forex hedging operations per dossier.
Two purchases per dossier: deposit and balance.
"""

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Optional, List

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select, func

from app.api.deps import CurrentUser, CurrentTenant, DbSession
from app.models.forex_hedge import ForexHedge

router = APIRouter()


# ============================================================================
# Schemas
# ============================================================================

class ForexHedgeCreate(BaseModel):
    dossier_id: uuid.UUID
    hedge_type: str  # deposit, balance
    provider: str = "kantox"
    reference: Optional[str] = None
    from_currency: str
    to_currency: str
    amount: Decimal
    rate: Optional[Decimal] = None
    purchase_date: Optional[date] = None
    notes: Optional[str] = None


class ForexHedgeUpdate(BaseModel):
    reference: Optional[str] = None
    rate: Optional[Decimal] = None
    purchase_date: Optional[date] = None
    status: Optional[str] = None
    notes: Optional[str] = None


class ForexHedgeResponse(BaseModel):
    id: int
    dossier_id: uuid.UUID
    invoice_id: Optional[int] = None
    hedge_type: str
    provider: str
    reference: Optional[str] = None
    from_currency: str
    to_currency: str
    amount: Decimal
    rate: Optional[Decimal] = None
    purchase_date: Optional[date] = None
    executed_at: Optional[datetime] = None
    status: str
    notes: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ForexHedgeListResponse(BaseModel):
    items: List[ForexHedgeResponse]
    total: int


# ============================================================================
# Endpoints
# ============================================================================

@router.get("", response_model=ForexHedgeListResponse)
async def list_forex_hedges(
    db: DbSession,
    tenant: CurrentTenant,
    dossier_id: Optional[uuid.UUID] = None,
    status_filter: Optional[str] = Query(None, alias="status"),
):
    """List forex hedges, optionally filtered by dossier."""
    query = select(ForexHedge).where(ForexHedge.tenant_id == tenant.id)
    count_query = select(func.count()).select_from(ForexHedge).where(ForexHedge.tenant_id == tenant.id)

    if dossier_id:
        query = query.where(ForexHedge.dossier_id == dossier_id)
        count_query = count_query.where(ForexHedge.dossier_id == dossier_id)

    if status_filter:
        query = query.where(ForexHedge.status == status_filter)
        count_query = count_query.where(ForexHedge.status == status_filter)

    query = query.order_by(ForexHedge.created_at.desc())

    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    result = await db.execute(query)
    items = result.scalars().all()

    return ForexHedgeListResponse(
        items=[ForexHedgeResponse.model_validate(i) for i in items],
        total=total,
    )


@router.post("", response_model=ForexHedgeResponse, status_code=status.HTTP_201_CREATED)
async def create_forex_hedge(
    data: ForexHedgeCreate,
    db: DbSession,
    tenant: CurrentTenant,
):
    """Create a new forex hedge record."""
    if data.hedge_type not in ("deposit", "balance"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid hedge type. Must be: deposit or balance",
        )

    hedge = ForexHedge(
        tenant_id=tenant.id,
        dossier_id=data.dossier_id,
        hedge_type=data.hedge_type,
        provider=data.provider,
        reference=data.reference,
        from_currency=data.from_currency,
        to_currency=data.to_currency,
        amount=data.amount,
        rate=data.rate,
        purchase_date=data.purchase_date,
        status="pending",
        notes=data.notes,
    )
    db.add(hedge)
    await db.commit()
    await db.refresh(hedge)

    return ForexHedgeResponse.model_validate(hedge)


@router.get("/{hedge_id}", response_model=ForexHedgeResponse)
async def get_forex_hedge(
    hedge_id: int,
    db: DbSession,
    tenant: CurrentTenant,
):
    """Get a forex hedge record."""
    result = await db.execute(
        select(ForexHedge)
        .where(ForexHedge.id == hedge_id, ForexHedge.tenant_id == tenant.id)
    )
    hedge = result.scalar_one_or_none()
    if not hedge:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Forex hedge not found")

    return ForexHedgeResponse.model_validate(hedge)


@router.patch("/{hedge_id}", response_model=ForexHedgeResponse)
async def update_forex_hedge(
    hedge_id: int,
    data: ForexHedgeUpdate,
    db: DbSession,
    tenant: CurrentTenant,
):
    """Update a forex hedge record."""
    result = await db.execute(
        select(ForexHedge)
        .where(ForexHedge.id == hedge_id, ForexHedge.tenant_id == tenant.id)
    )
    hedge = result.scalar_one_or_none()
    if not hedge:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Forex hedge not found")

    update_data = data.model_dump(exclude_unset=True)

    # If status is being changed to "executed", set executed_at
    if update_data.get("status") == "executed" and hedge.status != "executed":
        hedge.executed_at = datetime.utcnow()

    for field, value in update_data.items():
        setattr(hedge, field, value)

    await db.commit()
    await db.refresh(hedge)

    return ForexHedgeResponse.model_validate(hedge)


@router.delete("/{hedge_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_forex_hedge(
    hedge_id: int,
    db: DbSession,
    tenant: CurrentTenant,
):
    """Delete a forex hedge record (only pending status)."""
    result = await db.execute(
        select(ForexHedge)
        .where(ForexHedge.id == hedge_id, ForexHedge.tenant_id == tenant.id)
    )
    hedge = result.scalar_one_or_none()
    if not hedge:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Forex hedge not found")

    if hedge.status != "pending":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only pending hedges can be deleted",
        )

    await db.delete(hedge)
    await db.commit()
