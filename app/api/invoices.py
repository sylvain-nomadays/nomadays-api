"""
Invoice management endpoints.
Handles CRUD, PDF generation, workflow advancement, and payment tracking.
Supports: DEV (Devis), PRO (Proforma), FA (Facture), AV (Avoir/Credit Note).
"""

import json
import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Optional, List

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload

from app.api.deps import CurrentUser, CurrentTenant, DbSession, TenantId
from app.models.invoice import Invoice, InvoiceLine, InvoiceVatDetail, InvoicePaymentLink
from app.services.invoice_service import InvoiceService
from app.services.invoice_pdf import render_invoice_html, generate_pdf_bytes, generate_and_store_pdf

router = APIRouter()


# ============================================================================
# Schemas
# ============================================================================

class InvoiceLineCreate(BaseModel):
    description: str
    details: Optional[str] = None
    quantity: Decimal = Decimal("1")
    unit_price_ttc: Decimal
    line_type: str = "service"


class InvoiceLineUpdate(BaseModel):
    description: Optional[str] = None
    details: Optional[str] = None
    quantity: Optional[Decimal] = None
    unit_price_ttc: Optional[Decimal] = None
    line_type: Optional[str] = None


class InvoiceCreate(BaseModel):
    """Create an invoice from a dossier."""
    dossier_id: uuid.UUID
    type: str  # DEV, PRO, FA, AV
    total_ttc: Optional[Decimal] = None
    cost_ht: Optional[Decimal] = None  # For margin VAT calculation
    deposit_pct: Optional[Decimal] = None
    notes: Optional[str] = None
    client_notes: Optional[str] = None
    lines: Optional[List[InvoiceLineCreate]] = None
    # Dates d'échéance (optionnel — sinon calculées automatiquement)
    deposit_due_date: Optional[date] = None  # Date échéance acompte
    balance_due_date: Optional[date] = None  # Date échéance solde
    # Client override (when invoicing a specific participant instead of lead)
    client_name: Optional[str] = None
    client_email: Optional[str] = None
    client_phone: Optional[str] = None
    client_address: Optional[str] = None
    # Réforme e-facture 2026
    client_siren: Optional[str] = None
    delivery_address_line1: Optional[str] = None
    delivery_address_city: Optional[str] = None
    delivery_address_postal_code: Optional[str] = None
    delivery_address_country: Optional[str] = None
    operation_category: Optional[str] = "PS"  # LB, PS, LBPS
    # Pax / insured persons (for Chapka insurance)
    pax_count: Optional[int] = None  # Number of insured persons
    pax_names: Optional[List[str]] = None  # Participant names (when known)


class InvoiceUpdate(BaseModel):
    """Update draft invoice fields."""
    client_name: Optional[str] = None
    client_email: Optional[str] = None
    client_phone: Optional[str] = None
    client_company: Optional[str] = None
    client_address: Optional[str] = None
    client_siret: Optional[str] = None
    due_date: Optional[date] = None
    deposit_pct: Optional[Decimal] = None
    notes: Optional[str] = None
    client_notes: Optional[str] = None
    # Réforme e-facture 2026
    client_siren: Optional[str] = None
    delivery_address_line1: Optional[str] = None
    delivery_address_city: Optional[str] = None
    delivery_address_postal_code: Optional[str] = None
    delivery_address_country: Optional[str] = None
    operation_category: Optional[str] = None
    # Pax / insured persons (for Chapka insurance)
    pax_count: Optional[int] = None
    pax_names: Optional[List[str]] = None


class MarkPaidRequest(BaseModel):
    payment_method: Optional[str] = None
    payment_ref: Optional[str] = None
    paid_amount: Optional[Decimal] = None


class CancelRequest(BaseModel):
    reason: str
    create_credit_note: bool = False


class SendRequest(BaseModel):
    to_email: str


