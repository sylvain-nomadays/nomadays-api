"""
Monetico payment webhook — receives payment notifications.

This endpoint is called by Monetico's servers after a payment attempt.
No authentication required (uses HMAC seal verification instead).

STUB: Logs the incoming data but does not process real payments yet.
"""

import logging
from datetime import datetime

from fastapi import APIRouter, Request, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import Depends

from app.database import get_db
from app.models.invoice import Invoice, InvoicePaymentLink
from app.services.monetico_service import monetico_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhooks/monetico", tags=["Monetico Webhooks"])


@router.post("/payment-return")
async def monetico_payment_return(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """
    Receive Monetico payment notification (server-to-server).

    Monetico sends a POST with form data containing payment result + MAC seal.
    We verify the seal, update the payment link status, and return the
    expected acknowledgement.

    Expected Monetico response format:
        version=2 cdr=0 (success) or cdr=1 (failure)
    """
    # Parse form data
    form_data = await request.form()
    data = dict(form_data)

    logger.info("[Monetico webhook] Received notification: %s", data)

    # Extract key fields
    reference = data.get("reference", "")
    code_retour = data.get("code-retour", "")
    received_seal = data.get("MAC", "")

    # ── Verify HMAC seal ──
    if not monetico_service.verify_payment_response(data, received_seal):
        logger.warning("[Monetico webhook] Invalid MAC seal for reference: %s", reference)
        return Response(
            content="version=2\ncdr=1\n",
            media_type="text/plain",
        )

    # ── Process payment result ──
    # Reference format: "PL-{payment_link_id}" (e.g. "PL-42")
    payment_link_id = None
    if reference.startswith("PL-"):
        try:
            payment_link_id = int(reference.split("-", 1)[1])
        except (ValueError, IndexError):
            pass

    if payment_link_id:
        result = await db.execute(
            select(InvoicePaymentLink).where(InvoicePaymentLink.id == payment_link_id)
        )
        payment_link = result.scalar_one_or_none()

        if payment_link and code_retour == "payetest":
            # Successful payment (test mode) or "paiement" in production
            payment_link.status = "paid"
            payment_link.paid_at = datetime.utcnow()
            payment_link.payment_method = "card_monetico"
            payment_link.payment_ref = data.get("numauto", "")
            payment_link.paid_amount = payment_link.amount

            await db.commit()

            logger.info(
                "[Monetico webhook] Payment link %d marked as paid (ref: %s)",
                payment_link_id,
                reference,
            )

            # Check if all payment links for this invoice are paid
            await _check_invoice_fully_paid(db, payment_link.invoice_id)
        else:
            logger.info(
                "[Monetico webhook] Payment not successful for link %d (code: %s)",
                payment_link_id if payment_link_id else 0,
                code_retour,
            )
    else:
        logger.warning("[Monetico webhook] Unknown reference format: %s", reference)

    # Acknowledge receipt to Monetico
    return Response(
        content="version=2\ncdr=0\n",
        media_type="text/plain",
    )


async def _check_invoice_fully_paid(db: AsyncSession, invoice_id: int) -> None:
    """If all payment links are paid, mark the invoice as paid."""
    result = await db.execute(
        select(InvoicePaymentLink).where(InvoicePaymentLink.invoice_id == invoice_id)
    )
    links = result.scalars().all()

    if not links:
        return

    all_paid = all(link.status == "paid" for link in links)
    if all_paid:
        result = await db.execute(
            select(Invoice).where(Invoice.id == invoice_id)
        )
        invoice = result.scalar_one_or_none()
        if invoice and invoice.status != "paid":
            invoice.status = "paid"
            invoice.paid_at = datetime.utcnow()
            await db.commit()
            logger.info(
                "[Monetico webhook] Invoice %d fully paid — all payment links settled",
                invoice_id,
            )
