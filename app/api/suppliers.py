"""
Supplier management endpoints.
Aligned with frontend types in /src/lib/api/types.ts
"""

from datetime import datetime, date
from typing import List, Optional, Dict, Any
from uuid import UUID

from fastapi import APIRouter, HTTPException, status, Query
from pydantic import BaseModel, Field
from sqlalchemy import select, func

from sqlalchemy.orm import selectinload

from app.api.deps import DbSession, CurrentUser, CurrentTenant
from app.models.supplier import Supplier
from app.models.contract import Contract
from app.models.accommodation import Accommodation, RoomCategory, AccommodationSeason

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
    # types: array of supplier types (can provide multiple)
    types: Optional[List[SupplierType]] = None  # ['accommodation', 'activity']
    type: Optional[SupplierType] = None  # Legacy single type - converted to types
    status: Optional[SupplierStatus] = 'active'
    country_code: Optional[str] = None
    city: Optional[str] = None
    address: Optional[str] = None
    postal_code: Optional[str] = None
    # Contact commercial
    contact_name: Optional[str] = None
    contact_email: Optional[str] = None
    contact_phone: Optional[str] = None
    # Contact réservation (default pour tous les produits du fournisseur)
    reservation_email: Optional[str] = None
    reservation_phone: Optional[str] = None
    website: Optional[str] = None
    tax_id: Optional[str] = None
    is_vat_registered: Optional[bool] = False  # Assujetti TVA = TVA récupérable
    default_currency: Optional[str] = None
    default_payment_terms_id: Optional[int] = None
    # Billing entity (for logistics)
    billing_entity_name: Optional[str] = None  # Alternative name if different from supplier
    billing_entity_note: Optional[str] = None  # Note for logistics
    # Notes
    internal_notes: Optional[str] = None
    logistics_notes: Optional[str] = None
    quality_notes: Optional[str] = None
    tags: Optional[List[str]] = None


class SupplierUpdate(BaseModel):
    """Update supplier - all fields optional"""
    name: Optional[str] = None
    types: Optional[List[SupplierType]] = None  # Array of types
    type: Optional[SupplierType] = None  # Legacy single type
    status: Optional[SupplierStatus] = None
    country_code: Optional[str] = None
    city: Optional[str] = None
    address: Optional[str] = None
    postal_code: Optional[str] = None
    # Contact commercial
    contact_name: Optional[str] = None
    contact_email: Optional[str] = None
    contact_phone: Optional[str] = None
    # Contact réservation
    reservation_email: Optional[str] = None
    reservation_phone: Optional[str] = None
    website: Optional[str] = None
    tax_id: Optional[str] = None
    is_vat_registered: Optional[bool] = None  # Assujetti TVA = TVA récupérable
    default_currency: Optional[str] = None
    default_payment_terms_id: Optional[int] = None
    # Billing entity (for logistics)
    billing_entity_name: Optional[str] = None
    billing_entity_note: Optional[str] = None
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
    types: List[SupplierType]  # Array of types
    type: SupplierType  # Primary type (first in array) - for backwards compatibility
    status: SupplierStatus = 'active'
    # Location
    country_code: Optional[str] = None
    city: Optional[str] = None
    address: Optional[str] = None
    postal_code: Optional[str] = None
    # Contact commercial
    contact_name: Optional[str] = None
    contact_email: Optional[str] = None
    contact_phone: Optional[str] = None
    # Contact réservation (default pour les produits)
    reservation_email: Optional[str] = None
    reservation_phone: Optional[str] = None
    website: Optional[str] = None
    # Financial
    tax_id: Optional[str] = None
    is_vat_registered: bool = False  # Assujetti TVA = TVA récupérable sur factures
    default_currency: Optional[str] = None
    default_payment_terms_id: Optional[int] = None
    # Billing entity (for logistics)
    billing_entity_name: Optional[str] = None
    billing_entity_note: Optional[str] = None
    # Notes
    internal_notes: Optional[str] = None
    logistics_notes: Optional[str] = None
    quality_notes: Optional[str] = None
    tags: Optional[List[str]] = None
    # Location link
    location_id: Optional[int] = None
    # Contract workflow (user-managed)
    contract_workflow_status: Optional[str] = None  # needs_contract, contract_requested, dynamic_pricing
    # Contract info (calculated from relationships)
    active_contract_id: Optional[int] = None
    active_contract_name: Optional[str] = None
    contract_valid_to: Optional[str] = None
    contract_validity_status: Optional[str] = None  # valid, expiring_soon, expired, no_contract, contract_requested, dynamic_pricing
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