class InvoiceLineResponse(BaseModel):
    id: int
    sort_order: int
    description: str
    details: Optional[str] = None
    quantity: Decimal
    unit_price_ttc: Decimal
    total_ttc: Decimal
    line_type: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class PaymentLinkResponse(BaseModel):
    id: int
    payment_type: str
    amount: Decimal
    due_date: date
    status: str
    paid_at: Optional[datetime] = None
    paid_amount: Optional[Decimal] = None
    payment_method: Optional[str] = None
    payment_ref: Optional[str] = None
    payment_url: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class InvoiceSummaryResponse(BaseModel):
    id: int
    type: str
    number: str
    status: str
    client_name: Optional[str] = None
    client_company: Optional[str] = None
    issue_date: date
    due_date: Optional[date] = None
    total_ttc: Decimal
    deposit_amount: Decimal
    balance_amount: Decimal
    currency: str
    vat_regime: Optional[str] = None
    pdf_url: Optional[str] = None
    parent_invoice_id: Optional[int] = None
    dossier_id: Optional[uuid.UUID] = None
    pax_count: Optional[int] = None
    share_token: Optional[uuid.UUID] = None
    created_at: datetime
    # Extra fields for standalone invoices page
    dossier_reference: Optional[str] = None
    created_by_name: Optional[str] = None
    travel_start_date: Optional[date] = None
    travel_end_date: Optional[date] = None
    # Payment reminder
    reminder_enabled: bool = True
    reminder_date: Optional[date] = None
    reminder_sent_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class InvoiceDetailResponse(BaseModel):
    id: int
    type: str
    number: str
    year: int
    sequence: int
    status: str
    # Client
    client_type: Optional[str] = None
    client_name: Optional[str] = None
    client_email: Optional[str] = None
    client_phone: Optional[str] = None
    client_company: Optional[str] = None
    client_siret: Optional[str] = None
    client_vat_number: Optional[str] = None
    client_address: Optional[str] = None
    client_siren: Optional[str] = None
    # Delivery address (réforme 2026)
    delivery_address_line1: Optional[str] = None
    delivery_address_city: Optional[str] = None
    delivery_address_postal_code: Optional[str] = None
    delivery_address_country: Optional[str] = None
    # References
    dossier_id: Optional[uuid.UUID] = None
    trip_id: Optional[int] = None
    cotation_id: Optional[int] = None
    parent_invoice_id: Optional[int] = None
    # Dates
    issue_date: date
    due_date: Optional[date] = None
    travel_start_date: Optional[date] = None
    travel_end_date: Optional[date] = None
    # Amounts
    total_ht: Decimal
    total_ttc: Decimal
    deposit_amount: Decimal
    deposit_pct: Decimal
    balance_amount: Decimal
    currency: str
    # VAT
    vat_regime: Optional[str] = None
    vat_rate: Decimal
    vat_amount: Decimal
    vat_legal_mention: Optional[str] = None
    # Réforme e-facture 2026
    operation_category: Optional[str] = None
    vat_on_debits: Optional[bool] = None
    electronic_format: Optional[str] = None
    pa_transmission_status: Optional[str] = None
    pa_transmission_date: Optional[datetime] = None
    pa_transmission_id: Optional[str] = None
    # Payment
    payment_method: Optional[str] = None
    payment_ref: Optional[str] = None
    paid_at: Optional[datetime] = None
    paid_amount: Optional[Decimal] = None
    # PDF
    pdf_url: Optional[str] = None
    pdf_generated_at: Optional[datetime] = None
    # Cancellation
    cancelled_at: Optional[datetime] = None
    cancellation_reason: Optional[str] = None
    # Pax / insured persons
    pax_count: Optional[int] = None
    pax_names: Optional[str] = None  # JSON string of participant names
    # Meta
    notes: Optional[str] = None
    client_notes: Optional[str] = None
    created_by_id: Optional[uuid.UUID] = None
    sent_at: Optional[datetime] = None
    sent_to_email: Optional[str] = None
    # Sharing
    share_token: Optional[uuid.UUID] = None
    share_token_created_at: Optional[datetime] = None
    shared_link_viewed_at: Optional[datetime] = None
    # Payment reminder
    reminder_enabled: bool = True
    reminder_date: Optional[date] = None
    reminder_sent_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
    # Nested
    lines: List[InvoiceLineResponse] = []
    payment_links: List[PaymentLinkResponse] = []

    model_config = ConfigDict(from_attributes=True)


class InvoiceListResponse(BaseModel):
    items: List[InvoiceSummaryResponse]
    total: int
    page: int
    page_size: int


# ============================================================================
# Helpers
# ============================================================================

# Types commerciaux (non définitifs) modifiables après envoi
EDITABLE_TYPES = {"DEV", "PRO"}
EDITABLE_STATUSES = {"draft", "sent"}


