"""
Public invoice endpoints — no authentication required.
Accessed via share token by clients to view/download invoices.

Includes:
- Invoice metadata + HTML rendering
- Billing address validation
- Insurance selection (Chapka stub V1)
- Promo code application / removal
- PDF download

Security: all queries filter by share_token only, never by invoice_id or tenant_id.
Invalid UUIDs return 404 (no information leakage).
"""

import uuid
from datetime import datetime, date
from decimal import Decimal
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import HTMLResponse, Response
from pydantic import BaseModel, Field
from sqlalchemy import select, delete as sa_delete, text as sa_text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.models.invoice import Invoice, InvoiceLine, InvoicePaymentLink
from app.models.promo_code import PromoCode, PromoCodeUsage
from app.models.tenant import Tenant
from app.models.trip_insurance import TripInsurance
from app.services.invoice_pdf import render_invoice_html, generate_pdf_bytes
from app.services.invoice_service import InvoiceService
from app.services.destination_suggester import get_country_name

router = APIRouter(prefix="/public/invoices", tags=["Public Invoices"])

DbSession = Annotated[AsyncSession, Depends(get_db)]


# ---------------------------------------------------------------------------
# Pydantic schemas for public endpoints
# ---------------------------------------------------------------------------

class BillingAddressRequest(BaseModel):
    line1: str = Field(..., max_length=255)
    line2: Optional[str] = Field(None, max_length=255)
    city: str = Field(..., max_length=100)
    postal: str = Field(..., max_length=20)
    country: str = Field(..., max_length=100)


class ApplyPromoRequest(BaseModel):
    code: str = Field(..., max_length=50)


class SelectInsuranceRequest(BaseModel):
    insurance_type: str = Field(..., pattern="^(assistance|annulation|multirisques|declined)$")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

INSURANCE_STUB_PRICES = {
    "assistance": Decimal("25.00"),     # per pax
    "annulation": Decimal("45.00"),     # per pax
    "multirisques": Decimal("65.00"),   # per pax
    "declined": Decimal("0.00"),        # explicit decline
}

INSURANCE_LABELS = {
    "assistance": "Assistance rapatriement",
    "annulation": "Annulation toutes causes",
    "multirisques": "Multirisques (assistance + annulation)",
    "declined": "Assurance déclinée",
}


async def _get_invoice_by_token(
    share_token: str,
    db: AsyncSession,
) -> tuple[Invoice, Tenant]:
    """Load invoice and tenant by share_token. Raises 404 if not found."""
    try:
        token_uuid = uuid.UUID(share_token)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document introuvable")

    result = await db.execute(
        select(Invoice)
        .where(Invoice.share_token == token_uuid)
        .options(
            selectinload(Invoice.lines),
            selectinload(Invoice.payment_links),
            selectinload(Invoice.dossier),
        )
    )
    invoice = result.scalar_one_or_none()
    if not invoice:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document introuvable")

    # Load tenant for sender info (needed for PDF rendering)
    result = await db.execute(
        select(Tenant).where(Tenant.id == invoice.tenant_id)
    )
    tenant = result.scalar_one_or_none()
    if not tenant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document introuvable")

    return invoice, tenant


