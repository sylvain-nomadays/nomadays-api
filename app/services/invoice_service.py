"""
Invoice service — business logic for invoice creation, VAT calculation,
workflow advancement, and credit note generation.

Handles:
- DEV (Devis/Quote) → PRO (Proforma) → FA (Facture/Invoice) → AV (Avoir/Credit Note)
- VAT regime determination based on destination countries
- TVA sur la marge calculation for EU destinations
- Date calculations (deposit due, balance due, forex dates)
"""

import uuid
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.dossier import Dossier
from app.models.invoice import Invoice, InvoiceLine, InvoiceVatDetail, InvoicePaymentLink
from app.services.invoice_numbering import get_next_invoice_number


# ========================================================================
# VAT Configuration by destination
# ========================================================================

# Non-EU countries: VAT exempt (Art. 262-I du CGI)
NON_EU_EXEMPT_COUNTRIES = {
    "TH", "VN", "KH", "LA", "MM", "ID", "JP", "LK", "IN", "NP", "PH", "MY",
}

# EU countries: TVA sur la marge (Art. 266-1-c du CGI)
EU_MARGIN_COUNTRIES = {
    "ES", "IT", "PT", "GR", "HR", "FR",
}

VAT_EXEMPT_MENTION = "Exonération de TVA - Article 262-I du CGI (Prestations de services dont le lieu d'exécution est situé hors UE)"
VAT_MARGIN_MENTION = "TVA sur la marge - Article 266-1-c du CGI (Régime particulier des agences de voyage)"

# Default deposit percentage
DEFAULT_DEPOSIT_PCT = Decimal("30.00")