def _assert_invoice_editable(invoice: Invoice) -> None:
    """
    Vérifie qu'une facture peut être modifiée.

    Règles :
    - DEV et PRO sont des documents commerciaux : éditables en draft + sent
    - FA et AV sont des documents définitifs (loi française) : éditables en draft uniquement
    - paid et cancelled ne sont jamais modifiables
    """
    if invoice.status in ("paid", "cancelled"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Impossible de modifier un document {invoice.status}.",
        )
    if invoice.type in EDITABLE_TYPES:
        if invoice.status not in EDITABLE_STATUSES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Impossible de modifier ce {invoice.type} (statut: {invoice.status}).",
            )
    else:
        # FA, AV : seul le brouillon est modifiable
        if invoice.status != "draft":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Les {invoice.type} ne peuvent être modifiés qu'en brouillon.",
            )


# ============================================================================
# Endpoints
# ============================================================================


class SellerResponse(BaseModel):
    id: str
    name: str


@router.get("/sellers", response_model=List[SellerResponse])
async def list_invoice_sellers(
    db: DbSession,
    tenant: CurrentTenant,
):
    """List distinct users who have created invoices for this tenant."""
    from app.models.user import User

    query = (
        select(User.id, User.first_name, User.last_name)
        .join(Invoice, Invoice.created_by_id == User.id)
        .where(Invoice.tenant_id == tenant.id)
        .distinct()
        .order_by(User.first_name, User.last_name)
    )
    result = await db.execute(query)
    rows = result.all()

    sellers = []
    for row in rows:
        name_parts = [row.first_name, row.last_name]
        name = " ".join(p for p in name_parts if p) or "Utilisateur"
        sellers.append(SellerResponse(id=str(row.id), name=name))

    return sellers


@router.get("", response_model=InvoiceListResponse)
async def list_invoices(
    db: DbSession,
    tenant: CurrentTenant,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    dossier_id: Optional[uuid.UUID] = None,
    type: Optional[str] = None,
    status_filter: Optional[str] = Query(None, alias="status"),
    search: Optional[str] = None,
    # New filters for standalone invoices page
    created_by_id: Optional[uuid.UUID] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    due_date_from: Optional[date] = None,
    due_date_to: Optional[date] = None,
    overdue: Optional[bool] = None,
):
    """List invoices with pagination and filters."""
    from app.models.dossier import Dossier
    from app.models.user import User

    query = (
        select(Invoice)
        .outerjoin(Dossier, Invoice.dossier_id == Dossier.id)
        .outerjoin(User, Invoice.created_by_id == User.id)
        .where(Invoice.tenant_id == tenant.id)
        .order_by(Invoice.created_at.desc())
    )

    count_query = (
        select(func.count())
        .select_from(Invoice)
        .outerjoin(Dossier, Invoice.dossier_id == Dossier.id)
        .where(Invoice.tenant_id == tenant.id)
    )

    if dossier_id:
        query = query.where(Invoice.dossier_id == dossier_id)
        count_query = count_query.where(Invoice.dossier_id == dossier_id)

    if type:
        query = query.where(Invoice.type == type)
        count_query = count_query.where(Invoice.type == type)

    if status_filter:
        query = query.where(Invoice.status == status_filter)
        count_query = count_query.where(Invoice.status == status_filter)

    if search:
        search_term = f"%{search}%"
        search_filter = (
            (Invoice.number.ilike(search_term))
            | (Invoice.client_name.ilike(search_term))
            | (Invoice.client_company.ilike(search_term))
            | (Dossier.reference.ilike(search_term))
        )
        query = query.where(search_filter)
        count_query = count_query.where(search_filter)

    if created_by_id:
        query = query.where(Invoice.created_by_id == created_by_id)
        count_query = count_query.where(Invoice.created_by_id == created_by_id)

    if date_from:
        query = query.where(Invoice.issue_date >= date_from)
        count_query = count_query.where(Invoice.issue_date >= date_from)

    if date_to:
        query = query.where(Invoice.issue_date <= date_to)
        count_query = count_query.where(Invoice.issue_date <= date_to)

    if due_date_from:
        query = query.where(Invoice.due_date >= due_date_from)
        count_query = count_query.where(Invoice.due_date >= due_date_from)

    if due_date_to:
        query = query.where(Invoice.due_date <= due_date_to)
        count_query = count_query.where(Invoice.due_date <= due_date_to)

    if overdue:
        today = date.today()
        overdue_filter = (
            Invoice.due_date.isnot(None)
            & (Invoice.due_date < today)
            & Invoice.status.in_(["draft", "sent"])
        )
        query = query.where(overdue_filter)
        count_query = count_query.where(overdue_filter)

    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    # Load with joined data for extra fields
    query = query.add_columns(Dossier.reference.label("dossier_reference"), User.first_name, User.last_name)
    query = query.offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(query)
    rows = result.all()

    items = []
    for row in rows:
        inv = row[0]  # Invoice object
        dossier_ref = row[1]  # Dossier.reference
        first_name = row[2]  # User.first_name
        last_name = row[3]  # User.last_name

        item = InvoiceSummaryResponse.model_validate(inv)
        item.dossier_reference = dossier_ref
        # Build user display name
        name_parts = [first_name, last_name]
        item.created_by_name = " ".join(p for p in name_parts if p) or None
        item.travel_start_date = inv.travel_start_date
        item.travel_end_date = inv.travel_end_date
        items.append(item)

    return InvoiceListResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post("", response_model=InvoiceDetailResponse, status_code=status.HTTP_201_CREATED)
