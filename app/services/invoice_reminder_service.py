"""
Invoice payment reminder service.

Runs as a daily scheduled job (APScheduler).
Finds FA invoices where reminder_date <= today, reminder not yet sent,
status is not paid/cancelled, and reminder_enabled is True.
Sends an email to the client and records the send timestamp.
"""

import logging
from datetime import date, datetime

from sqlalchemy import select, and_

from app.database import async_session_maker
from app.models.invoice import Invoice
from app.models.tenant import Tenant
from app.services.email_service import EmailService

logger = logging.getLogger(__name__)


async def process_invoice_reminders() -> None:
    """
    Main entry point for the daily reminder job.

    Creates its own DB session (not a request-scoped dependency).
    Finds all eligible invoices across all tenants and sends reminders.
    """
    today = date.today()
    logger.info("Starting invoice reminder processing for date: %s", today)

    async with async_session_maker() as db:
        # Find all FA invoices needing a reminder
        query = (
            select(Invoice)
            .where(
                and_(
                    Invoice.type == "FA",
                    Invoice.status.in_(["draft", "sent"]),
                    Invoice.reminder_enabled == True,  # noqa: E712
                    Invoice.reminder_sent_at.is_(None),
                    Invoice.reminder_date <= today,
                    Invoice.client_email.isnot(None),
                )
            )
            .order_by(Invoice.tenant_id, Invoice.id)
        )

        result = await db.execute(query)
        invoices = result.scalars().all()

        if not invoices:
            logger.info("No invoices need reminders today.")
            return

        logger.info("Found %d invoice(s) needing reminders.", len(invoices))

        email_service = EmailService()
        sent_count = 0
        error_count = 0

        # Cache tenants to avoid repeated queries
        tenant_cache: dict[int, Tenant] = {}

        for invoice in invoices:
            try:
                # Load tenant (with cache)
                tenant = tenant_cache.get(invoice.tenant_id)
                if tenant is None:
                    tenant_result = await db.execute(
                        select(Tenant).where(Tenant.id == invoice.tenant_id)
                    )
                    tenant = tenant_result.scalar_one_or_none()
                    if not tenant:
                        logger.warning(
                            "Tenant not found for invoice %s (tenant_id=%s)",
                            invoice.number, invoice.tenant_id,
                        )
                        continue
                    tenant_cache[invoice.tenant_id] = tenant

                # Build and send reminder email
                success = _send_reminder_email(
                    email_service=email_service,
                    invoice=invoice,
                    tenant=tenant,
                )

                if success:
                    invoice.reminder_sent_at = datetime.utcnow()
                    sent_count += 1
                    logger.info(
                        "Reminder sent for invoice %s to %s",
                        invoice.number, invoice.client_email,
                    )
                else:
                    error_count += 1

            except Exception as e:
                logger.error(
                    "Error processing reminder for invoice %s: %s",
                    invoice.number, e, exc_info=True,
                )
                error_count += 1

        # Commit all updates at once
        await db.commit()
        logger.info(
            "Reminder processing complete. Sent: %d, Errors: %d",
            sent_count, error_count,
        )