class InvoiceService:
    """Main service for invoice business logic."""

    # ================================================================
    # VAT Determination
    # ================================================================

    @staticmethod
    def determine_vat_regime(destination_countries: list[str] | None) -> dict:
        """
        Determine the VAT regime based on destination countries.

        Non-EU destinations → exempt (0%)
        EU destinations → margin (20%)
        Mixed → defaults to margin (conservative approach)

        Returns:
            {
                "regime": "exempt" | "margin",
                "rate": Decimal,
                "legal_mention": str,
            }
        """
        if not destination_countries:
            return {
                "regime": "exempt",
                "rate": Decimal("0.00"),
                "legal_mention": VAT_EXEMPT_MENTION,
            }

        countries = set(c.upper() for c in destination_countries)

        # If any EU country is in the destination, use margin regime
        if countries.intersection(EU_MARGIN_COUNTRIES):
            return {
                "regime": "margin",
                "rate": Decimal("20.00"),
                "legal_mention": VAT_MARGIN_MENTION,
            }

        return {
            "regime": "exempt",
            "rate": Decimal("0.00"),
            "legal_mention": VAT_EXEMPT_MENTION,
        }

    # ================================================================
    # VAT on Margin Calculation (internal)
    # ================================================================

    @staticmethod
    def calculate_vat_on_margin(
        selling_price_ttc: Decimal,
        cost_price_ht: Decimal,
        vat_rate: Decimal,
    ) -> dict:
        """
        Calculate TVA sur la marge (internal — not shown to client).

        Formula:
            Margin = Selling Price TTC - Cost HT
            VAT = Margin × (Rate / (100 + Rate))
            Margin HT = Margin - VAT

        Example:
            Selling: 2450€ TTC, Cost: 1800€ HT, Rate: 20%
            Margin TTC = 650€
            VAT = 650 × 20/120 = 108.33€
            Margin HT = 541.67€
        """
        margin_ttc = selling_price_ttc - cost_price_ht

        if vat_rate <= 0 or margin_ttc <= 0:
            return {
                "margin_ttc": margin_ttc,
                "margin_ht": margin_ttc,
                "vat_amount": Decimal("0.00"),
            }

        vat_amount = (margin_ttc * vat_rate / (Decimal("100") + vat_rate)).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        margin_ht = margin_ttc - vat_amount

        return {
            "margin_ttc": margin_ttc.quantize(Decimal("0.01")),
            "margin_ht": margin_ht.quantize(Decimal("0.01")),
            "vat_amount": vat_amount,
        }

    # ================================================================
    # Date Calculations
    # ================================================================

    @staticmethod
    def calculate_dates(
        issue_date: date,
        travel_start_date: date | None = None,
    ) -> dict:
        """
        Calculate standard dates for invoicing.

        Returns:
            {
                "deposit_due_date": issue_date + 10 days,
                "balance_due_date": travel_start - 30 days (or None),
                "forex_deposit_date": deposit_due + 10 days,
                "forex_balance_date": balance_due + 7 days (or None),
            }
        """
        deposit_due = issue_date + timedelta(days=10)

        balance_due = None
        forex_deposit_date = deposit_due + timedelta(days=10)
        forex_balance_date = None

        if travel_start_date:
            balance_due = travel_start_date - timedelta(days=30)
            # Ensure balance due isn't before deposit due
            if balance_due < deposit_due:
                balance_due = deposit_due
            forex_balance_date = balance_due + timedelta(days=7)

        return {
            "deposit_due_date": deposit_due,
            "balance_due_date": balance_due,
            "forex_deposit_date": forex_deposit_date,
            "forex_balance_date": forex_balance_date,
        }

    # ================================================================
    # Invoice Creation
    # ================================================================

    @staticmethod
    async def create_from_dossier(
        db: AsyncSession,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID,
        dossier_id: uuid.UUID,
        invoice_type: str,
        lines_data: list[dict] | None = None,
        total_ttc: Decimal | None = None,
        cost_ht: Decimal | None = None,
        deposit_pct: Decimal | None = None,
        notes: str | None = None,
        client_notes: str | None = None,
        # Dates d'échéance (optionnel — sinon calculées automatiquement)
        deposit_due_date: date | None = None,
        balance_due_date: date | None = None,
        # Réforme e-facture 2026
        client_siren: str | None = None,
        delivery_address_line1: str | None = None,
        delivery_address_city: str | None = None,
        delivery_address_postal_code: str | None = None,
        delivery_address_country: str | None = None,
        operation_category: str | None = "PS",
        # Pax / insured persons (for Chapka insurance)
        pax_count: int | None = None,
        pax_names: str | None = None,
        # Client override (when invoicing a specific participant instead of lead)
        client_name: str | None = None,
        client_email: str | None = None,
        client_phone: str | None = None,
        client_address: str | None = None,
    ) -> Invoice:
        """
        Create an invoice from a dossier.

        Steps:
        1. Load dossier with relationships
        2. Determine VAT regime from destination countries
        3. Allocate sequential number
        4. Calculate amounts (deposit, balance)
        5. Create invoice + lines + VAT details + payment links
        """
        # Block direct FA creation — FA is auto-generated when PRO is marked paid
        if invoice_type == "FA":
            raise ValueError(
                "Les factures sont générées automatiquement au paiement de la proforma. "
                "Créez une proforma (PRO) puis marquez-la comme payée."
            )

        # Validate deposit_pct (0-100)
        if deposit_pct is not None:
            if deposit_pct < Decimal("0") or deposit_pct > Decimal("100"):
                raise ValueError("Le taux d'acompte doit être compris entre 0 et 100%.")

        # 1. Load dossier
        result = await db.execute(
            select(Dossier)
            .where(Dossier.id == dossier_id, Dossier.tenant_id == tenant_id)
        )
        dossier = result.scalar_one_or_none()
        if not dossier:
            raise ValueError(f"Dossier not found: {dossier_id}")

        # 2. Determine VAT
        vat_info = InvoiceService.determine_vat_regime(dossier.destination_countries)

        # 3. Allocate number
        today = date.today()
        number, sequence = await get_next_invoice_number(db, tenant_id, invoice_type)

        # 4. Calculate amounts
        amount_ttc = total_ttc or Decimal("0.00")
        dep_pct = deposit_pct or DEFAULT_DEPOSIT_PCT
        deposit = (amount_ttc * dep_pct / Decimal("100")).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        balance = amount_ttc - deposit

        # Calculate dates (auto-calculated, then overridden if user provided custom dates)
        dates = InvoiceService.calculate_dates(
            today,
            dossier.departure_date_from,
        )

        # Override with user-provided dates if any
        if deposit_due_date:
            dates["deposit_due_date"] = deposit_due_date
        if balance_due_date:
            dates["balance_due_date"] = balance_due_date

        # Determine due date based on invoice type
        due_date = None
        if invoice_type == "PRO":
            due_date = dates["deposit_due_date"]
        elif invoice_type == "FA":
            due_date = dates["balance_due_date"] or dates["deposit_due_date"]
        elif invoice_type == "DEV":
            due_date = today + timedelta(days=30)  # Quote validity 30 days

        # 5. Create invoice
        invoice = Invoice(
            tenant_id=tenant_id,
            type=invoice_type,
            number=number,
            year=today.year,
            sequence=sequence,
            # References
            dossier_id=dossier_id,
            trip_id=dossier.selected_trip_id,
            cotation_id=dossier.selected_cotation_id,
            # Client snapshot (override if specific participant, fallback to dossier)
            client_type="individual",
            client_name=client_name or dossier.client_name,
            client_email=client_email or dossier.client_email,
            client_phone=client_phone or dossier.client_phone,
            client_company=dossier.client_company,
            client_address=client_address or dossier.client_address,
            client_siren=client_siren,
            # Delivery address (réforme 2026)
            delivery_address_line1=delivery_address_line1,
            delivery_address_city=delivery_address_city,
            delivery_address_postal_code=delivery_address_postal_code,
            delivery_address_country=delivery_address_country,
            # Dates
            issue_date=today,
            due_date=due_date,
            travel_start_date=dossier.departure_date_from,
            travel_end_date=dossier.departure_date_to,
            # Amounts
            total_ttc=amount_ttc,
            deposit_amount=deposit,
            deposit_pct=dep_pct,
            balance_amount=balance,
            currency=dossier.budget_currency or "EUR",
            # VAT
            vat_regime=vat_info["regime"],
            vat_rate=vat_info["rate"],
            vat_legal_mention=vat_info["legal_mention"],
            # Réforme e-facture 2026
            operation_category=operation_category or "PS",
            vat_on_debits=False,  # Agence de voyage = TVA sur encaissements
            electronic_format="facturx_basic",
            pa_transmission_status="draft",
            # Status
            status="draft",
            # Pax / insured persons
            pax_count=pax_count,
            pax_names=pax_names,
            # Meta
            notes=notes,
            client_notes=client_notes,
            created_by_id=user_id,
        )
        db.add(invoice)
        await db.flush()  # Get invoice.id

        # 6. Create lines
        if lines_data:
            for i, line_data in enumerate(lines_data):
                qty = Decimal(str(line_data.get("quantity", 1)))
                unit_price = Decimal(str(line_data["unit_price_ttc"]))
                line = InvoiceLine(
                    tenant_id=tenant_id,
                    invoice_id=invoice.id,
                    sort_order=i,
                    description=line_data["description"],
                    details=line_data.get("details"),
                    quantity=qty,
                    unit_price_ttc=unit_price,
                    total_ttc=(qty * unit_price).quantize(Decimal("0.01")),
                    line_type=line_data.get("line_type", "service"),
                )
                db.add(line)
        elif amount_ttc > 0:
            # Create a single line with the total amount
            pax_info = ""
            if dossier.pax_adults:
                pax_info = f" - {dossier.pax_adults} adulte{'s' if dossier.pax_adults > 1 else ''}"
                if dossier.pax_children:
                    pax_info += f", {dossier.pax_children} enfant{'s' if dossier.pax_children > 1 else ''}"

            line = InvoiceLine(
                tenant_id=tenant_id,
                invoice_id=invoice.id,
                sort_order=0,
                description=f"Forfait voyage{pax_info}",
                quantity=Decimal("1"),
                unit_price_ttc=amount_ttc,
                total_ttc=amount_ttc,
                line_type="service",
            )
            db.add(line)

        # 7. Create VAT details (internal) for margin regime
        if vat_info["regime"] == "margin" and cost_ht is not None and amount_ttc > 0:
            vat_calc = InvoiceService.calculate_vat_on_margin(
                amount_ttc, cost_ht, vat_info["rate"]
            )
            vat_detail = InvoiceVatDetail(
                tenant_id=tenant_id,
                invoice_id=invoice.id,
                selling_price_ttc=amount_ttc,
                cost_price_ht=cost_ht,
                margin_ttc=vat_calc["margin_ttc"],
                margin_ht=vat_calc["margin_ht"],
                vat_rate=vat_info["rate"],
                vat_amount=vat_calc["vat_amount"],
                period=today.strftime("%Y-%m"),
            )
            db.add(vat_detail)
            invoice.vat_amount = vat_calc["vat_amount"]
            invoice.total_ht = amount_ttc - vat_calc["vat_amount"]

        # 8. Create payment links
        if invoice_type == "PRO" and amount_ttc > 0:
            # Deposit payment link (acompte)
            pl_deposit = InvoicePaymentLink(
                tenant_id=tenant_id,
                invoice_id=invoice.id,
                payment_type="deposit",
                amount=deposit,
                due_date=dates["deposit_due_date"],
                status="pending",
            )
            db.add(pl_deposit)
            # Balance payment link (solde — pré-configuré pour Kantox)
            if balance > 0:
                pl_balance = InvoicePaymentLink(
                    tenant_id=tenant_id,
                    invoice_id=invoice.id,
                    payment_type="balance",
                    amount=balance,
                    due_date=dates["balance_due_date"] or dates["deposit_due_date"],
                    status="pending",
                )
                db.add(pl_balance)

        await db.commit()
        await db.refresh(invoice)

        return invoice

    # ================================================================
    # Workflow
    # ================================================================

    @staticmethod
    async def advance_workflow(
        db: AsyncSession,
        invoice: Invoice,
    ) -> Invoice | None:
        """
        Advance the invoice workflow:
        - DEV (draft/sent) → creates a new PRO

        Note: PRO → FA is handled automatically by mark_paid().
        FA cannot be created manually.

        Returns the newly created invoice, or None if no advancement possible.
        """
        if invoice.type == "DEV" and invoice.status in ("draft", "sent"):
            # DEV → PRO: create proforma with deposit amount
            new_invoice = await InvoiceService.create_from_dossier(
                db=db,
                tenant_id=invoice.tenant_id,
                user_id=invoice.created_by_id,
                dossier_id=invoice.dossier_id,
                invoice_type="PRO",
                total_ttc=invoice.total_ttc,
                deposit_pct=invoice.deposit_pct,
                notes=f"Proforma générée depuis le devis {invoice.number}",
            )
            new_invoice.parent_invoice_id = invoice.id
            await db.commit()
            return new_invoice

        return None

    # ================================================================
    # Auto-generate FA from PRO at payment
    # ================================================================

    @staticmethod
    async def _generate_fa_from_pro(
        db: AsyncSession,
        pro_invoice: Invoice,
    ) -> Invoice:
        """
        Auto-generate a FA (Facture) when a PRO is marked as paid.

        The FA number is allocated at this moment — guaranteeing no gaps
        in the definitive numbering sequence (legal requirement in France).

        The FA contains:
        - The balance amount (total_ttc - deposit_amount)
        - The balance due date from the PRO's payment links
        - All client/VAT/réforme 2026 info copied from the PRO
        """
        today = date.today()

        # 1. Allocate definitive FA number (atomic, no gaps)
        number, sequence = await get_next_invoice_number(
            db, pro_invoice.tenant_id, "FA"
        )

        # 2. Calculate balance amount
        balance = pro_invoice.balance_amount or (
            pro_invoice.total_ttc - (pro_invoice.deposit_amount or Decimal("0"))
        )

        # 3. Get balance due date from PRO's payment links
        balance_due_date = None
        result = await db.execute(
            select(InvoicePaymentLink)
            .where(
                InvoicePaymentLink.invoice_id == pro_invoice.id,
                InvoicePaymentLink.payment_type == "balance",
            )
        )
        balance_link = result.scalar_one_or_none()
        if balance_link:
            balance_due_date = balance_link.due_date

        if not balance_due_date:
            # Fallback: 30 days from now
            balance_due_date = today + timedelta(days=30)

        # 4. Create FA invoice
        fa_invoice = Invoice(
            tenant_id=pro_invoice.tenant_id,
            type="FA",
            number=number,
            year=today.year,
            sequence=sequence,
            # Parent reference
            parent_invoice_id=pro_invoice.id,
            # Dossier references
            dossier_id=pro_invoice.dossier_id,
            trip_id=pro_invoice.trip_id,
            cotation_id=pro_invoice.cotation_id,
            # Client snapshot (copy from PRO)
            client_type=pro_invoice.client_type,
            client_name=pro_invoice.client_name,
            client_email=pro_invoice.client_email,
            client_phone=pro_invoice.client_phone,
            client_company=pro_invoice.client_company,
            client_address=pro_invoice.client_address,
            client_siren=pro_invoice.client_siren,
            # Delivery address (réforme 2026)
            delivery_address_line1=pro_invoice.delivery_address_line1,
            delivery_address_city=pro_invoice.delivery_address_city,
            delivery_address_postal_code=pro_invoice.delivery_address_postal_code,
            delivery_address_country=pro_invoice.delivery_address_country,
            # Dates
            issue_date=today,
            due_date=balance_due_date,
            travel_start_date=pro_invoice.travel_start_date,
            travel_end_date=pro_invoice.travel_end_date,
            # Amounts (balance = solde restant)
            total_ttc=balance,
            deposit_amount=Decimal("0"),
            deposit_pct=Decimal("0"),
            balance_amount=balance,
            currency=pro_invoice.currency,
            # VAT (copy from PRO)
            vat_regime=pro_invoice.vat_regime,
            vat_rate=pro_invoice.vat_rate,
            vat_amount=Decimal("0"),
            vat_legal_mention=pro_invoice.vat_legal_mention,
            # Réforme e-facture 2026
            operation_category=pro_invoice.operation_category,
            vat_on_debits=pro_invoice.vat_on_debits,
            electronic_format=pro_invoice.electronic_format,
            pa_transmission_status="draft",
            # Status: draft for manual review before sending
            status="draft",
            # Meta
            notes=f"Facture solde générée automatiquement au paiement de la proforma {pro_invoice.number}",
            created_by_id=pro_invoice.created_by_id,
        )
        db.add(fa_invoice)
        await db.flush()  # Get fa_invoice.id

        # 5. Create a single line for the balance
        line = InvoiceLine(
            tenant_id=pro_invoice.tenant_id,
            invoice_id=fa_invoice.id,
            sort_order=0,
            description=f"Solde du voyage — Proforma {pro_invoice.number}",
            quantity=Decimal("1"),
            unit_price_ttc=balance,
            total_ttc=balance,
            line_type="service",
        )
        db.add(line)

        # 6. Create balance payment link
        pl_balance = InvoicePaymentLink(
            tenant_id=pro_invoice.tenant_id,
            invoice_id=fa_invoice.id,
            payment_type="balance",
            amount=balance,
            due_date=balance_due_date,
            status="pending",
        )
        db.add(pl_balance)

        return fa_invoice

    # ================================================================
    # Mark Paid (with auto FA generation for PRO)
    # ================================================================

    @staticmethod
    async def mark_paid(
        db: AsyncSession,
        invoice: Invoice,
        payment_data: dict | None = None,
    ) -> tuple[Invoice, Invoice | None]:
        """
        Mark an invoice as paid.

        If the invoice is a PRO, automatically generates a FA (Facture)
        with the balance amount and a definitive FA number.

        Returns:
            (paid_invoice, generated_fa_or_none)
        """
        from datetime import datetime

        payment_data = payment_data or {}
        now = datetime.utcnow()

        invoice.status = "paid"
        invoice.paid_at = now
        invoice.payment_method = payment_data.get("payment_method")
        invoice.payment_ref = payment_data.get("payment_ref")
        invoice.paid_amount = (
            Decimal(str(payment_data["paid_amount"]))
            if payment_data.get("paid_amount")
            else invoice.total_ttc
        )

        # Update payment links
        for pl in invoice.payment_links:
            if pl.status == "pending":
                pl.status = "paid"
                pl.paid_at = now
                pl.paid_amount = pl.amount
                pl.payment_method = payment_data.get("payment_method")
                pl.payment_ref = payment_data.get("payment_ref")

        # Auto-generate FA if this is a PRO
        generated_fa = None
        if invoice.type == "PRO":
            generated_fa = await InvoiceService._generate_fa_from_pro(db, invoice)

        await db.commit()
        if generated_fa:
            await db.refresh(generated_fa)

        return invoice, generated_fa

    # ================================================================
    # Credit Note
    # ================================================================

    @staticmethod
    async def create_credit_note(
        db: AsyncSession,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID,
        invoice_id: int,
        reason: str,
    ) -> Invoice:
        """
        Create an AV (Avoir / Credit Note) linked to an existing FA.
        The credit note has a negative amount matching the original invoice.
        """
        # Load original invoice
        result = await db.execute(
            select(Invoice)
            .where(Invoice.id == invoice_id, Invoice.tenant_id == tenant_id)
            .options(selectinload(Invoice.lines))
        )
        original = result.scalar_one_or_none()
        if not original:
            raise ValueError(f"Invoice not found: {invoice_id}")

        if original.type not in ("FA", "PRO"):
            raise ValueError("Credit notes can only be created from FA or PRO invoices")

        # Allocate number
        today = date.today()
        number, sequence = await get_next_invoice_number(db, tenant_id, "AV")

        # Create credit note (negative amounts)
        credit_note = Invoice(
            tenant_id=tenant_id,
            type="AV",
            number=number,
            year=today.year,
            sequence=sequence,
            parent_invoice_id=original.id,
            dossier_id=original.dossier_id,
            trip_id=original.trip_id,
            # Client (same as original)
            client_type=original.client_type,
            client_name=original.client_name,
            client_email=original.client_email,
            client_phone=original.client_phone,
            client_company=original.client_company,
            client_address=original.client_address,
            client_siren=original.client_siren,
            # Delivery address (same as original)
            delivery_address_line1=original.delivery_address_line1,
            delivery_address_city=original.delivery_address_city,
            delivery_address_postal_code=original.delivery_address_postal_code,
            delivery_address_country=original.delivery_address_country,
            # Dates
            issue_date=today,
            travel_start_date=original.travel_start_date,
            travel_end_date=original.travel_end_date,
            # Negative amounts
            total_ttc=-original.total_ttc,
            currency=original.currency,
            # VAT
            vat_regime=original.vat_regime,
            vat_rate=original.vat_rate,
            vat_amount=-original.vat_amount if original.vat_amount else Decimal("0"),
            vat_legal_mention=original.vat_legal_mention,
            # Réforme e-facture 2026
            operation_category=original.operation_category,
            vat_on_debits=original.vat_on_debits,
            electronic_format=original.electronic_format,
            pa_transmission_status="draft",
            # Status
            status="draft",
            cancellation_reason=reason,
            # Meta
            notes=f"Avoir pour la facture {original.number} — {reason}",
            created_by_id=user_id,
        )
        db.add(credit_note)
        await db.flush()

        # Copy lines with negative amounts
        for line in original.lines:
            credit_line = InvoiceLine(
                tenant_id=tenant_id,
                invoice_id=credit_note.id,
                sort_order=line.sort_order,
                description=line.description,
                details=line.details,
                quantity=line.quantity,
                unit_price_ttc=-line.unit_price_ttc,
                total_ttc=-line.total_ttc,
                line_type=line.line_type,
            )
            db.add(credit_line)

        # Cancel the original invoice
        original.status = "cancelled"
        original.cancelled_at = today
        original.cancellation_reason = reason

        await db.commit()
        await db.refresh(credit_note)

        return credit_note