async def _build_invoice_response(invoice: Invoice, tenant: Tenant, sender_info: dict, html: str, db: AsyncSession) -> dict:
    """Build the full JSON response for the public invoice page."""

    # Document type labels
    type_labels = {
        "DEV": "Devis",
        "PRO": "Facture Proforma",
        "FA": "Facture",
        "AV": "Avoir",
    }

    # Payment links
    payment_links = []
    for pl in (invoice.payment_links or []):
        payment_links.append({
            "id": pl.id,
            "payment_type": pl.payment_type,
            "amount": float(pl.amount) if pl.amount else 0,
            "due_date": str(pl.due_date) if pl.due_date else None,
            "status": pl.status,
            "paid_at": str(pl.paid_at) if pl.paid_at else None,
            "payment_url": pl.payment_url,
        })

    # Billing address
    billing_address = None
    if any([
        invoice.billing_address_line1,
        invoice.billing_address_city,
        invoice.billing_address_postal,
        invoice.billing_address_country,
    ]):
        billing_address = {
            "line1": invoice.billing_address_line1 or "",
            "line2": invoice.billing_address_line2 or "",
            "city": invoice.billing_address_city or "",
            "postal": invoice.billing_address_postal or "",
            "country": invoice.billing_address_country or "",
        }

    # Pre-fill from lead participant if no billing address saved on invoice
    if billing_address is None and invoice.dossier_id:
        result = await db.execute(
            sa_text("""
                SELECT p.address, p.city, p.postal_code, p.country
                FROM dossier_participants dp
                JOIN participants p ON dp.participant_id = p.id
                WHERE dp.dossier_id = :dossier_id AND dp.is_lead = TRUE
                LIMIT 1
            """),
            {"dossier_id": str(invoice.dossier_id)},
        )
        lead = result.mappings().first()
        if lead and any([lead["address"], lead["city"], lead["postal_code"], lead["country"]]):
            billing_address = {
                "line1": lead["address"] or "",
                "line2": "",
                "city": lead["city"] or "",
                "postal": lead["postal_code"] or "",
                "country": get_country_name(lead["country"]) if lead["country"] else "",
            }

    # Fallback 2: parse invoice.client_address (free text like "14 Rue Royale, 75008 Paris, France")
    if billing_address is None and invoice.client_address:
        parts = [p.strip() for p in invoice.client_address.split(",")]
        if len(parts) >= 3:
            line1 = parts[0]
            # Try to split "75008 Paris" into postal + city
            city_part = parts[1].strip()
            postal = ""
            city = city_part
            tokens = city_part.split(" ", 1)
            if len(tokens) == 2 and tokens[0].isdigit():
                postal = tokens[0]
                city = tokens[1]
            country = parts[2].strip() if len(parts) >= 3 else ""
            billing_address = {
                "line1": line1,
                "line2": "",
                "city": city,
                "postal": postal,
                "country": country,
            }
        elif len(parts) == 2:
            billing_address = {
                "line1": parts[0],
                "line2": "",
                "city": parts[1],
                "postal": "",
                "country": "",
            }
        elif len(parts) == 1 and parts[0]:
            billing_address = {
                "line1": parts[0],
                "line2": "",
                "city": "",
                "postal": "",
                "country": "",
            }

    # Bank transfer info (from tenant config)
    bank_transfer_info = None
    if sender_info.get("bank_iban"):
        bank_transfer_info = {
            "bank_name": sender_info.get("bank_name", ""),
            "iban": sender_info.get("bank_iban", ""),
            "bic": sender_info.get("bank_bic", ""),
            "account_holder": sender_info.get("bank_account_holder", ""),
            "bank_address": sender_info.get("bank_address", ""),
        }

    # Insurance options (stub V1) — exclude "declined" from buyable options
    insurance_options = [
        {
            "type": ins_type,
            "label": INSURANCE_LABELS[ins_type],
            "price_per_pax": float(INSURANCE_STUB_PRICES[ins_type]),
            "available": True,
        }
        for ins_type in ("assistance", "annulation", "multirisques")
    ]
    # "declined" is handled separately in frontend as a button, not a priced option

    # Find existing insurance / promo lines
    selected_insurance = None
    applied_promo = None
    for line in (invoice.lines or []):
        if line.line_type == "insurance":
            selected_insurance = {
                "type": line.details or "multirisques",
                "label": INSURANCE_LABELS.get(line.details or "", line.description),
                "total": float(line.total_ttc),
                "line_id": line.id,
            }
        elif line.line_type == "discount":
            applied_promo = {
                "description": line.description,
                "discount_amount": float(abs(line.total_ttc)),
                "line_id": line.id,
            }

    # Is proforma? (only PRO invoices get the validation sections)
    is_proforma = invoice.type == "PRO"

    # Destination & partner from tenant
    destination = get_country_name(tenant.country_code) if tenant.country_code else None
    partner_name = tenant.name if tenant.name else None

    # Dossier reference (real reference, not UUID)
    dossier_reference = None
    if invoice.dossier:
        dossier_reference = invoice.dossier.reference

    return {
        "number": invoice.number,
        "type": invoice.type,
        "type_label": type_labels.get(invoice.type, "Document"),
        "status": invoice.status,
        "client_name": invoice.client_name,
        "total_ttc": float(invoice.total_ttc) if invoice.total_ttc else 0,
        "currency": invoice.currency,
        "issue_date": str(invoice.issue_date) if invoice.issue_date else None,
        "company_name": sender_info.get("company_name", tenant.name if tenant.name else "NOMADAYS"),
        "html": html,
        "payment_links": payment_links,
        # New fields for pre-invoice validation
        "is_proforma": is_proforma,
        "billing_address": billing_address,
        "billing_address_validated": invoice.billing_address_validated_at is not None,
        "bank_transfer_info": bank_transfer_info,
        "insurance_options": insurance_options if is_proforma else [],
        "selected_insurance": selected_insurance,
        "applied_promo": applied_promo,
        "pax_count": invoice.pax_count or 1,
        "cgv_accepted": invoice.cgv_accepted_at is not None,
        "cgv_html": sender_info.get("cgv_html") if sender_info else None,
        # Voyage info
        "destination": destination,
        "partner_name": partner_name,
        "dossier_reference": dossier_reference,
    }