async def create_invoice(
    data: InvoiceCreate,
    db: DbSession,
    user: CurrentUser,
    tenant: CurrentTenant,
):
    """Create a new invoice from a dossier."""
    if data.type not in ("DEV", "PRO", "AV"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Les factures (FA) sont générées automatiquement au paiement de la proforma. "
                "Types autorisés : DEV, PRO, AV."
            )
            if data.type == "FA"
            else f"Type de document invalide : {data.type}. Types autorisés : DEV, PRO, AV.",
        )

    lines_data = None
    if data.lines:
        lines_data = [
            {
                "description": line.description,
                "details": line.details,
                "quantity": line.quantity,
                "unit_price_ttc": line.unit_price_ttc,
                "line_type": line.line_type,
            }
            for line in data.lines
        ]

    # Client override (when invoicing a specific participant)
    reform_fields = {}
    if data.client_name is not None:
        reform_fields["client_name"] = data.client_name
    if data.client_email is not None:
        reform_fields["client_email"] = data.client_email
    if data.client_phone is not None:
        reform_fields["client_phone"] = data.client_phone
    if data.client_address is not None:
        reform_fields["client_address"] = data.client_address

    # Réforme 2026 extra fields
    if data.client_siren is not None:
        reform_fields["client_siren"] = data.client_siren
    if data.delivery_address_line1 is not None:
        reform_fields["delivery_address_line1"] = data.delivery_address_line1
    if data.delivery_address_city is not None:
        reform_fields["delivery_address_city"] = data.delivery_address_city
    if data.delivery_address_postal_code is not None:
        reform_fields["delivery_address_postal_code"] = data.delivery_address_postal_code
    if data.delivery_address_country is not None:
        reform_fields["delivery_address_country"] = data.delivery_address_country
    if data.operation_category is not None:
        reform_fields["operation_category"] = data.operation_category

    # Pax / insured persons
    if data.pax_count is not None:
        reform_fields["pax_count"] = data.pax_count
    if data.pax_names is not None:
        reform_fields["pax_names"] = json.dumps(data.pax_names, ensure_ascii=False)

    try:
        invoice = await InvoiceService.create_from_dossier(
            db=db,
            tenant_id=tenant.id,
            user_id=user.id,
            dossier_id=data.dossier_id,
            invoice_type=data.type,
            lines_data=lines_data,
            total_ttc=data.total_ttc,
            cost_ht=data.cost_ht,
            deposit_pct=data.deposit_pct,
            notes=data.notes,
            client_notes=data.client_notes,
            deposit_due_date=data.deposit_due_date,
            balance_due_date=data.balance_due_date,
            **reform_fields,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    # Reload with relationships
    result = await db.execute(
        select(Invoice)
        .where(Invoice.id == invoice.id)
        .options(
            selectinload(Invoice.lines),
            selectinload(Invoice.payment_links),
        )
    )
    invoice = result.scalar_one()

    return InvoiceDetailResponse.model_validate(invoice)


@router.get("/{invoice_id}", response_model=InvoiceDetailResponse)
async def get_invoice(
    invoice_id: int,
    db: DbSession,
    tenant: CurrentTenant,
):
    """Get full invoice details with lines and payment links."""
    result = await db.execute(
        select(Invoice)
        .where(Invoice.id == invoice_id, Invoice.tenant_id == tenant.id)
        .options(
            selectinload(Invoice.lines),
            selectinload(Invoice.payment_links),
        )
    )
    invoice = result.scalar_one_or_none()
    if not invoice:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invoice not found")

    return InvoiceDetailResponse.model_validate(invoice)


@router.patch("/{invoice_id}", response_model=InvoiceDetailResponse)
async def update_invoice(
    invoice_id: int,
    data: InvoiceUpdate,
    db: DbSession,
    tenant: CurrentTenant,
):
    """Update an invoice (DEV/PRO: draft+sent, FA/AV: draft only)."""
    result = await db.execute(
        select(Invoice)
        .where(Invoice.id == invoice_id, Invoice.tenant_id == tenant.id)
        .options(
            selectinload(Invoice.lines),
            selectinload(Invoice.payment_links),
        )
    )
    invoice = result.scalar_one_or_none()
    if not invoice:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invoice not found")

    _assert_invoice_editable(invoice)

    update_data = data.model_dump(exclude_unset=True)

    # Serialize pax_names from list to JSON string
    if "pax_names" in update_data and update_data["pax_names"] is not None:
        update_data["pax_names"] = json.dumps(update_data["pax_names"], ensure_ascii=False)

    # Recalculate deposit/balance if deposit_pct changes
    if "deposit_pct" in update_data and update_data["deposit_pct"] is not None:
        pct = Decimal(str(update_data["deposit_pct"]))
        invoice.deposit_pct = pct
        invoice.deposit_amount = (invoice.total_ttc * pct / Decimal("100")).quantize(Decimal("0.01"))
        invoice.balance_amount = invoice.total_ttc - invoice.deposit_amount
        del update_data["deposit_pct"]

    for field, value in update_data.items():
        setattr(invoice, field, value)

    await db.commit()
    await db.refresh(invoice)

    return InvoiceDetailResponse.model_validate(invoice)


@router.delete("/{invoice_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_invoice(
    invoice_id: int,
    db: DbSession,
    tenant: CurrentTenant,
):
    """Delete a draft invoice."""
    result = await db.execute(
        select(Invoice)
        .where(Invoice.id == invoice_id, Invoice.tenant_id == tenant.id)
    )
    invoice = result.scalar_one_or_none()
    if not invoice:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invoice not found")

    if invoice.status != "draft":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only draft invoices can be deleted",
        )

    await db.delete(invoice)
    await db.commit()


