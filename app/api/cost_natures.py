"""
Cost Nature management endpoints.
Defines how an item cost is processed after trip confirmation
(booking, purchase order, payroll, cash advance).
Auto-seeds 6 default cost natures per tenant on first access.
"""

from typing import List, Optional

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select

from app.api.deps import DbSession, CurrentUser, CurrentTenant
from app.models.cost_nature import CostNature

router = APIRouter()


# ─── Default cost natures (auto-seeded per tenant) ───────────────────
DEFAULT_COST_NATURES = [
    {"code": "HTL", "label": "Hébergement",       "generates_booking": True},
    {"code": "TRS", "label": "Transport",          "generates_booking": True},
    {"code": "ACT", "label": "Activité/Excursion", "generates_booking": True},
    {"code": "GDE", "label": "Équipe",             "generates_payroll": True},
    {"code": "RES", "label": "Restauration",       "generates_booking": True},
    {"code": "MIS", "label": "Divers",             "generates_purchase_order": True},
]


# ─── Schemas ─────────────────────────────────────────────────────────
class CostNatureResponse(BaseModel):
    """Cost nature response."""
    id: int
    code: str
    label: str
    generates_booking: bool
    generates_purchase_order: bool
    generates_payroll: bool
    generates_advance: bool
    vat_recoverable_default: bool
    accounting_code: Optional[str]
    is_system: bool

    class Config:
        from_attributes = True


class CostNatureListResponse(BaseModel):
    """List response."""
    items: List[CostNatureResponse]
    total: int


# ─── Helpers ─────────────────────────────────────────────────────────
async def _seed_cost_natures(db, tenant) -> list:
    """Auto-seed default cost natures for a tenant on first access."""
    natures = []
    for data in DEFAULT_COST_NATURES:
        nature = CostNature(
            tenant_id=tenant.id,
            code=data["code"],
            label=data["label"],
            generates_booking=data.get("generates_booking", False),
            generates_purchase_order=data.get("generates_purchase_order", False),
            generates_payroll=data.get("generates_payroll", False),
            generates_advance=data.get("generates_advance", False),
            is_system=True,
        )
        db.add(nature)
        natures.append(nature)
    await db.commit()
    for n in natures:
        await db.refresh(n)
    return natures


# ─── Endpoints ───────────────────────────────────────────────────────
@router.get("", response_model=CostNatureListResponse)
async def list_cost_natures(
    db: DbSession,
    tenant: CurrentTenant,
):
    """
    List all cost natures for the current tenant.
    Auto-seeds defaults on first access.
    """
    query = (
        select(CostNature)
        .where(CostNature.tenant_id == tenant.id)
        .order_by(CostNature.code)
    )

    result = await db.execute(query)
    natures = result.scalars().all()

    # Auto-seed if empty
    if not natures:
        natures = await _seed_cost_natures(db, tenant)

    return CostNatureListResponse(
        items=[CostNatureResponse.model_validate(n) for n in natures],
        total=len(natures),
    )


@router.get("/{nature_id}", response_model=CostNatureResponse)
async def get_cost_nature(
    nature_id: int,
    db: DbSession,
    tenant: CurrentTenant,
):
    """
    Get a cost nature by ID.
    """
    result = await db.execute(
        select(CostNature).where(
            CostNature.id == nature_id,
            CostNature.tenant_id == tenant.id,
        )
    )
    nature = result.scalar_one_or_none()

    if not nature:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Cost nature not found",
        )

    return CostNatureResponse.model_validate(nature)