def _recalculate_invoice_totals(invoice: Invoice) -> None:
    """Recalculate invoice totals from lines, and update payment link amounts."""
    # Sum all lines (discount lines have negative total_ttc)
    total = sum(line.total_ttc for line in (invoice.lines or []))
    if total < Decimal("0"):
        total = Decimal("0")
    invoice.total_ttc = total

    # Recalculate deposit/balance
    # Deposit = % on services/fees/discounts only + 100% of insurance
    services_total = sum(
        line.total_ttc for line in (invoice.lines or [])
        if line.line_type in ("service", "discount", "fee")
    )
    if services_total < Decimal("0"):
        services_total = Decimal("0")

    insurance_total = sum(
        line.total_ttc for line in (invoice.lines or [])
        if line.line_type == "insurance"
    )

    deposit_on_services = (
        services_total * invoice.deposit_pct / Decimal("100")
    ).quantize(Decimal("0.01"))
    invoice.deposit_amount = deposit_on_services + insurance_total
    invoice.balance_amount = invoice.total_ttc - invoice.deposit_amount

    # Update pending payment link amounts
    for pl in (invoice.payment_links or []):
        if pl.status == "pending":
            if pl.payment_type == "deposit":
                pl.amount = invoice.deposit_amount
            elif pl.payment_type == "balance":
                pl.amount = invoice.balance_amount
            elif pl.payment_type == "full":
                pl.amount = invoice.total_ttc


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/{share_token}")
async def get_public_invoice_metadata(
    share_token: str,
    db: DbSession,
):
    """
    Return invoice metadata as JSON (for the Next.js public page).
    Includes rendered HTML, billing address, insurance options, promo info, bank details.
    """
    invoice, tenant = await _get_invoice_by_token(share_token, db)

    # Record view
    await InvoiceService.record_share_view(db, invoice)

    sender_info = tenant.invoice_sender_info or {}
    html = render_invoice_html(invoice, invoice.lines, tenant, sender_info)

    return await _build_invoice_response(invoice, tenant, sender_info, html, db)


@router.get("/{share_token}/html", response_class=HTMLResponse)
async def get_public_invoice_html(
    share_token: str,
    db: DbSession,
):
    """Return rendered invoice HTML for direct viewing."""
    invoice, tenant = await _get_invoice_by_token(share_token, db)

    # Record view
    await InvoiceService.record_share_view(db, invoice)

    sender_info = tenant.invoice_sender_info or {}
    html = render_invoice_html(invoice, invoice.lines, tenant, sender_info)

    return HTMLResponse(content=html)


