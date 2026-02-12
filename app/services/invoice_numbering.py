"""
Invoice numbering service — guarantees sequential, gap-free numbering.
French legal requirement: no gaps in invoice numbering.

Uses SELECT ... FOR UPDATE for atomic allocation.
Format: {TYPE}-{YEAR}-{XXXXX}  (e.g., FA-2026-00142)
"""

import uuid
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.invoice import InvoiceNumberSequence


async def get_next_invoice_number(
    db: AsyncSession,
    tenant_id: uuid.UUID,
    invoice_type: str,
    year: int | None = None,
) -> tuple[str, int]:
    """
    Atomically allocate the next invoice number.

    Uses SELECT ... FOR UPDATE to lock the sequence row,
    preventing concurrent allocations from creating gaps.

    Args:
        db: Database session (must be within a transaction)
        tenant_id: Tenant UUID
        invoice_type: One of "DEV", "PRO", "FA", "AV"
        year: Fiscal year (defaults to current year)

    Returns:
        (formatted_number, sequence) — e.g., ("FA-2026-00142", 142)
    """
    if year is None:
        year = date.today().year

    if invoice_type not in ("DEV", "PRO", "FA", "AV"):
        raise ValueError(f"Invalid invoice type: {invoice_type}")

    # Try to lock the existing sequence row
    result = await db.execute(
        select(InvoiceNumberSequence)
        .where(
            InvoiceNumberSequence.tenant_id == tenant_id,
            InvoiceNumberSequence.type == invoice_type,
            InvoiceNumberSequence.year == year,
        )
        .with_for_update()
    )
    seq = result.scalar_one_or_none()

    if seq is None:
        # First invoice of this type/year for this tenant — create sequence
        seq = InvoiceNumberSequence(
            tenant_id=tenant_id,
            type=invoice_type,
            year=year,
            last_sequence=0,
        )
        db.add(seq)
        await db.flush()  # Get the row in DB so FOR UPDATE works next time

    # Increment
    seq.last_sequence += 1
    next_seq = seq.last_sequence

    # Format: TYPE-YEAR-XXXXX
    formatted = f"{invoice_type}-{year}-{next_seq:05d}"

    return formatted, next_seq


async def validate_sequence_integrity(
    db: AsyncSession,
    tenant_id: uuid.UUID,
    invoice_type: str,
    year: int,
) -> tuple[bool, list[str]]:
    """
    Verify there are no gaps in the numbering for emitted invoices.
    Only checks non-draft invoices (drafts don't count for legal numbering).

    Returns:
        (is_valid, list of gap descriptions)
    """
    from app.models.invoice import Invoice

    result = await db.execute(
        select(Invoice.sequence)
        .where(
            Invoice.tenant_id == tenant_id,
            Invoice.type == invoice_type,
            Invoice.year == year,
            Invoice.status != "draft",
        )
        .order_by(Invoice.sequence)
    )
    sequences = [row[0] for row in result.all()]

    if not sequences:
        return True, []

    gaps = []
    expected = 1
    for seq in sequences:
        if seq != expected:
            gaps.append(f"Gap: expected {expected}, found {seq}")
            expected = seq + 1
        else:
            expected += 1

    return len(gaps) == 0, gaps
