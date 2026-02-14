"""
Promo codes CRUD — admin-only endpoints.
Promo codes are centralized (Nomadays-level, not per-tenant).
Only admin/manager roles can manage promo codes.
"""

from datetime import date
from decimal import Decimal
from typing import Optional, List

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import CurrentUser, DbSession
from app.models.promo_code import PromoCode, PromoCodeUsage

router = APIRouter()


# ============================================================================
# Schemas
# ============================================================================

class PromoCodeCreate(BaseModel):
    code: str = Field(..., max_length=50)
    description: Optional[str] = None
    discount_type: str = Field(..., pattern="^(fixed|percentage)$")
    discount_value: Decimal = Field(..., gt=0)
    currency: str = Field("EUR", max_length=3)
    min_amount: Decimal = Field(Decimal("0"), ge=0)
    max_uses: Optional[int] = Field(None, ge=1)
    valid_from: Optional[date] = None
    valid_until: Optional[date] = None


class PromoCodeUpdate(BaseModel):
    description: Optional[str] = None
    discount_type: Optional[str] = Field(None, pattern="^(fixed|percentage)$")
    discount_value: Optional[Decimal] = Field(None, gt=0)
    currency: Optional[str] = Field(None, max_length=3)
    min_amount: Optional[Decimal] = Field(None, ge=0)
    max_uses: Optional[int] = None
    valid_from: Optional[date] = None
    valid_until: Optional[date] = None
    is_active: Optional[bool] = None


class PromoCodeResponse(BaseModel):
    id: int
    code: str
    description: Optional[str]
    discount_type: str
    discount_value: float
    currency: str
    min_amount: float
    max_uses: Optional[int]
    current_uses: int
    valid_from: Optional[str]
    valid_until: Optional[str]
    is_active: bool
    created_at: str
    updated_at: str


class PromoCodeUsageResponse(BaseModel):
    id: int
    invoice_id: int
    discount_amount: float
    applied_at: str


# ============================================================================
# Helpers
# ============================================================================

def _check_admin(user: CurrentUser):
    """Ensure user is admin or manager."""
    if user.role not in ("admin", "manager"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Seuls les administrateurs peuvent gérer les codes promo",
        )


def _to_response(promo: PromoCode) -> dict:
    return {
        "id": promo.id,
        "code": promo.code,
        "description": promo.description,
        "discount_type": promo.discount_type,
        "discount_value": float(promo.discount_value),
        "currency": promo.currency,
        "min_amount": float(promo.min_amount) if promo.min_amount else 0,
        "max_uses": promo.max_uses,
        "current_uses": promo.current_uses or 0,
        "valid_from": str(promo.valid_from) if promo.valid_from else None,
        "valid_until": str(promo.valid_until) if promo.valid_until else None,
        "is_active": promo.is_active,
        "created_at": str(promo.created_at),
        "updated_at": str(promo.updated_at),
    }


# ============================================================================
# Endpoints
# ============================================================================

@router.get("")
async def list_promo_codes(
    user: CurrentUser,
    db: DbSession,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    active_only: bool = Query(False),
):
    """List all promo codes (admin/manager only)."""
    _check_admin(user)

    query = select(PromoCode).order_by(PromoCode.created_at.desc())
    if active_only:
        query = query.where(PromoCode.is_active == True)

    query = query.offset(skip).limit(limit)
    result = await db.execute(query)
    promos = result.scalars().all()

    # Count total
    count_query = select(func.count(PromoCode.id))
    if active_only:
        count_query = count_query.where(PromoCode.is_active == True)
    count_result = await db.execute(count_query)
    total = count_result.scalar() or 0

    return {
        "items": [_to_response(p) for p in promos],
        "total": total,
        "skip": skip,
        "limit": limit,
    }


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_promo_code(
    body: PromoCodeCreate,
    user: CurrentUser,
    db: DbSession,
):
    """Create a new promo code (admin/manager only)."""
    _check_admin(user)

    # Normalize code to uppercase
    code = body.code.upper().strip()

    # Check uniqueness
    existing = await db.execute(
        select(PromoCode).where(PromoCode.code == code)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Le code '{code}' existe déjà",
        )

    promo = PromoCode(
        code=code,
        description=body.description,
        discount_type=body.discount_type,
        discount_value=body.discount_value,
        currency=body.currency,
        min_amount=body.min_amount,
        max_uses=body.max_uses,
        valid_from=body.valid_from,
        valid_until=body.valid_until,
    )
    db.add(promo)
    await db.commit()
    await db.refresh(promo)

    return _to_response(promo)


@router.get("/{promo_id}")
async def get_promo_code(
    promo_id: int,
    user: CurrentUser,
    db: DbSession,
):
    """Get a single promo code (admin/manager only)."""
    _check_admin(user)

    result = await db.execute(
        select(PromoCode).where(PromoCode.id == promo_id)
    )
    promo = result.scalar_one_or_none()
    if not promo:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Code promo introuvable")

    return _to_response(promo)


@router.patch("/{promo_id}")
async def update_promo_code(
    promo_id: int,
    body: PromoCodeUpdate,
    user: CurrentUser,
    db: DbSession,
):
    """Update a promo code (admin/manager only)."""
    _check_admin(user)

    result = await db.execute(
        select(PromoCode).where(PromoCode.id == promo_id)
    )
    promo = result.scalar_one_or_none()
    if not promo:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Code promo introuvable")

    update_data = body.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(promo, field, value)

    await db.commit()
    await db.refresh(promo)

    return _to_response(promo)


@router.delete("/{promo_id}")
async def delete_promo_code(
    promo_id: int,
    user: CurrentUser,
    db: DbSession,
):
    """Soft-delete a promo code by setting is_active=false (admin/manager only)."""
    _check_admin(user)

    result = await db.execute(
        select(PromoCode).where(PromoCode.id == promo_id)
    )
    promo = result.scalar_one_or_none()
    if not promo:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Code promo introuvable")

    promo.is_active = False
    await db.commit()

    return {"message": "Code promo désactivé", "id": promo_id}


@router.get("/{promo_id}/usages")
async def get_promo_code_usages(
    promo_id: int,
    user: CurrentUser,
    db: DbSession,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
):
    """Get usage history for a promo code (admin/manager only)."""
    _check_admin(user)

    # Verify promo exists
    result = await db.execute(
        select(PromoCode).where(PromoCode.id == promo_id)
    )
    promo = result.scalar_one_or_none()
    if not promo:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Code promo introuvable")

    # Get usages
    result = await db.execute(
        select(PromoCodeUsage)
        .where(PromoCodeUsage.promo_code_id == promo_id)
        .order_by(PromoCodeUsage.applied_at.desc())
        .offset(skip)
        .limit(limit)
    )
    usages = result.scalars().all()

    return {
        "promo_code": promo.code,
        "items": [
            {
                "id": u.id,
                "invoice_id": u.invoice_id,
                "discount_amount": float(u.discount_amount),
                "applied_at": str(u.applied_at),
            }
            for u in usages
        ],
    }