@router.get("/{share_token}/pdf")
async def get_public_invoice_pdf(
    share_token: str,
    db: DbSession,
):
    """Download invoice as PDF (generated on-the-fly for consistency)."""
    invoice, tenant = await _get_invoice_by_token(share_token, db)

    sender_info = tenant.invoice_sender_info or {}

    try:
        pdf_bytes = await generate_pdf_bytes(invoice, invoice.lines, tenant, sender_info)
    except ImportError:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="PDF generation is not available",
        )

    filename = f"{invoice.number}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
        },
    )


# ---------------------------------------------------------------------------
# Billing address
# ---------------------------------------------------------------------------

@router.patch("/{share_token}/billing-address")
async def update_billing_address(
    share_token: str,
    body: BillingAddressRequest,
    db: DbSession,
):
    """Validate and save the client's billing address on the invoice."""
    invoice, tenant = await _get_invoice_by_token(share_token, db)

    invoice.billing_address_line1 = body.line1
    invoice.billing_address_line2 = body.line2
    invoice.billing_address_city = body.city
    invoice.billing_address_postal = body.postal
    invoice.billing_address_country = body.country
    invoice.billing_address_validated_at = datetime.utcnow()

    # Also update client_address so DESTINATAIRE section shows the validated address
    address_parts = [body.line1]
    if body.line2:
        address_parts.append(body.line2)
    address_parts.append(f"{body.postal} {body.city}")
    if body.country:
        address_parts.append(body.country)
    invoice.client_address = ", ".join(address_parts)

    # Also update the dossier client address for future invoices
    if invoice.dossier:
        invoice.dossier.client_address = invoice.client_address

    # Propagate billing address to lead participant's profile
    if invoice.dossier_id:
        from app.services.destination_suggester import get_country_code

        lead_result = await db.execute(
            sa_text("""
                SELECT dp.participant_id
                FROM dossier_participants dp
                WHERE dp.dossier_id = :dossier_id AND dp.is_lead = TRUE
                LIMIT 1
            """),
            {"dossier_id": str(invoice.dossier_id)},
        )
        lead_row = lead_result.mappings().first()
        if lead_row:
            country_code = get_country_code(body.country) if body.country else None
            await db.execute(
                sa_text("""
                    UPDATE participants
                    SET address = :address,
                        city = :city,
                        postal_code = :postal_code,
                        country = :country
                    WHERE id = :participant_id
                """),
                {
                    "address": body.line1,
                    "city": body.city,
                    "postal_code": body.postal,
                    "country": country_code,
                    "participant_id": str(lead_row["participant_id"]),
                },
            )

    await db.commit()
    await db.refresh(invoice)

    sender_info = tenant.invoice_sender_info or {}
    html = render_invoice_html(invoice, invoice.lines, tenant, sender_info)
    return await _build_invoice_response(invoice, tenant, sender_info, html, db)


# ---------------------------------------------------------------------------
# Promo codes
# ---------------------------------------------------------------------------