def calculate_contract_status(supplier: Supplier) -> Dict[str, Any]:
    """
    Calculate contract validity status from supplier's contracts and workflow status.

    Returns dict with:
    - active_contract_id
    - active_contract_name
    - contract_valid_to
    - contract_validity_status: valid | expiring_soon | expired | no_contract | contract_requested | dynamic_pricing
    - days_until_contract_expiry
    """
    workflow_status = getattr(supplier, 'contract_workflow_status', 'needs_contract')

    # Dynamic pricing suppliers don't need contracts
    if workflow_status == 'dynamic_pricing':
        return {
            "active_contract_id": None,
            "active_contract_name": None,
            "contract_valid_to": None,
            "contract_validity_status": "dynamic_pricing",
            "days_until_contract_expiry": None,
        }

    # Check if contracts are loaded
    contracts = getattr(supplier, 'contracts', None)
    if contracts is None:
        # Contracts not loaded, fallback to workflow status
        if workflow_status == 'contract_requested':
            return {
                "active_contract_id": None,
                "active_contract_name": None,
                "contract_valid_to": None,
                "contract_validity_status": "contract_requested",
                "days_until_contract_expiry": None,
            }
        return {
            "active_contract_id": None,
            "active_contract_name": None,
            "contract_valid_to": None,
            "contract_validity_status": "no_contract",
            "days_until_contract_expiry": None,
        }

    # Find active contract (status='active' and within date range)
    today = date.today()
    active_contract = None

    for contract in contracts:
        if contract.status == "active" and contract.valid_from and contract.valid_to:
            if contract.valid_from <= today <= contract.valid_to:
                active_contract = contract
                break

    if active_contract:
        # Active contract found - check if expiring soon (30 days)
        days_until_expiry = (active_contract.valid_to - today).days
        validity_status = "expiring_soon" if days_until_expiry <= 30 else "valid"

        return {
            "active_contract_id": active_contract.id,
            "active_contract_name": active_contract.name,
            "contract_valid_to": active_contract.valid_to.isoformat(),
            "contract_validity_status": validity_status,
            "days_until_contract_expiry": days_until_expiry,
        }

    # No active contract - check for expired contracts
    expired_contracts = [
        c for c in contracts
        if c.status == "active" and c.valid_to and c.valid_to < today
    ]

    if expired_contracts:
        # Most recently expired
        latest_expired = max(expired_contracts, key=lambda c: c.valid_to)
        days_since_expiry = (today - latest_expired.valid_to).days

        return {
            "active_contract_id": latest_expired.id,
            "active_contract_name": latest_expired.name,
            "contract_valid_to": latest_expired.valid_to.isoformat(),
            "contract_validity_status": "expired",
            "days_until_contract_expiry": -days_since_expiry,  # Negative for expired
        }

    # No contract - check workflow status
    if workflow_status == 'contract_requested':
        return {
            "active_contract_id": None,
            "active_contract_name": None,
            "contract_valid_to": None,
            "contract_validity_status": "contract_requested",
            "days_until_contract_expiry": None,
        }

    return {
        "active_contract_id": None,
        "active_contract_name": None,
        "contract_valid_to": None,
        "contract_validity_status": "no_contract",
        "days_until_contract_expiry": None,
    }


