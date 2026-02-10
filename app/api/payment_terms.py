"""
Payment Terms API - CRUD operations for supplier payment conditions.
"""

from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select, update

from app.api.deps import DbSession, TenantId
from app.models.payment_terms import PaymentTerms
from app.models.supplier import Supplier


router = APIRouter(prefix="/payment-terms", tags=["payment-terms"])


# ============================================================================
# Schemas
# ============================================================================

class PaymentInstallmentDTO(BaseModel):
    """A single payment installment."""
    percentage: float = Field(..., ge=0, le=100, description="Percentage of total amount")
    reference: str = Field(..., description="Reference point: confirmation, departure, service, return, invoice")
    days_offset: int = Field(..., description="Days before (-) or after (+) reference date")
    label: Optional[str] = Field(None, description="Label for this installment (e.g., 'Acompte', 'Solde')")


class PaymentTermsCreateDTO(BaseModel):
    """Create payment terms."""
    supplier_id: Optional[int] = None
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    installments: List[PaymentInstallmentDTO] = Field(default_factory=list)
    is_default: bool = False
    is_active: bool = True


class PaymentTermsUpdateDTO(BaseModel):
    """Update payment terms."""
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    installments: Optional[List[PaymentInstallmentDTO]] = None
    is_default: Optional[bool] = None
    is_active: Optional[bool] = None


class PaymentTermsResponse(BaseModel):
    """Payment terms response."""
    id: int
    tenant_id: str
    supplier_id: Optional[int] = None
    name: str
    description: Optional[str] = None
    installments: List[dict]
    is_default: bool
    is_active: bool
    created_at: str
    updated_at: str

    class Config:
        from_attributes = True


# ============================================================================
# Helper functions
# ============================================================================

def payment_terms_to_response(pt: PaymentTerms) -> PaymentTermsResponse:
    """Convert PaymentTerms model to response."""
    return PaymentTermsResponse(
        id=pt.id,
        tenant_id=str(pt.tenant_id),
        supplier_id=pt.supplier_id,
        name=pt.name,
        description=pt.description,
        installments=pt.installments or [],
        is_default=pt.is_default,
        is_active=pt.is_active,
        created_at=pt.created_at.isoformat() if pt.created_at else "",
        updated_at=pt.updated_at.isoformat() if pt.updated_at else "",
    )


# ============================================================================
# Endpoints
# ============================================================================

@router.get("", response_model=List[PaymentTermsResponse])
async def list_payment_terms(
    db: DbSession,
    tenant_id: TenantId,
    supplier_id: Optional[int] = Query(None, description="Filter by supplier"),
    is_active: Optional[bool] = Query(None, description="Filter by active status"),
):
    """List payment terms for the current tenant."""
    query = select(PaymentTerms).where(PaymentTerms.tenant_id == tenant_id)

    if supplier_id is not None:
        query = query.where(PaymentTerms.supplier_id == supplier_id)

    if is_active is not None:
        query = query.where(PaymentTerms.is_active == is_active)

    query = query.order_by(PaymentTerms.name)

    result = await db.execute(query)
    terms = result.scalars().all()

    return [payment_terms_to_response(pt) for pt in terms]


@router.get("/{payment_terms_id}", response_model=PaymentTermsResponse)
async def get_payment_terms(
    payment_terms_id: int,
    db: DbSession,
    tenant_id: TenantId,
):
    """Get a specific payment terms by ID."""
    query = select(PaymentTerms).where(
        PaymentTerms.id == payment_terms_id,
        PaymentTerms.tenant_id == tenant_id,
    )

    result = await db.execute(query)
    pt = result.scalar_one_or_none()

    if not pt:
        raise HTTPException(status_code=404, detail="Payment terms not found")

    return payment_terms_to_response(pt)