@router.post("/{share_token}/apply-promo")
async def apply_promo_code(
    share_token: str,
    body: ApplyPromoRequest,
    db: DbSession,
):
    """Apply a promo code to the invoice. Creates a discount line and recalculates totals."""
    invoice, tenant = await _get_invoice_by_token(share_token, db)

    # Check no promo already applied
    existing_discount = next(
        (l for l in (invoice.lines or []) if l.line_type == "discount"),
        None,
    )
    if existing_discount:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Un code promo est déjà appliqué. Retirez-le d'abord.",
        )

    # Lookup promo code (case-insensitive)
    result = await db.execute(
        select(PromoCode).where(PromoCode.code == body.code.upper().strip())
    )
    promo = result.scalar_one_or_none()
    if not promo:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Code promo invalide",
        )

    # Validate promo
    # Calculate total before discount (only service + insurance + fee lines)
    base_total = sum(
        l.total_ttc for l in (invoice.lines or [])
        if l.line_type in ("service", "insurance", "fee")
    )

    valid, error_msg = promo.is_valid(invoice_amount=base_total)
    if not valid:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=error_msg)

    # Calculate discount
    discount_amount = promo.calculate_discount(base_total)
    if discount_amount <= 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Le montant de la réduction est nul",
        )

    # Create discount line (negative amount)
    max_sort = max((l.sort_order for l in (invoice.lines or [])), default=0)
    discount_line = InvoiceLine(
        tenant_id=invoice.tenant_id,
        invoice_id=invoice.id,
        sort_order=max_sort + 1,
        description=f"Réduction — Code promo {promo.code}",
        details=promo.description,
        quantity=Decimal("1"),
        unit_price_ttc=-discount_amount,
        total_ttc=-discount_amount,
        line_type="discount",
    )
    db.add(discount_line)

    # Track usage
    usage = PromoCodeUsage(
        promo_code_id=promo.id,
        invoice_id=invoice.id,
        discount_amount=discount_amount,
    )
    db.add(usage)

    # Increment usage count
    promo.current_uses = (promo.current_uses or 0) + 1

    # Add line to in-memory list for recalculation
    invoice.lines.append(discount_line)

    # Recalculate totals
    _recalculate_invoice_totals(invoice)

    await db.commit()
    await db.refresh(invoice)

    sender_info = tenant.invoice_sender_info or {}
    html = render_invoice_html(invoice, invoice.lines, tenant, sender_info)
    return await _build_invoice_response(invoice, tenant, sender_info, html, db)


@router.delete("/{share_token}/remove-promo")
async def remove_promo_code(
    share_token: str,
    db: DbSession,
):
    """Remove the applied promo code from the invoice."""
    invoice, tenant = await _get_invoice_by_token(share_token, db)

    # Find discount line
    discount_line = next(
        (l for l in (invoice.lines or []) if l.line_type == "discount"),
        None,
    )
    if not discount_line:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Aucun code promo appliqué",
        )

    # Find and remove usage record, decrement counter
    result = await db.execute(
        select(PromoCodeUsage).where(PromoCodeUsage.invoice_id == invoice.id)
    )
    usage = result.scalar_one_or_none()
    if usage:
        # Decrement promo counter
        result = await db.execute(
            select(PromoCode).where(PromoCode.id == usage.promo_code_id)
        )
        promo = result.scalar_one_or_none()
        if promo and promo.current_uses > 0:
            promo.current_uses -= 1
        await db.delete(usage)

    # Remove the discount line
    invoice.lines.remove(discount_line)
    await db.delete(discount_line)

    # Recalculate totals
    _recalculate_invoice_totals(invoice)

    await db.commit()
    await db.refresh(invoice)

    sender_info = tenant.invoice_sender_info or {}
    html = render_invoice_html(invoice, invoice.lines, tenant, sender_info)
    return await _build_invoice_response(invoice, tenant, sender_info, html, db)


# ---------------------------------------------------------------------------
# Insurance (Chapka stub V1)
# ---------------------------------------------------------------------------