def supplier_to_response(supplier: Supplier) -> SupplierResponse:
    """Convert SQLAlchemy model to Pydantic response with proper type conversions"""
    # Get types array, fallback to ['accommodation'] if not set
    types = supplier.types if supplier.types else ['accommodation']
    primary_type = types[0] if types else 'accommodation'

    # Calculate contract status from contracts relationship
    contract_info = calculate_contract_status(supplier)

    return SupplierResponse(
        id=supplier.id,
        tenant_id=str(supplier.tenant_id),  # UUID to string
        name=supplier.name,
        types=types,
        type=primary_type,  # Primary type for backwards compatibility
        status='active' if supplier.is_active else 'inactive',
        country_code=supplier.country_code,
        city=supplier.city,
        address=supplier.address,
        postal_code=getattr(supplier, 'postal_code', None),
        contact_name=supplier.contact_name,
        contact_email=supplier.contact_email,
        contact_phone=supplier.contact_phone,
        # Contact réservation
        reservation_email=supplier.reservation_email,
        reservation_phone=supplier.reservation_phone,
        website=getattr(supplier, 'website', None),
        tax_id=supplier.tax_id,
        is_vat_registered=getattr(supplier, 'is_vat_registered', False),
        default_currency=supplier.default_currency,
        default_payment_terms_id=getattr(supplier, 'default_payment_terms_id', None),
        # Billing entity
        billing_entity_name=getattr(supplier, 'billing_entity_name', None),
        billing_entity_note=getattr(supplier, 'billing_entity_note', None),
        internal_notes=getattr(supplier, 'internal_notes', None),
        logistics_notes=getattr(supplier, 'logistics_notes', None),
        quality_notes=getattr(supplier, 'quality_notes', None),
        tags=getattr(supplier, 'tags', None),
        # Location link
        location_id=getattr(supplier, 'location_id', None),
        # Contract workflow
        contract_workflow_status=getattr(supplier, 'contract_workflow_status', 'needs_contract'),
        # Contract info (calculated)
        **contract_info,
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
    # Location filters
    country_code: Optional[str] = Query(None, description="Filter by country code (e.g., TH, MA)"),
    city: Optional[str] = Query(None, description="Filter by city name (partial match)"),
    location_id: Optional[int] = Query(None, description="Filter by location ID"),
    # Contract status filter
    contract_status: Optional[str] = Query(
        None,
        description="Filter by contract status: valid, expiring_soon, expired, no_contract, contract_requested, dynamic_pricing"
    ),
):
    """
    List suppliers for the current tenant.
    Supports filtering by type, status, search, location, and contract status.
    """
    # Base query with eager loading of contracts for status calculation
    query = (
        select(Supplier)
        .where(Supplier.tenant_id == tenant.id)
        .options(selectinload(Supplier.contracts))
    )

    # Filters - type filter (check if type is in the types array)
    if type:
        # Use PostgreSQL ANY operator to check if type is in the array
        query = query.where(Supplier.types.any(type))

    # Status filter (maps to is_active)
    if status == 'active':
        query = query.where(Supplier.is_active == True)
    elif status == 'inactive':
        query = query.where(Supplier.is_active == False)
    elif is_active is not None:
        query = query.where(Supplier.is_active == is_active)

    # Search by name
    if search:
        query = query.where(Supplier.name.ilike(f"%{search}%"))

    # Location filters
    if country_code:
        query = query.where(Supplier.country_code == country_code.upper())
    if city:
        query = query.where(Supplier.city.ilike(f"%{city}%"))
    if location_id:
        query = query.where(Supplier.location_id == location_id)

    # Execute query (we need all results for contract_status filter)
    query = query.order_by(Supplier.name)
    result = await db.execute(query)
    all_suppliers = result.scalars().all()

    # Post-filter by contract status (calculated field)
    if contract_status:
        all_suppliers = [
            s for s in all_suppliers
            if calculate_contract_status(s)["contract_validity_status"] == contract_status
        ]

    # Calculate total after contract_status filter
    total = len(all_suppliers)

    # Apply pagination manually
    start = (page - 1) * page_size
    end = start + page_size
    suppliers = all_suppliers[start:end]

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
    print(f"[create_supplier] Received data: {data.model_dump()}")
    print(f"[create_supplier] Tenant: {tenant.id}")

    try:
        # Build types array
        types = data.types if data.types else ([data.type] if data.type else ['accommodation'])
        print(f"[create_supplier] Types: {types}")

        # Build supplier data
        supplier = Supplier(
            tenant_id=tenant.id,
            name=data.name,
            types=types,
            contact_name=data.contact_name,
            contact_email=data.contact_email,
            contact_phone=data.contact_phone,
            reservation_email=data.reservation_email,
            reservation_phone=data.reservation_phone,
            country_code=data.country_code,
            city=data.city,
            address=data.address,
            website=data.website,
            tax_id=data.tax_id,
            is_vat_registered=data.is_vat_registered if data.is_vat_registered is not None else False,
            default_currency=data.default_currency,
            default_payment_terms_id=data.default_payment_terms_id,
            billing_entity_name=data.billing_entity_name,
            billing_entity_note=data.billing_entity_note,
            is_active=data.status != 'inactive' if data.status else True,
        )
        print(f"[create_supplier] Supplier object created: {supplier}")
        db.add(supplier)
        print("[create_supplier] Added to session")
        await db.commit()
        print(f"[create_supplier] Committed, id={supplier.id}")

        # Reload supplier with contracts relationship for proper response
        result = await db.execute(
            select(Supplier)
            .where(Supplier.id == supplier.id)
            .options(selectinload(Supplier.contracts))
        )
        supplier = result.scalar_one()
        print("[create_supplier] Reloaded with contracts")

        return supplier_to_response(supplier)
    except Exception as e:
        print(f"[create_supplier] ERROR: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erreur lors de la création: {str(e)}",
        )


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
        select(Supplier)
        .where(
            Supplier.id == supplier_id,
            Supplier.tenant_id == tenant.id,
        )
        .options(selectinload(Supplier.contracts))
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
    print(f"[update_supplier] Received data: {update_data}")
    print(f"[update_supplier] Supplier before: name={supplier.name}, city={supplier.city}")

    # Handle status -> is_active mapping
    if 'status' in update_data:
        status_val = update_data.pop('status')
        update_data['is_active'] = status_val != 'inactive'

    # Handle types: if 'type' is provided (legacy), convert to types array
    if 'type' in update_data and 'types' not in update_data:
        update_data['types'] = [update_data.pop('type')]
    elif 'type' in update_data:
        update_data.pop('type')  # Remove legacy field if types is provided

    # Filter to only fields that exist on the model
    model_fields = {'name', 'types', 'contact_name', 'contact_email', 'contact_phone',
                    'reservation_email', 'reservation_phone',
                    'country_code', 'city', 'address', 'website', 'tax_id', 'is_vat_registered',
                    'default_currency', 'default_payment_terms_id', 'is_active',
                    'location_id', 'contract_workflow_status',
                    'billing_entity_name', 'billing_entity_note'}

    applied_fields = []
    for field, value in update_data.items():
        if field in model_fields:
            setattr(supplier, field, value)
            applied_fields.append(f"{field}={value}")

    print(f"[update_supplier] Applied fields: {applied_fields}")
    await db.commit()
    print(f"[update_supplier] Supplier after commit: name={supplier.name}, city={supplier.city}")

    # Reload supplier with contracts relationship for proper response
    from sqlalchemy.orm import selectinload
    result = await db.execute(
        select(Supplier)
        .where(Supplier.id == supplier_id)
        .options(selectinload(Supplier.contracts))
    )
    supplier = result.scalar_one()

    return supplier_to_response(supplier)