# ============================================================================
# PDF
# ============================================================================

@router.post("/{invoice_id}/generate-pdf")
async def generate_invoice_pdf(
    invoice_id: int,
    db: DbSession,
    tenant: CurrentTenant,
):
    """Generate or regenerate PDF for an invoice."""
    result = await db.execute(
        select(Invoice)
        .where(Invoice.id == invoice_id, Invoice.tenant_id == tenant.id)
        .options(selectinload(Invoice.lines))
    )
    invoice = result.scalar_one_or_none()
    if not invoice:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invoice not found")

    sender_info = tenant.invoice_sender_info or {}

    try:
        pdf_url = await generate_and_store_pdf(invoice, invoice.lines, tenant, sender_info)

        invoice.pdf_url = pdf_url
        invoice.pdf_generated_at = datetime.utcnow()
        await db.commit()

        return {"pdf_url": pdf_url, "generated_at": invoice.pdf_generated_at}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"PDF generation failed: {str(e)}",
        )


@router.get("/{invoice_id}/pdf")
async def get_invoice_pdf(
    invoice_id: int,
    db: DbSession,
    tenant: CurrentTenant,
):
    """Get PDF URL for an invoice."""
    result = await db.execute(
        select(Invoice)
        .where(Invoice.id == invoice_id, Invoice.tenant_id == tenant.id)
    )
    invoice = result.scalar_one_or_none()
    if not invoice:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invoice not found")

    if not invoice.pdf_url:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="PDF not generated yet. Use POST /generate-pdf first.",
        )

    return {"pdf_url": invoice.pdf_url, "generated_at": invoice.pdf_generated_at}


# ============================================================================
# Actions
# ============================================================================

@router.post("/{invoice_id}/send")
async def send_invoice(
    invoice_id: int,
    data: SendRequest,
    db: DbSession,
    user: CurrentUser,
    tenant: CurrentTenant,
):
    """Send invoice by email."""
    result = await db.execute(
        select(Invoice)
        .where(Invoice.id == invoice_id, Invoice.tenant_id == tenant.id)
    )
    invoice = result.scalar_one_or_none()
    if not invoice:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invoice not found")

    if invoice.status == "cancelled":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot send a cancelled invoice",
        )

    # TODO: integrate with email service when ready
    # For now, just update the status
    invoice.status = "sent"
    invoice.sent_at = datetime.utcnow()
    invoice.sent_to_email = data.to_email

    await db.commit()

    return {
        "message": "Invoice marked as sent",
        "sent_at": invoice.sent_at,
        "sent_to": data.to_email,
    }