@router.post("/{share_token}/select-insurance")
async def select_insurance(
    share_token: str,
    body: SelectInsuranceRequest,
    db: DbSession,
):
    """Select a travel insurance option. Creates an insurance line and recalculates totals."""
    invoice, tenant = await _get_invoice_by_token(share_token, db)

    # Check no insurance already selected
    existing_insurance = next(
        (l for l in (invoice.lines or []) if l.line_type == "insurance"),
        None,
    )
    if existing_insurance:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Une assurance est déjà sélectionnée. Retirez-la d'abord.",
        )

    # Calculate price (stub: fixed price × pax count)
    price_per_pax = INSURANCE_STUB_PRICES.get(body.insurance_type)
    if price_per_pax is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Type d'assurance invalide",
        )

    pax_count = invoice.pax_count or 1
    is_declined = body.insurance_type == "declined"

    if is_declined:
        total_premium = Decimal("0.00")
    else:
        total_premium = (price_per_pax * pax_count).quantize(Decimal("0.01"))

    # Create TripInsurance record (if dossier linked) — skip for declined
    if invoice.dossier_id and not is_declined:
        insurance_record = TripInsurance(
            tenant_id=invoice.tenant_id,
            dossier_id=invoice.dossier_id,
            invoice_id=invoice.id,
            insurance_type=body.insurance_type,
            provider="chapka",
            premium_amount=total_premium,
            commission_pct=Decimal("25.00"),
            commission_amount=(total_premium * Decimal("0.25")).quantize(Decimal("0.01")),
            currency=invoice.currency,
            status="quoted",
            start_date=invoice.travel_start_date,
            end_date=invoice.travel_end_date,
            pax_count=pax_count,
        )
        db.add(insurance_record)

    # Create insurance line on invoice
    max_sort = max((l.sort_order for l in (invoice.lines or [])), default=0)

    if is_declined:
        insurance_line = InvoiceLine(
            tenant_id=invoice.tenant_id,
            invoice_id=invoice.id,
            sort_order=max_sort + 1,
            description="Assurance déclinée par le client",
            details="declined",
            quantity=Decimal("1"),
            unit_price_ttc=Decimal("0.00"),
            total_ttc=Decimal("0.00"),
            line_type="insurance",
        )
    else:
        insurance_line = InvoiceLine(
            tenant_id=invoice.tenant_id,
            invoice_id=invoice.id,
            sort_order=max_sort + 1,
            description=f"Assurance voyage — {INSURANCE_LABELS[body.insurance_type]}",
            details=body.insurance_type,
            quantity=Decimal(str(pax_count)),
            unit_price_ttc=price_per_pax,
            total_ttc=total_premium,
            line_type="insurance",
        )
    db.add(insurance_line)
    invoice.lines.append(insurance_line)

    # Recalculate totals
    _recalculate_invoice_totals(invoice)

    await db.commit()
    await db.refresh(invoice)

    sender_info = tenant.invoice_sender_info or {}
    html = render_invoice_html(invoice, invoice.lines, tenant, sender_info)
    return await _build_invoice_response(invoice, tenant, sender_info, html, db)


@router.delete("/{share_token}/remove-insurance")
async def remove_insurance(
    share_token: str,
    db: DbSession,
):
    """Remove the selected insurance from the invoice."""
    invoice, tenant = await _get_invoice_by_token(share_token, db)

    # Find insurance line
    insurance_line = next(
        (l for l in (invoice.lines or []) if l.line_type == "insurance"),
        None,
    )
    if not insurance_line:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Aucune assurance sélectionnée",
        )

    # Remove TripInsurance record if exists
    if invoice.dossier_id:
        result = await db.execute(
            select(TripInsurance).where(
                TripInsurance.invoice_id == invoice.id,
                TripInsurance.tenant_id == invoice.tenant_id,
            )
        )
        trip_insurance = result.scalar_one_or_none()
        if trip_insurance:
            await db.delete(trip_insurance)

    # Remove line
    invoice.lines.remove(insurance_line)
    await db.delete(insurance_line)

    # Recalculate totals
    _recalculate_invoice_totals(invoice)

    await db.commit()
    await db.refresh(invoice)

    sender_info = tenant.invoice_sender_info or {}
    html = render_invoice_html(invoice, invoice.lines, tenant, sender_info)
    return await _build_invoice_response(invoice, tenant, sender_info, html, db)


# ---------------------------------------------------------------------------
# CGV acceptance
# ---------------------------------------------------------------------------

