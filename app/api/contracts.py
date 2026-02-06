"""
Contract management endpoints.
"""

from datetime import date
from typing import List, Optional

from fastapi import APIRouter, HTTPException, status, Query
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload

from app.api.deps import DbSession, CurrentUser, CurrentTenant
from app.models.contract import Contract, ContractRate
from app.models.supplier import Supplier

router = APIRouter()


# Schemas
class ContractRateCreate(BaseModel):
    service_name: str
    service_code: Optional[str] = None
    pax_category: Optional[str] = None
    currency: str = "EUR"
    base_price: float
    season_name: Optional[str] = None
    season_start_mmdd: Optional[str] = None
    season_end_mmdd: Optional[str] = None
    day_of_week_mask: int = 127
    min_pax: Optional[int] = None
    max_pax: Optional[int] = None


class ContractRateResponse(BaseModel):
    id: int
    contract_id: int
    service_name: str
    service_code: Optional[str]
    pax_category: Optional[str]
    currency: str
    base_price: float
    season_name: Optional[str]
    season_start_mmdd: Optional[str]
    season_end_mmdd: Optional[str]
    day_of_week_mask: int
    min_pax: Optional[int]
    max_pax: Optional[int]

    class Config:
        from_attributes = True


class ContractCreate(BaseModel):
    supplier_id: int
    name: str
    reference: Optional[str] = None
    valid_from: date
    valid_to: date
    payment_terms_json: Optional[dict] = None
    cancellation_terms_json: Optional[dict] = None
    rates: Optional[List[ContractRateCreate]] = None


class ContractUpdate(BaseModel):
    name: Optional[str] = None
    reference: Optional[str] = None
    valid_from: Optional[date] = None
    valid_to: Optional[date] = None
    payment_terms_json: Optional[dict] = None
    cancellation_terms_json: Optional[dict] = None
    status: Optional[str] = None


class ContractResponse(BaseModel):
    id: int
    tenant_id: int
    supplier_id: int
    name: str
    reference: Optional[str]
    valid_from: date
    valid_to: date
    payment_terms_json: Optional[dict]
    cancellation_terms_json: Optional[dict]
    status: str
    rates: List[ContractRateResponse] = []

    class Config:
        from_attributes = True


class ContractListResponse(BaseModel):
    items: List[ContractResponse]
    total: int
    page: int
    page_size: int


# Endpoints
@router.get("", response_model=ContractListResponse)
async def list_contracts(
    db: DbSession,
    tenant: CurrentTenant,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    supplier_id: Optional[int] = None,
    status: Optional[str] = None,
    expiring_within_days: Optional[int] = None,
):
    """
    List contracts for the current tenant.
    """
    # Base query with rates
    query = (
        select(Contract)
        .where(Contract.tenant_id == tenant.id)
        .options(selectinload(Contract.rates))
    )

    # Filters
    if supplier_id:
        query = query.where(Contract.supplier_id == supplier_id)
    if status:
        query = query.where(Contract.status == status)
    if expiring_within_days:
        expiry_date = date.today() + timedelta(days=expiring_within_days)
        query = query.where(Contract.valid_to <= expiry_date)

    # Count
    count_query = select(func.count()).select_from(
        select(Contract).where(Contract.tenant_id == tenant.id).subquery()
    )
    total = (await db.execute(count_query)).scalar()

    # Pagination
    query = query.offset((page - 1) * page_size).limit(page_size)
    query = query.order_by(Contract.valid_to)

    result = await db.execute(query)
    contracts = result.scalars().unique().all()

    return ContractListResponse(
        items=[ContractResponse.model_validate(c) for c in contracts],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post("", response_model=ContractResponse, status_code=status.HTTP_201_CREATED)
async def create_contract(
    data: ContractCreate,
    db: DbSession,
    tenant: CurrentTenant,
    user: CurrentUser,
):
    """
    Create a new contract with optional rates.
    """
    # Verify supplier belongs to tenant
    result = await db.execute(
        select(Supplier).where(
            Supplier.id == data.supplier_id,
            Supplier.tenant_id == tenant.id,
        )
    )
    if not result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Supplier not found",
        )

    # Create contract
    contract_data = data.model_dump(exclude={"rates"})
    contract = Contract(
        tenant_id=tenant.id,
        status="draft",
        **contract_data,
    )
    db.add(contract)
    await db.flush()

    # Create rates
    if data.rates:
        for rate_data in data.rates:
            rate = ContractRate(
                tenant_id=tenant.id,
                contract_id=contract.id,
                **rate_data.model_dump(),
            )
            db.add(rate)

    await db.commit()

    # Reload with rates
    result = await db.execute(
        select(Contract)
        .where(Contract.id == contract.id)
        .options(selectinload(Contract.rates))
    )
    contract = result.scalar_one()

    return ContractResponse.model_validate(contract)


@router.get("/{contract_id}", response_model=ContractResponse)
async def get_contract(
    contract_id: int,
    db: DbSession,
    tenant: CurrentTenant,
):
    """
    Get a specific contract with its rates.
    """
    result = await db.execute(
        select(Contract)
        .where(Contract.id == contract_id, Contract.tenant_id == tenant.id)
        .options(selectinload(Contract.rates))
    )
    contract = result.scalar_one_or_none()

    if not contract:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Contract not found",
        )

    return ContractResponse.model_validate(contract)


@router.patch("/{contract_id}", response_model=ContractResponse)
async def update_contract(
    contract_id: int,
    data: ContractUpdate,
    db: DbSession,
    tenant: CurrentTenant,
    user: CurrentUser,
):
    """
    Update a contract.
    """
    result = await db.execute(
        select(Contract)
        .where(Contract.id == contract_id, Contract.tenant_id == tenant.id)
        .options(selectinload(Contract.rates))
    )
    contract = result.scalar_one_or_none()

    if not contract:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Contract not found",
        )

    # Update fields
    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(contract, field, value)

    await db.commit()
    await db.refresh(contract)

    return ContractResponse.model_validate(contract)


@router.post("/{contract_id}/activate", response_model=ContractResponse)
async def activate_contract(
    contract_id: int,
    db: DbSession,
    tenant: CurrentTenant,
    user: CurrentUser,
):
    """
    Activate a contract (change status to 'active').
    """
    result = await db.execute(
        select(Contract)
        .where(Contract.id == contract_id, Contract.tenant_id == tenant.id)
        .options(selectinload(Contract.rates))
    )
    contract = result.scalar_one_or_none()

    if not contract:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Contract not found",
        )

    contract.status = "active"
    contract.human_validated_at = datetime.utcnow()
    contract.validated_by_id = user.id

    await db.commit()
    await db.refresh(contract)

    return ContractResponse.model_validate(contract)


# Import needed
from datetime import timedelta, datetime