@router.post("/{invoice_id}/mark-paid")
async def mark_invoice_paid(
    invoice_id: int,
    data: MarkPaidRequest,
    db: DbSession,
    tenant: CurrentTenant,
):
    """
    Mark an invoice as paid.

    If the invoice is a PRO (Proforma), a FA (Facture) is automatically
    generated with a definitive number and the balance amount.
    """
    result = await db.execute(
        select(Invoice)
        .where(Invoice.id == invoice_id, Invoice.tenant_id == tenant.id)
        .options(selectinload(Invoice.payment_links))
    )
    invoice = result.scalar_one_or_none()
    if not invoice:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invoice not found")

    if invoice.status == "cancelled":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot mark a cancelled invoice as paid",
        )

    payment_data = {
        "payment_method": data.payment_method,
        "payment_ref": data.payment_ref,
    }
    if data.paid_amount is not None:
        payment_data["paid_amount"] = data.paid_amount

    paid_invoice, generated_fa = await InvoiceService.mark_paid(
        db=db,
        invoice=invoice,
        payment_data=payment_data,
    )

    response = {
        "message": "Marqué comme payé",
        "paid_at": str(paid_invoice.paid_at),
    }

    if generated_fa:
        response["generated_invoice"] = {
            "id": generated_fa.id,
            "number": generated_fa.number,
            "type": "FA",
            "total_ttc": float(generated_fa.total_ttc),
        }

    return response


@router.post("/{invoice_id}/cancel")
async def cancel_invoice(
    invoice_id: int,
    data: CancelRequest,
    db: DbSession,
    user: CurrentUser,
    tenant: CurrentTenant,
):
    """Cancel an invoice, optionally creating a credit note (AV)."""
    result = await db.execute(
        select(Invoice)
        .where(Invoice.id == invoice_id, Invoice.tenant_id == tenant.id)
    )
    invoice = result.scalar_one_or_none()
    if not invoice:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invoice not found")

    if invoice.status == "cancelled":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invoice is already cancelled",
        )

    if data.create_credit_note and invoice.type in ("FA", "PRO"):
        try:
            credit_note = await InvoiceService.create_credit_note(
                db=db,
                tenant_id=tenant.id,
                user_id=user.id,
                invoice_id=invoice_id,
                reason=data.reason,
            )
            return {
                "message": "Invoice cancelled with credit note",
                "credit_note_id": credit_note.id,
                "credit_note_number": credit_note.number,
            }
        except ValueError as e:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    else:
        # Simple cancellation without credit note
        invoice.status = "cancelled"
        invoice.cancelled_at = datetime.utcnow()
        invoice.cancellation_reason = data.reason
        await db.commit()

        return {"message": "Invoice cancelled"}


@router.post("/{invoice_id}/advance")
async def advance_invoice_workflow(
    invoice_id: int,
    db: DbSession,
    user: CurrentUser,
    tenant: CurrentTenant,
):
    """
    Advance the invoice workflow:
    - DEV → PRO (create proforma with deposit)

    Note: PRO → FA is handled automatically when PRO is marked as paid.
    """
    result = await db.execute(
        select(Invoice)
        .where(Invoice.id == invoice_id, Invoice.tenant_id == tenant.id)
    )
    invoice = result.scalar_one_or_none()
    if not invoice:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invoice not found")

    new_invoice = await InvoiceService.advance_workflow(db, invoice)

    if not new_invoice:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot advance invoice of type '{invoice.type}' with status '{invoice.status}'",
        )

    # Reload with relationships
    result = await db.execute(
        select(Invoice)
        .where(Invoice.id == new_invoice.id)
        .options(
            selectinload(Invoice.lines),
            selectinload(Invoice.payment_links),
        )
    )
    new_invoice = result.scalar_one()

    return InvoiceDetailResponse.model_validate(new_invoice)


# ============================================================================
# Sharing — public link for client access
# ============================================================================

@router.post("/{invoice_id}/share")
async def create_share_link(
    invoice_id: int,
    db: DbSession,
    tenant: CurrentTenant,
):
    """Generate a shareable public link for an invoice."""
    result = await db.execute(
        select(Invoice)
        .where(Invoice.id == invoice_id, Invoice.tenant_id == tenant.id)
        .options(selectinload(Invoice.lines))
    )
    invoice = result.scalar_one_or_none()
    if not invoice:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invoice not found")

    if invoice.status == "draft":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Impossible de partager un brouillon. Envoyez le document d'abord.",
        )

    token = await InvoiceService.generate_share_token(db, invoice)

    # Auto-generate PDF if not yet done
    if not invoice.pdf_url:
        sender_info = tenant.invoice_sender_info or {}
        try:
            pdf_url = await generate_and_store_pdf(invoice, invoice.lines, tenant, sender_info)
            invoice.pdf_url = pdf_url
            invoice.pdf_generated_at = datetime.utcnow()
            await db.commit()
        except Exception:
            pass  # PDF gen failure should not block share link creation

    return {
        "share_token": str(token),
        "share_url": f"/invoices/{token}",
        "created_at": str(invoice.share_token_created_at),
        "viewed_at": str(invoice.shared_link_viewed_at) if invoice.shared_link_viewed_at else None,
    }


