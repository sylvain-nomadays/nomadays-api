"""
Supplier management endpoints.
Aligned with frontend types in /src/lib/api/types.ts
"""

from datetime import datetime
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, HTTPException, status, Query
from pydantic import BaseModel, Field
from sqlalchemy import select, func

from app.api.deps import DbSession, CurrentUser, CurrentTenant
from app.models.supplier import Supplier

router = APIRouter()


# ============================================================================
# Schemas - aligned with frontend types
# ============================================================================

# Type aliases matching frontend
SupplierType = str  # 'accommodation' | 'activity' | 'transport' | 'restaurant' | 'guide' | 'other'
SupplierStatus = str  # 'active' | 'inactive' | 'pending'


class SupplierCreate(BaseModel):
    """Create a new supplier - matches frontend CreateSupplierDTO"""
    name: str
    type: SupplierType  # accommodation, activity, transport, restaurant, guide, other
    status: Optional[SupplierStatus] = 'active'
    country_code: Optional[str] = None
    city: Optional[str] = None
    address: Optional[str] = None
    postal_code: Optional[str] = None
    contact_name: Optional[str] = None
    contact_email: Optional[str] = None
    contact_phone: Optional[str] = None
    website: Optional[str] = None
    tax_id: Optional[str] = None
    default_currency: Optional[str] = None
    # Notes
    internal_notes: Optional[str] = None
    logistics_notes: Optional[str] = None
    quality_notes: Optional[str] = None
    tags: Optional[List[str]] = None


class SupplierUpdate(BaseModel):
    """Update supplier - all fields optional"""
    name: Optional[str] = None
    type: Optional[SupplierType] = None
    status: Optional[SupplierStatus] = None
    country_code: Optional[str] = None
    city: Optional[str] = None
    address: Optional[str] = None
    postal_code: Optional[str] = None
    contact_name: Optional[str] = None
    contact_email: Optional[str] = None
    contact_phone: Optional[str] = None
    website: Optional[str] = None
    tax_id: Optional[str] = None
    default_currency: Optional[str] = None
    internal_notes: Optional[str] = None
    logistics_notes: Optional[str] = None
    quality_notes: Optional[str] = None
    tags: Optional[List[str]] = None
    is_active: Optional[bool] = None


class SupplierResponse(BaseModel):
    """Supplier response - matches frontend Supplier interface"""
    id: int
    tenant_id: str  # UUID as string for frontend compatibility
    name: str
    type: SupplierType
    status: SupplierStatus = 'active'
    # Location
    country_code: Optional[str] = None
    city: Optional[str] = None
    address: Optional[str] = None
    postal_code: Optional[str] = None
    # Contact
    contact_name: Optional[str] = None
    contact_email: Optional[str] = None
    contact_phone: Optional[str] = None
    website: Optional[str] = None
    # Financial
    tax_id: Optional[str] = None
    default_currency: Optional[str] = None
    # Notes
    internal_notes: Optional[str] = None
    logistics_notes: Optional[str] = None
    quality_notes: Optional[str] = None
    tags: Optional[List[str]] = None
    # Contract info (populated from relationships)
    active_contract_id: Optional[int] = None
    active_contract_name: Optional[str] = None
    contract_valid_to: Optional[str] = None
    contract_validity_status: Optional[str] = None  # valid, expiring_soon, expired, no_contract
    days_until_contract_expiry: Optional[int] = None
    # Timestamps
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class SupplierListResponse(BaseModel):
    """Paginated list response - matches frontend PaginatedResponse<Supplier>"""
    items: List[SupplierResponse]
    total: int
    page: int
    page_size: int


# ============================================================================
# Helper functions
# ============================================================================

def supplier_to_response(supplier: Supplier) -> SupplierResponse:
    """Convert SQLAlchemy model to Pydantic response with proper type conversions"""
    return SupplierResponse(
        id=supplier.id,
        tenant_id=str(supplier.tenant_id),  # UUID to string
        name=supplier.name,
        type=supplier.type,
        status='active' if supplier.is_active else 'inactive',
        country_code=supplier.country_code,
        city=supplier.city,
        address=supplier.address,
        postal_code=getattr(supplier, 'postal_code', None),
        contact_name=supplier.contact_name,
        contact_email=supplier.contact_email,
        contact_phone=supplier.contact_phone,
        website=getattr(supplier, 'website', None),
        tax_id=supplier.tax_id,
        default_currency=supplier.default_currency,
        internal_notes=getattr(supplier, 'internal_notes', None),
        logistics_notes=getattr(supplier, 'logistics_notes', None),
        quality_notes=getattr(supplier, 'quality_notes', None),
        tags=getattr(supplier, 'tags', None),
        # Contract info - TODO: populate from contracts relationship
        active_contract_id=None,
        active_contract_name=None,
        contract_valid_to=None,
        contract_validity_status='no_contract',
        days_until_contract_expiry=None,
        created_at=getattr(supplier, 'created_at', None),
        updated_at=getattr(supplier, 'updated_at', None),
    )