@router.post("", response_model=PaymentTermsResponse, status_code=201)
async def create_payment_terms(
    data: PaymentTermsCreateDTO,
    db: DbSession,
    tenant_id: TenantId,
):
    """Create new payment terms."""
    # Verify supplier exists if provided
    if data.supplier_id:
        supplier_query = select(Supplier).where(
            Supplier.id == data.supplier_id,
            Supplier.tenant_id == tenant_id,
        )
        result = await db.execute(supplier_query)
        supplier = result.scalar_one_or_none()
        if not supplier:
            raise HTTPException(status_code=404, detail="Supplier not found")

    # If this is marked as default, unset other defaults for the same supplier
    if data.is_default and data.supplier_id:
        await db.execute(
            update(PaymentTerms)
            .where(
                PaymentTerms.supplier_id == data.supplier_id,
                PaymentTerms.is_default == True,
            )
            .values(is_default=False)
        )

    # Convert installments to dict format
    installments = [inst.model_dump() for inst in data.installments]

    # Create new payment terms
    pt = PaymentTerms(
        tenant_id=tenant_id,
        supplier_id=data.supplier_id,
        name=data.name,
        description=data.description,
        installments=installments,
        is_default=data.is_default,
        is_active=data.is_active,
    )

    db.add(pt)
    await db.commit()
    await db.refresh(pt)

    return payment_terms_to_response(pt)


@router.patch("/{payment_terms_id}", response_model=PaymentTermsResponse)
async def update_payment_terms(
    payment_terms_id: int,
    data: PaymentTermsUpdateDTO,
    db: DbSession,
    tenant_id: TenantId,
):
    """Update payment terms."""
    query = select(PaymentTerms).where(
        PaymentTerms.id == payment_terms_id,
        PaymentTerms.tenant_id == tenant_id,
    )

    result = await db.execute(query)
    pt = result.scalar_one_or_none()

    if not pt:
        raise HTTPException(status_code=404, detail="Payment terms not found")

    # If setting as default, unset other defaults for the same supplier
    if data.is_default is True and pt.supplier_id:
        await db.execute(
            update(PaymentTerms)
            .where(
                PaymentTerms.supplier_id == pt.supplier_id,
                PaymentTerms.is_default == True,
                PaymentTerms.id != payment_terms_id,
            )
            .values(is_default=False)
        )

    # Update fields
    if data.name is not None:
        pt.name = data.name
    if data.description is not None:
        pt.description = data.description
    if data.installments is not None:
        pt.installments = [inst.model_dump() for inst in data.installments]
    if data.is_default is not None:
        pt.is_default = data.is_default
    if data.is_active is not None:
        pt.is_active = data.is_active

    await db.commit()
    await db.refresh(pt)

    return payment_terms_to_response(pt)


@router.delete("/{payment_terms_id}", status_code=204)
async def delete_payment_terms(
    payment_terms_id: int,
    db: DbSession,
    tenant_id: TenantId,
):
    """Delete payment terms."""
    query = select(PaymentTerms).where(
        PaymentTerms.id == payment_terms_id,
        PaymentTerms.tenant_id == tenant_id,
    )

    result = await db.execute(query)
    pt = result.scalar_one_or_none()

    if not pt:
        raise HTTPException(status_code=404, detail="Payment terms not found")

    await db.delete(pt)
    await db.commit()

    return None


@router.post("/{payment_terms_id}/set-default", response_model=PaymentTermsResponse)
async def set_default_payment_terms(
    payment_terms_id: int,
    db: DbSession,
    tenant_id: TenantId,
):
    """Set payment terms as default for its supplier."""
    query = select(PaymentTerms).where(
        PaymentTerms.id == payment_terms_id,
        PaymentTerms.tenant_id == tenant_id,
    )

    result = await db.execute(query)
    pt = result.scalar_one_or_none()

    if not pt:
        raise HTTPException(status_code=404, detail="Payment terms not found")

    if not pt.supplier_id:
        raise HTTPException(status_code=400, detail="Cannot set as default: payment terms has no supplier")

    # Unset other defaults for the same supplier
    await db.execute(
        update(PaymentTerms)
        .where(
            PaymentTerms.supplier_id == pt.supplier_id,
            PaymentTerms.is_default == True,
        )
        .values(is_default=False)
    )

    # Set this one as default
    pt.is_default = True

    # Also update the supplier's default_payment_terms_id
    supplier_query = select(Supplier).where(Supplier.id == pt.supplier_id)
    result = await db.execute(supplier_query)
    supplier = result.scalar_one_or_none()
    if supplier:
        supplier.default_payment_terms_id = pt.id

    await db.commit()
    await db.refresh(pt)

    return payment_terms_to_response(pt)
