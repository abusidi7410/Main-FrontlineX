"""One definition of "what does this student still owe?".

Three separate numbers can apply to an invoice:

    total           the snapshot of the fees assessed
    discount_total   the sum of active discounts / scholarships / waivers
    verified_paid    money that has actually cleared

Everything in the product — payment guards, financial clearance, activation,
the class Fee Collection dashboard, a student's statement and the receipts'
opening balance — must agree on:

    outstanding = max(total - discount_total - verified_paid, 0)

Keeping that expression in one module is what stops the discount from being
applied in one screen and forgotten in another.
"""
from __future__ import annotations

from decimal import Decimal

from ..models import FeeAdjustment, Invoice, Payment


def _zero() -> Decimal:
    return Decimal('0')


def invoice_discount_total(invoice: Invoice) -> Decimal:
    """The invoice's own denormalised discount figure."""
    return Decimal(invoice.discount_total or 0)


def invoice_net_total(invoice: Invoice) -> Decimal:
    """Payable amount on this invoice after adjustments."""
    return max(Decimal(invoice.total or 0) - invoice_discount_total(invoice), _zero())


def invoice_outstanding(invoice: Invoice, verified_paid: Decimal | None = None) -> Decimal:
    """Amount still owed on this invoice, from verified money only.

    `verified_paid` may be supplied by a caller that already annotated or
    aggregated it, so a list screen does not pay for one query per row.
    """
    if verified_paid is None:
        verified_paid = invoice.verified_paid
    return max(invoice_net_total(invoice) - Decimal(verified_paid or 0), _zero())


def adjustment_amount_total(adjustments) -> Decimal:
    total = _zero()
    for adjustment in adjustments:
        total += Decimal(adjustment.amount or 0)
    return total


def active_adjustments_for_invoice(invoice: Invoice):
    """Active adjustments that reduce this invoice's obligation."""
    return FeeAdjustment.objects.filter(
        school_id=invoice.school_id,
        student_id=invoice.student_id,
        academic_session_id=invoice.academic_session_id,
        term=invoice.term or '',
        is_active=True,
    )


def recompute_invoice_discount(invoice: Invoice) -> Decimal:
    """Re-derive `discount_total` from the active adjustments and persist it.

    The demormalised column is never incremented or decremented in place: it is
    always rebuilt from the rows that justify it, so it cannot drift.
    """
    from django.db.models import Sum

    total = (
        active_adjustments_for_invoice(invoice)
        .aggregate(total=Sum('amount'))['total']
        or _zero()
    )
    if Decimal(invoice.discount_total or 0) != Decimal(total):
        invoice.discount_total = total
        invoice.save(update_fields=['discount_total', 'updated_at'])
    return Decimal(total)


def student_outstanding(student) -> Decimal:
    """Total still owed across every live invoice, from verified payments."""
    from django.db.models import Q, Sum
    from django.db.models.functions import Coalesce

    invoices = Invoice.objects.filter(
        school_id=student.school_id, student=student, is_cancelled=False,
    ).annotate(
        verified_paid_total=Coalesce(
            Sum(
                'payments__amount',
                filter=Q(payments__status=Payment.Status.VERIFIED),
            ),
            _zero(),
        ),
    )
    outstanding = _zero()
    for invoice in invoices:
        outstanding += invoice_outstanding(invoice, invoice.verified_paid_total)
    return outstanding
