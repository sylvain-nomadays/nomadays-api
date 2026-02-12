"""
Invoice PDF generation service.
Uses Jinja2 for HTML templating + WeasyPrint for PDF conversion.

If WeasyPrint is not available, falls back to returning HTML only.
"""

import os
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Optional

from jinja2 import Environment, FileSystemLoader

from app.models.invoice import Invoice, InvoiceLine
from app.models.tenant import Tenant


# Template directory
TEMPLATE_DIR = Path(__file__).parent.parent / "templates"


def _get_jinja_env() -> Environment:
    """Create Jinja2 environment with the templates directory."""
    return Environment(
        loader=FileSystemLoader(str(TEMPLATE_DIR)),
        autoescape=True,
    )


def _format_amount(amount: Decimal | float | None, currency: str = "EUR") -> str:
    """Format amount for display: 1 467,00 €"""
    if amount is None:
        return "0,00 €"
    value = Decimal(str(amount))
    # French format: space as thousands separator, comma as decimal
    integer_part = int(abs(value))
    decimal_part = abs(value) - integer_part
    formatted_int = f"{integer_part:,}".replace(",", " ")
    formatted_dec = f"{decimal_part:.2f}"[1:]  # .XX
    formatted_dec = formatted_dec.replace(".", ",")
    sign = "-" if value < 0 else ""
    symbol = "€" if currency == "EUR" else currency
    return f"{sign}{formatted_int}{formatted_dec} {symbol}"


def _format_date(d) -> str:
    """Format date for display: 10/02/2026"""
    if d is None:
        return ""
    if isinstance(d, str):
        return d
    return d.strftime("%d/%m/%Y")


def render_invoice_html(
    invoice: Invoice,
    lines: list[InvoiceLine],
    tenant: Tenant,
    sender_info: dict | None = None,
) -> str:
    """
    Render invoice HTML from Jinja2 template.

    Args:
        invoice: The Invoice model
        lines: List of InvoiceLine models
        tenant: The Tenant model
        sender_info: Override sender info (or use tenant.invoice_sender_info)

    Returns:
        HTML string ready for PDF conversion or preview
    """
    env = _get_jinja_env()
    template = env.get_template("invoice.html")

    # Use tenant sender info or defaults
    sender = sender_info or (tenant.invoice_sender_info if tenant.invoice_sender_info else {})
    if not sender:
        sender = {
            "company_name": "NOMADAYS SAS",
            "address": "123 rue du Voyage",
            "postal_code": "75001",
            "city": "Paris",
            "country": "France",
            "siren": "123 456 789",
            "siret": "123 456 789 00012",
            "rcs": "Paris B 123 456 789",
            "vat_number": "FR12345678901",
            "capital": "10 000 €",
            "immatriculation": "IM075XXXXXX",
            "garantie": "APST - 15 avenue Carnot, 75017 Paris",
            "assurance_rcp": "AXA France - Contrat n° 1234567890",
            "mediateur": "MTV - Médiation Tourisme et Voyage - www.mtv.travel - BP 80 303, 75823 Paris Cedex 17",
        }

    # Inject SIREN from tenant model if not in sender_info
    if not sender.get("siren") and hasattr(tenant, "siren") and tenant.siren:
        sender["siren"] = tenant.siren

    # Document type labels
    type_labels = {
        "DEV": "DEVIS",
        "PRO": "FACTURE PROFORMA",
        "FA": "FACTURE",
        "AV": "AVOIR",
    }

    # Build template context
    context = {
        # Document
        "doc_type_label": type_labels.get(invoice.type, "DOCUMENT"),
        "invoice": invoice,
        "lines": lines,
        "sender": sender,
        # Formatting helpers
        "format_amount": _format_amount,
        "format_date": _format_date,
        # Computed values
        "is_credit_note": invoice.type == "AV",
        "is_eu": invoice.vat_regime == "margin",
        "show_deposit_balance": invoice.type in ("DEV", "PRO", "FA") and invoice.deposit_amount and invoice.deposit_amount > 0,
        "generated_at": datetime.now().strftime("%d/%m/%Y à %H:%M"),
    }

    return template.render(**context)


async def generate_pdf_bytes(
    invoice: Invoice,
    lines: list[InvoiceLine],
    tenant: Tenant,
    sender_info: dict | None = None,
) -> bytes:
    """
    Generate PDF bytes from invoice data.

    Uses WeasyPrint if available, otherwise raises ImportError.
    """
    html = render_invoice_html(invoice, lines, tenant, sender_info)

    try:
        from weasyprint import HTML
        pdf_bytes = HTML(string=html).write_pdf()
        return pdf_bytes
    except ImportError:
        raise ImportError(
            "WeasyPrint is required for PDF generation. "
            "Install it with: pip install weasyprint"
        )


async def generate_and_store_pdf(
    invoice: Invoice,
    lines: list[InvoiceLine],
    tenant: Tenant,
    sender_info: dict | None = None,
) -> str:
    """
    Generate PDF and upload to Supabase Storage.

    Returns the public URL of the stored PDF.
    """
    pdf_bytes = await generate_pdf_bytes(invoice, lines, tenant, sender_info)

    # Upload to Supabase Storage
    from supabase import create_client

    supabase_url = os.environ.get("SUPABASE_URL", "")
    supabase_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")

    if not supabase_url or not supabase_key:
        raise ValueError("Supabase credentials not configured for PDF storage")

    client = create_client(supabase_url, supabase_key)

    # Storage path: invoices/{tenant_id}/{year}/{type}/{number}.pdf
    storage_path = (
        f"invoices/{invoice.tenant_id}/{invoice.year}"
        f"/{invoice.type}/{invoice.number}.pdf"
    )

    # Upload
    client.storage.from_("documents").upload(
        storage_path,
        pdf_bytes,
        file_options={"content-type": "application/pdf", "upsert": "true"},
    )

    # Get public URL
    url_response = client.storage.from_("documents").get_public_url(storage_path)

    return url_response