@router.post("/{share_token}/accept-cgv")
async def accept_cgv(
    share_token: str,
    db: DbSession,
):
    """Record client acceptance of the terms and conditions (CGV)."""
    invoice, tenant = await _get_invoice_by_token(share_token, db)

    if invoice.cgv_accepted_at:
        sender_info = tenant.invoice_sender_info or {}
        html = render_invoice_html(invoice, invoice.lines, tenant, sender_info)
        return await _build_invoice_response(invoice, tenant, sender_info, html, db)

    invoice.cgv_accepted_at = datetime.utcnow()

    # Store CGV PDF in dossier documents (best-effort)
    if invoice.dossier_id:
        try:
            await _store_cgv_document(invoice, tenant, db)
        except Exception:
            import logging
            logging.getLogger(__name__).warning(
                f"Failed to store CGV document for invoice {invoice.number}",
                exc_info=True,
            )

    await db.commit()
    await db.refresh(invoice)

    sender_info = tenant.invoice_sender_info or {}
    html = render_invoice_html(invoice, invoice.lines, tenant, sender_info)
    return await _build_invoice_response(invoice, tenant, sender_info, html, db)


async def _store_cgv_document(invoice: Invoice, tenant: Tenant, db: AsyncSession) -> None:
    """Generate CGV PDF and store it in the dossier documents via Supabase Storage."""
    from app.services.storage import get_supabase_client

    cgv_html = _generate_cgv_html(invoice, tenant)

    pdf_bytes = None
    # Try Playwright first
    try:
        from playwright.async_api import async_playwright
        async with async_playwright() as p:
            browser = await p.chromium.launch()
            page = await browser.new_page()
            await page.set_content(cgv_html, wait_until="networkidle")
            pdf_bytes = await page.pdf(format="A4", print_background=True)
            await browser.close()
    except Exception:
        pass

    # Fallback to WeasyPrint
    if pdf_bytes is None:
        try:
            from weasyprint import HTML as WeasyHTML
            pdf_bytes = WeasyHTML(string=cgv_html).write_pdf()
        except Exception:
            return

    supabase = get_supabase_client()
    now_str = datetime.utcnow().strftime("%Y-%m-%d")
    filename = f"cgv_acceptees_{now_str}.pdf"
    storage_path = f"{invoice.tenant_id}/{invoice.dossier_id}/{filename}"

    try:
        supabase.storage.from_("documents").upload(
            path=storage_path,
            file=pdf_bytes,
            file_options={"content-type": "application/pdf", "cache-control": "3600"},
        )
    except Exception:
        import logging
        logging.getLogger(__name__).warning("Failed to upload CGV PDF, skipping", exc_info=True)
        return

    import uuid as uuid_mod
    from sqlalchemy import text
    await db.execute(
        text("""
            INSERT INTO documents (id, tenant_id, dossier_id, storage_path, storage_bucket,
                                   filename, original_filename, mime_type, size_bytes,
                                   type, description, is_client_visible, created_at)
            VALUES (:id, :tenant_id, :dossier_id, :storage_path, :storage_bucket,
                    :filename, :original_filename, :mime_type, :size_bytes,
                    :type, :description, :is_client_visible, NOW())
        """),
        {
            "id": str(uuid_mod.uuid4()),
            "tenant_id": str(invoice.tenant_id),
            "dossier_id": str(invoice.dossier_id),
            "storage_path": storage_path,
            "storage_bucket": "documents",
            "filename": filename,
            "original_filename": filename,
            "mime_type": "application/pdf",
            "size_bytes": len(pdf_bytes),
            "type": "contract",
            "description": f"Conditions particulières de vente acceptées le {datetime.utcnow().strftime('%d/%m/%Y')}",
            "is_client_visible": True,
        },
    )