# ============================================================================
# Endpoints
# ============================================================================

@router.get("", response_model=SupplierListResponse)
async def list_suppliers(
    db: DbSession,
    tenant: CurrentTenant,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    type: Optional[str] = None,
    status: Optional[str] = None,
    search: Optional[str] = None,
    is_active: Optional[bool] = None,  # For backwards compatibility
):
    """
    List suppliers for the current tenant.
    Supports filtering by type, status, and search query.
    """
    # Base query
    query = select(Supplier).where(Supplier.tenant_id == tenant.id)

    # Filters
    if type:
        query = query.where(Supplier.type == type)

    # Status filter (maps to is_active)
    if status == 'active':
        query = query.where(Supplier.is_active == True)
    elif status == 'inactive':
        query = query.where(Supplier.is_active == False)
    elif is_active is not None:
        query = query.where(Supplier.is_active == is_active)

    if search:
        query = query.where(Supplier.name.ilike(f"%{search}%"))

    # Count total
    count_query = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_query)).scalar()

    # Pagination
    query = query.offset((page - 1) * page_size).limit(page_size)
    query = query.order_by(Supplier.name)

    result = await db.execute(query)
    suppliers = result.scalars().all()

    return SupplierListResponse(
        items=[supplier_to_response(s) for s in suppliers],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post("", response_model=SupplierResponse, status_code=status.HTTP_201_CREATED)
async def create_supplier(
    data: SupplierCreate,
    db: DbSession,
    tenant: CurrentTenant,
    user: CurrentUser,
):
    """
    Create a new supplier.
    """
    # Extract fields that map to model columns
    supplier_data = data.model_dump(exclude={'status', 'tags', 'postal_code', 'website', 'internal_notes', 'logistics_notes', 'quality_notes'})

    # Map status to is_active
    supplier_data['is_active'] = data.status != 'inactive' if data.status else True

    supplier = Supplier(
        tenant_id=tenant.id,
        **supplier_data,
    )
    db.add(supplier)
    await db.commit()
    await db.refresh(supplier)

    return supplier_to_response(supplier)


@router.get("/{supplier_id}", response_model=SupplierResponse)
async def get_supplier(
    supplier_id: int,
    db: DbSession,
    tenant: CurrentTenant,
):
    """
    Get a specific supplier.
    """
    result = await db.execute(
        select(Supplier).where(
            Supplier.id == supplier_id,
            Supplier.tenant_id == tenant.id,
        )
    )
    supplier = result.scalar_one_or_none()

    if not supplier:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Supplier not found",
        )

    return supplier_to_response(supplier)


@router.patch("/{supplier_id}", response_model=SupplierResponse)
async def update_supplier(
    supplier_id: int,
    data: SupplierUpdate,
    db: DbSession,
    tenant: CurrentTenant,
    user: CurrentUser,
):
    """
    Update a supplier.
    """
    result = await db.execute(
        select(Supplier).where(
            Supplier.id == supplier_id,
            Supplier.tenant_id == tenant.id,
        )
    )
    supplier = result.scalar_one_or_none()

    if not supplier:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Supplier not found",
        )

    # Update fields
    update_data = data.model_dump(exclude_unset=True)

    # Handle status -> is_active mapping
    if 'status' in update_data:
        status_val = update_data.pop('status')
        update_data['is_active'] = status_val != 'inactive'

    # Filter to only fields that exist on the model
    model_fields = {'name', 'type', 'contact_name', 'contact_email', 'contact_phone',
                    'country_code', 'city', 'address', 'tax_id', 'default_currency', 'is_active'}

    for field, value in update_data.items():
        if field in model_fields:
            setattr(supplier, field, value)

    await db.commit()
    await db.refresh(supplier)

    return supplier_to_response(supplier)


@router.delete("/{supplier_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_supplier(
    supplier_id: int,
    db: DbSession,
    tenant: CurrentTenant,
    user: CurrentUser,
):
    """
    Delete a supplier (soft delete by setting is_active=False).
    """
    result = await db.execute(
        select(Supplier).where(
            Supplier.id == supplier_id,
            Supplier.tenant_id == tenant.id,
        )
    )
    supplier = result.scalar_one_or_none()

    if not supplier:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Supplier not found",
        )

    supplier.is_active = False
    await db.commit()