@router.get("/{invoice_id}/share")
async def get_share_info(
    invoice_id: int,
    db: DbSession,
    tenant: CurrentTenant,
):
    """Get sharing info for an invoice (token, URL, view status)."""
    result = await db.execute(
        select(Invoice)
        .where(Invoice.id == invoice_id, Invoice.tenant_id == tenant.id)
    )
    invoice = result.scalar_one_or_none()
    if not invoice:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invoice not found")

    if not invoice.share_token:
        return {"shared": False, "share_token": None, "share_url": None, "viewed_at": None}

    return {
        "shared": True,
        "share_token": str(invoice.share_token),
        "share_url": f"/invoices/{invoice.share_token}",
        "created_at": str(invoice.share_token_created_at),
        "viewed_at": str(invoice.shared_link_viewed_at) if invoice.shared_link_viewed_at else None,
    }


# ============================================================================
# Payment Reminder — Toggle automatic reminder
# ============================================================================


class ReminderToggleRequest(BaseModel):
    enabled: bool


@router.patch("/{invoice_id}/reminder")
async def toggle_invoice_reminder(
    invoice_id: int,
    data: ReminderToggleRequest,
    db: DbSession,
    tenant: CurrentTenant,
    user: CurrentUser,
):
    """
    Enable or disable the automatic payment reminder for an FA invoice.
    Only applicable to FA invoices that are not yet paid or cancelled.
    """
    result = await db.execute(
        select(Invoice)
        .where(Invoice.id == invoice_id, Invoice.tenant_id == tenant.id)
    )
    invoice = result.scalar_one_or_none()
    if not invoice:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invoice not found")

    if invoice.type != "FA":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Les relances automatiques ne s'appliquent qu'aux factures (FA).",
        )

    if invoice.status in ("paid", "cancelled"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Impossible de modifier la relance d'une facture payée ou annulée.",
        )

    invoice.reminder_enabled = data.enabled
    await db.commit()

    return {
        "message": f"Relance {'activée' if data.enabled else 'désactivée'}",
        "reminder_enabled": invoice.reminder_enabled,
        "reminder_date": str(invoice.reminder_date) if invoice.reminder_date else None,
    }


# ============================================================================
# Payment Links — Monetico online payment
# ============================================================================

@router.post("/{invoice_id}/payment-links/{link_id}/pay")
async def initiate_payment(
    invoice_id: int,
    link_id: int,
    db: DbSession,
    tenant: CurrentTenant,
):
    """
    Generate a Monetico payment URL for a specific payment link.

    Returns the payment URL (or a stub message if Monetico is not configured).
    """
    from app.services.monetico_service import monetico_service

    # Load invoice + verify tenant
    result = await db.execute(
        select(Invoice)
        .where(Invoice.id == invoice_id, Invoice.tenant_id == tenant.id)
        .options(selectinload(Invoice.payment_links))
    )
    invoice = result.scalar_one_or_none()
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")

    # Find the payment link
    payment_link = next((pl for pl in invoice.payment_links if pl.id == link_id), None)
    if not payment_link:
        raise HTTPException(status_code=404, detail="Payment link not found")

    if payment_link.status == "paid":
        raise HTTPException(status_code=400, detail="Payment link already paid")

    # Generate Monetico payment request
    base_url = "https://www.nomadays.com"  # TODO: use env var
    payment_result = monetico_service.create_payment_request(
        amount=float(payment_link.amount),
        currency=invoice.currency or "EUR",
        reference=f"PL-{payment_link.id}",
        return_url=f"{base_url}/invoices/{invoice.share_token}",
        cancel_url=f"{base_url}/invoices/{invoice.share_token}",
        notify_url=f"{base_url}/api/webhooks/monetico/payment-return",
    )

    # Store payment URL if available
    if payment_result.get("payment_url"):
        payment_link.payment_url = payment_result["payment_url"]
        await db.commit()

    return {
        "payment_url": payment_result.get("payment_url"),
        "payment_id": payment_result.get("payment_id"),
        "status": payment_result.get("status", "stub"),
        "message": payment_result.get("message"),
    }