CGV_PLACEHOLDER_TEXT = """<h2>Article 1 — Objet</h2>
<p>Les présentes conditions particulières de vente régissent les relations contractuelles entre l'Organisateur et le Voyageur dans le cadre de la prestation de voyage référencée.</p>
<h2>Article 2 — Inscription et paiement</h2>
<p>L'inscription est considérée comme ferme et définitive après le versement de l'acompte prévu et l'acceptation des présentes conditions. Le solde doit être réglé au plus tard 30 jours avant la date de départ.</p>
<h2>Article 3 — Annulation par le Voyageur</h2>
<p>En cas d'annulation par le Voyageur, des frais d'annulation seront appliqués selon le barème suivant : plus de 60 jours avant le départ : 30%% du prix total ; de 60 à 31 jours : 50%% ; de 30 à 15 jours : 75%% ; moins de 15 jours : 100%%.</p>
<h2>Article 4 — Modification par l'Organisateur</h2>
<p>L'Organisateur se réserve le droit de modifier les éléments non essentiels du voyage. En cas de modification substantielle, le Voyageur pourra choisir entre l'acceptation de la modification, un voyage de substitution ou le remboursement intégral.</p>
<h2>Article 5 — Assurance</h2>
<p>L'Organisateur propose une assurance voyage couvrant l'annulation et l'assistance rapatriement. Le Voyageur est libre de souscrire ou de décliner cette assurance, étant informé des risques encourus en cas de non-souscription.</p>
<h2>Article 6 — Responsabilité</h2>
<p>L'Organisateur est responsable de la bonne exécution des services prévus au contrat, conformément aux dispositions du Code du tourisme.</p>
<h2>Article 7 — Réclamation et médiation</h2>
<p>Toute réclamation doit être adressée par écrit dans les 30 jours suivant la fin du voyage. En cas de litige, le Voyageur peut recourir au médiateur du tourisme et du voyage (MTV).</p>
<h2>Article 8 — Protection des données</h2>
<p>Les données personnelles collectées sont traitées conformément au RGPD. Le Voyageur dispose d'un droit d'accès, de rectification et de suppression de ses données.</p>
<h2>Article 9 — Droit applicable</h2>
<p>Les présentes conditions sont régies par le droit français.</p>"""


def _generate_cgv_html(invoice: Invoice, tenant: Tenant) -> str:
    """Generate HTML for the CGV acceptance document (PDF)."""
    company_name = "NOMADAYS"
    if tenant.invoice_sender_info:
        company_name = tenant.invoice_sender_info.get("company_name", tenant.name or "NOMADAYS")
    elif tenant.name:
        company_name = tenant.name

    # Use tenant-configured CGV text, fallback to placeholder
    cgv_content = CGV_PLACEHOLDER_TEXT
    if tenant.invoice_sender_info and tenant.invoice_sender_info.get("cgv_html"):
        cgv_content = tenant.invoice_sender_info["cgv_html"]

    accepted_date = invoice.cgv_accepted_at.strftime("%d/%m/%Y à %H:%M") if invoice.cgv_accepted_at else ""

    return f"""<!DOCTYPE html>
<html lang="fr"><head><meta charset="UTF-8">
<style>
body {{ font-family: Arial, sans-serif; font-size: 10pt; color: #333; margin: 40px; line-height: 1.6; }}
h1 {{ color: #0FB6BC; font-size: 16pt; margin-bottom: 20px; }}
h2 {{ color: #333; font-size: 12pt; margin-top: 20px; }}
.header {{ border-bottom: 2px solid #0FB6BC; padding-bottom: 15px; margin-bottom: 25px; }}
.company {{ font-size: 14pt; font-weight: bold; color: #0FB6BC; }}
.acceptance {{ margin-top: 30px; padding: 15px; background: #f0fafb; border: 1px solid #0FB6BC; border-radius: 6px; }}
.footer {{ margin-top: 30px; font-size: 8pt; color: #999; border-top: 1px solid #ddd; padding-top: 10px; }}
</style></head>
<body>
<div class="header"><div class="company">{company_name}</div>
<div>Facture : {invoice.number or ''}</div><div>Client : {invoice.client_name or ''}</div></div>
<h1>Conditions Particulières de Vente</h1>
{cgv_content}
<div class="acceptance"><strong>Acceptation des conditions</strong><br>
Les présentes conditions particulières de vente ont été acceptées électroniquement par le client le {accepted_date}.</div>
<div class="footer">Document généré automatiquement — {company_name}</div>
</body></html>"""