@router.delete("/{supplier_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_supplier(
    supplier_id: int,
    db: DbSession,
    tenant: CurrentTenant,
    user: CurrentUser,
    permanent: bool = Query(False, description="Si true, supprime définitivement au lieu de désactiver"),
):
    """
    Delete a supplier.
    - Par défaut: soft delete (is_active=False)
    - Avec permanent=true: suppression définitive
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

    if permanent:
        # Suppression définitive
        await db.delete(supplier)
    else:
        # Soft delete
        supplier.is_active = False

    await db.commit()


@router.get("/{supplier_id}/accommodation")
async def get_supplier_accommodation(
    supplier_id: int,
    db: DbSession,
    tenant: CurrentTenant,
):
    """
    Get the accommodation for a supplier (if exists).
    Returns the accommodation with room categories and seasons.
    """
    # Verify supplier exists
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

    # Get accommodation with related data (first one if multiple exist)
    result = await db.execute(
        select(Accommodation)
        .where(
            Accommodation.supplier_id == supplier_id,
            Accommodation.tenant_id == tenant.id,
        )
        .options(
            selectinload(Accommodation.room_categories),
            selectinload(Accommodation.seasons),
        )
        .order_by(Accommodation.id)
        .limit(1)
    )
    accommodation = result.scalar_one_or_none()

    if not accommodation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No accommodation found for this supplier",
        )

    # Convert to response
    return {
        "id": accommodation.id,
        "tenant_id": str(accommodation.tenant_id),
        "supplier_id": accommodation.supplier_id,
        "name": accommodation.name,
        "description": accommodation.description,
        "star_rating": accommodation.star_rating,
        "internal_priority": accommodation.internal_priority,
        "internal_notes": accommodation.internal_notes,
        # Location (lien vers table locations pour filtrage)
        "location_id": getattr(accommodation, 'location_id', None),
        # Adresse Google Maps
        "address": accommodation.address,
        "city": accommodation.city,
        "country_code": accommodation.country_code,
        "lat": float(accommodation.lat) if accommodation.lat else None,
        "lng": float(accommodation.lng) if accommodation.lng else None,
        "google_place_id": accommodation.google_place_id,
        "check_in_time": accommodation.check_in_time,
        "check_out_time": accommodation.check_out_time,
        "amenities": accommodation.amenities or [],
        "reservation_email": accommodation.reservation_email,
        "reservation_phone": accommodation.reservation_phone,
        "website_url": accommodation.website_url,
        "external_provider": accommodation.external_provider,
        "external_id": accommodation.external_id,
        # Lien futur vers article de contenu
        "content_id": getattr(accommodation, 'content_id', None),
        # Payment terms override (optional - if NULL, use supplier.default_payment_terms)
        "payment_terms_id": getattr(accommodation, 'payment_terms_id', None),
        "status": accommodation.status,
        "is_active": accommodation.is_active,
        "created_at": accommodation.created_at.isoformat() if accommodation.created_at else None,
        "updated_at": accommodation.updated_at.isoformat() if accommodation.updated_at else None,
        "room_categories": [
            {
                "id": cat.id,
                "accommodation_id": cat.accommodation_id,
                "name": cat.name,
                "code": cat.code,
                "description": cat.description,
                "min_occupancy": cat.min_occupancy,
                "max_occupancy": cat.max_occupancy,
                "max_adults": cat.max_adults,
                "max_children": cat.max_children,
                "available_bed_types": cat.available_bed_types or ["DBL"],
                "size_sqm": cat.size_sqm,
                "amenities": cat.amenities or [],
                "is_active": cat.is_active,
                "sort_order": cat.sort_order,
            }
            for cat in (accommodation.room_categories or [])
        ],
        "seasons": [
            {
                "id": s.id,
                "accommodation_id": s.accommodation_id,
                "name": s.name,
                "code": s.code,
                "season_type": s.season_type,
                "start_date": s.start_date,
                "end_date": s.end_date,
                "weekdays": s.weekdays,
                "year": s.year,
                "priority": s.priority,
                "is_active": s.is_active,
                "created_at": s.created_at.isoformat() if hasattr(s, 'created_at') and s.created_at else None,
                "updated_at": s.updated_at.isoformat() if hasattr(s, 'updated_at') and s.updated_at else None,
            }
            for s in (accommodation.seasons or [])
        ],
        "created_at": accommodation.created_at.isoformat() if accommodation.created_at else None,
        "updated_at": accommodation.updated_at.isoformat() if accommodation.updated_at else None,
    }


@router.get("/{supplier_id}/payment-terms")
async def get_supplier_payment_terms(
    supplier_id: int,
    db: DbSession,
    tenant: CurrentTenant,
):
    """
    Get payment terms for a supplier.
    Returns empty list if no payment terms are configured.
    """
    # Verify supplier exists
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

    # TODO: Implement actual payment terms storage
    # For now, return empty list as payment terms are not yet implemented
    return []


@router.post("/{supplier_id}/payment-terms")
async def create_supplier_payment_terms(
    supplier_id: int,
    data: dict,
    db: DbSession,
    tenant: CurrentTenant,
    user: CurrentUser,
):
    """
    Create payment terms for a supplier.
    """
    # Verify supplier exists
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

    # TODO: Implement actual payment terms storage
    # For now, just return the data as if it was saved
    return data


# ============================================================================
# Contract Workflow Endpoints
# ============================================================================

class UpdateContractWorkflowDTO(BaseModel):
    """Update contract workflow status"""
    contract_workflow_status: str  # needs_contract, contract_requested, dynamic_pricing


@router.patch("/{supplier_id}/contract-workflow", response_model=SupplierResponse)
async def update_contract_workflow(
    supplier_id: int,
    data: UpdateContractWorkflowDTO,
    db: DbSession,
    tenant: CurrentTenant,
    user: CurrentUser,
):
    """
    Update supplier's contract workflow status.

    Workflow states:
    - needs_contract: Default, supplier needs a contract
    - contract_requested: Logistics has requested contract from supplier
    - dynamic_pricing: No contract needed, supplier uses dynamic pricing only
    """
    # Validate status
    valid_statuses = {'needs_contract', 'contract_requested', 'dynamic_pricing'}
    if data.contract_workflow_status not in valid_statuses:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid workflow status. Must be one of: {', '.join(valid_statuses)}",
        )

    # Fetch supplier with contracts
    result = await db.execute(
        select(Supplier)
        .where(
            Supplier.id == supplier_id,
            Supplier.tenant_id == tenant.id,
        )
        .options(selectinload(Supplier.contracts))
    )
    supplier = result.scalar_one_or_none()

    if not supplier:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Supplier not found",
        )

    # Update workflow status
    supplier.contract_workflow_status = data.contract_workflow_status

    await db.commit()
    await db.refresh(supplier)

    # Re-fetch with contracts for response
    result = await db.execute(
        select(Supplier)
        .where(Supplier.id == supplier_id)
        .options(selectinload(Supplier.contracts))
    )
    supplier = result.scalar_one()

    return supplier_to_response(supplier)