# ============================================================================
# Invoice Lines
# ============================================================================

@router.post("/{invoice_id}/lines", response_model=InvoiceLineResponse, status_code=status.HTTP_201_CREATED)
async def add_invoice_line(
    invoice_id: int,
    data: InvoiceLineCreate,
    db: DbSession,
    tenant: CurrentTenant,
):
    """Add a line to a draft invoice."""
    result = await db.execute(
        select(Invoice)
        .where(Invoice.id == invoice_id, Invoice.tenant_id == tenant.id)
        .options(selectinload(Invoice.lines))
    )
    invoice = result.scalar_one_or_none()
    if not invoice:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invoice not found")

    _assert_invoice_editable(invoice)

    # Determine sort order
    max_order = max((l.sort_order for l in invoice.lines), default=-1)

    total_ttc = (data.quantity * data.unit_price_ttc).quantize(Decimal("0.01"))

    line = InvoiceLine(
        tenant_id=tenant.id,
        invoice_id=invoice_id,
        sort_order=max_order + 1,
        description=data.description,
        details=data.details,
        quantity=data.quantity,
        unit_price_ttc=data.unit_price_ttc,
        total_ttc=total_ttc,
        line_type=data.line_type,
    )
    db.add(line)

    # Recalculate invoice total
    invoice.total_ttc += total_ttc
    invoice.deposit_amount = (invoice.total_ttc * invoice.deposit_pct / Decimal("100")).quantize(Decimal("0.01"))
    invoice.balance_amount = invoice.total_ttc - invoice.deposit_amount

    await db.commit()
    await db.refresh(line)

    return InvoiceLineResponse.model_validate(line)


@router.patch("/{invoice_id}/lines/{line_id}", response_model=InvoiceLineResponse)
async def update_invoice_line(
    invoice_id: int,
    line_id: int,
    data: InvoiceLineUpdate,
    db: DbSession,
    tenant: CurrentTenant,
):
    """Update a line on a draft invoice."""
    result = await db.execute(
        select(Invoice)
        .where(Invoice.id == invoice_id, Invoice.tenant_id == tenant.id)
    )
    invoice = result.scalar_one_or_none()
    if not invoice:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invoice not found")

    _assert_invoice_editable(invoice)

    result = await db.execute(
        select(InvoiceLine)
        .where(
            InvoiceLine.id == line_id,
            InvoiceLine.invoice_id == invoice_id,
            InvoiceLine.tenant_id == tenant.id,
        )
    )
    line = result.scalar_one_or_none()
    if not line:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invoice line not found")

    old_total = line.total_ttc

    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(line, field, value)

    # Recalculate line total
    line.total_ttc = (line.quantity * line.unit_price_ttc).quantize(Decimal("0.01"))

    # Recalculate invoice total
    diff = line.total_ttc - old_total
    invoice.total_ttc += diff
    invoice.deposit_amount = (invoice.total_ttc * invoice.deposit_pct / Decimal("100")).quantize(Decimal("0.01"))
    invoice.balance_amount = invoice.total_ttc - invoice.deposit_amount

    await db.commit()
    await db.refresh(line)

    return InvoiceLineResponse.model_validate(line)


@router.delete("/{invoice_id}/lines/{line_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_invoice_line(
    invoice_id: int,
    line_id: int,
    db: DbSession,
    tenant: CurrentTenant,
):
    """Delete a line from a draft invoice."""
    result = await db.execute(
        select(Invoice)
        .where(Invoice.id == invoice_id, Invoice.tenant_id == tenant.id)
    )
    invoice = result.scalar_one_or_none()
    if not invoice:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invoice not found")

    _assert_invoice_editable(invoice)

    result = await db.execute(
        select(InvoiceLine)
        .where(
            InvoiceLine.id == line_id,
            InvoiceLine.invoice_id == invoice_id,
            InvoiceLine.tenant_id == tenant.id,
        )
    )
    line = result.scalar_one_or_none()
    if not line:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invoice line not found")

    # Recalculate invoice total
    invoice.total_ttc -= line.total_ttc
    invoice.deposit_amount = (invoice.total_ttc * invoice.deposit_pct / Decimal("100")).quantize(Decimal("0.01"))
    invoice.balance_amount = invoice.total_ttc - invoice.deposit_amount

    await db.delete(line)
    await db.commit()