def _send_reminder_email(
    email_service: EmailService,
    invoice: Invoice,
    tenant: Tenant,
) -> bool:
    """Build and send a single reminder email."""
    client_name = _escape(invoice.client_name or "Client")
    due_date_str = _format_date(invoice.due_date)
    amount = invoice.balance_amount or invoice.total_ttc
    amount_str = f"{amount:,.2f} {invoice.currency}".replace(",", " ")

    # Build share link if available
    share_link_section = ""
    if invoice.share_token:
        # TODO: make configurable per tenant via env var
        base_url = "https://www.nomadays.com"
        share_url = f"{base_url}/invoices/{invoice.share_token}"
        share_link_section = f"""
      <div style="margin-top:24px;text-align:center;">
        <a href="{_escape(share_url)}"
           style="display:inline-block;background:#0FB6BC;color:#FFFFFF;text-decoration:none;
                  padding:14px 36px;border-radius:6px;font-weight:700;font-size:15px;
                  font-family:'Nunito',Arial,sans-serif;">
          Consulter et payer ma facture
        </a>
      </div>"""

    # Sender info from tenant
    sender_info = tenant.invoice_sender_info or {}
    company_name = _escape(
        sender_info.get("company_name") or tenant.name or "Nomadays"
    )

    subject = f"Rappel — Facture {invoice.number} — Échéance le {due_date_str}"

    html_content = f"""<!DOCTYPE html>
<html lang="fr">
<head><meta charset="UTF-8"></head>
<body style="margin:0;padding:0;font-family:'Source Sans 3',Arial,sans-serif;background:#FAFAFA;">
  <div style="max-width:600px;margin:24px auto;background:#FFFFFF;border-radius:8px;
              border:1px solid #E5E5E5;overflow:hidden;">

    <!-- Header (terracotta = warning/rappel) -->
    <div style="background:#DD9371;padding:24px 32px;">
      <h1 style="margin:0;color:#FFFFFF;font-family:'Nunito',Arial,sans-serif;
                 font-size:20px;font-weight:700;">
        Rappel de paiement
      </h1>
      <p style="margin:6px 0 0;color:#FDF5F2;font-size:14px;">
        Facture {_escape(invoice.number)}
      </p>
    </div>

    <!-- Body -->
    <div style="padding:24px 32px;">
      <p style="color:#525252;font-size:15px;margin:0 0 16px;line-height:1.6;">
        Bonjour {client_name},
      </p>
      <p style="color:#525252;font-size:15px;margin:0 0 20px;line-height:1.6;">
        Nous vous rappelons que votre facture arrive bient\u00f4t \u00e0 \u00e9ch\u00e9ance.
        Merci de bien vouloir proc\u00e9der au r\u00e8glement dans les meilleurs d\u00e9lais.
      </p>

      <table style="width:100%;border-collapse:collapse;font-size:14px;">
        <tr>
          <td style="padding:10px 16px;border-bottom:1px solid #F0F0F0;color:#737373;width:45%;">
            Facture
          </td>
          <td style="padding:10px 16px;border-bottom:1px solid #F0F0F0;color:#171717;font-weight:600;">
            {_escape(invoice.number)}
          </td>
        </tr>
        <tr>
          <td style="padding:10px 16px;border-bottom:1px solid #F0F0F0;color:#737373;">
            Montant d\u00fb
          </td>
          <td style="padding:10px 16px;border-bottom:1px solid #F0F0F0;color:#0FB6BC;
                     font-size:18px;font-weight:700;">
            {_escape(amount_str)}
          </td>
        </tr>
        <tr>
          <td style="padding:10px 16px;border-bottom:1px solid #F0F0F0;color:#737373;">
            Date d'\u00e9ch\u00e9ance
          </td>
          <td style="padding:10px 16px;border-bottom:1px solid #F0F0F0;color:#DC2626;
                     font-weight:600;">
            {_escape(due_date_str)}
          </td>
        </tr>
      </table>

      {share_link_section}

      <div style="margin-top:28px;padding-top:16px;border-top:1px solid #E5E5E5;">
        <p style="color:#525252;font-size:13px;margin:0;line-height:1.6;">
          Si vous avez d\u00e9j\u00e0 effectu\u00e9 le r\u00e8glement, veuillez ne pas tenir compte de ce message.
        </p>
        <p style="color:#525252;font-size:13px;margin:8px 0 0;line-height:1.6;">
          Pour toute question, n'h\u00e9sitez pas \u00e0 nous contacter.
        </p>
      </div>
    </div>

    <!-- Footer -->
    <div style="background:#F5F5F5;padding:16px 32px;text-align:center;">
      <p style="margin:0;color:#A3A3A3;font-size:12px;">
        {company_name} — Cet email a \u00e9t\u00e9 envoy\u00e9 automatiquement.
      </p>
    </div>

  </div>
</body>
</html>"""

    return email_service.send_generic(
        to=invoice.client_email,
        subject=subject,
        html_content=html_content,
    )


# ── Helpers ──────────────────────────────────────────────────────────────


def _format_date(value) -> str:
    """Return a human-readable date string (DD/MM/YYYY)."""
    if isinstance(value, date):
        return value.strftime("%d/%m/%Y")
    if isinstance(value, str):
        return value
    return str(value) if value else ""


def _escape(value) -> str:
    """Minimal HTML escape for user-provided values."""
    if value is None:
        return ""
    s = str(value)
    return (
        s.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#x27;")
    )
