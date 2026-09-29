"""Payment Structure resolution and automatic invoice generation (spec §5–§12).

An administrator configures ``FeeStructure`` rows; invoices are *always*
calculated from them. Nobody types an invoice total.

Fee resolution precedence (spec §6)::

    class-specific  →  level-specific  →  school/session default

For one fee type the most specific active row wins. `FeeStructure` is keyed by
a `scope` + `scope_key` pair, so a fee type can only resolve to exactly one row
per scope — the class row simply shadows the level row, which shadows the
session default.

Historical integrity (spec §8): the resolved rows are copied into
``Invoice.items`` as an immutable snapshot, and ``Invoice.total`` is the sum of
that snapshot. Later edits to the Payment Structure never rewrite an invoice
that already exists.
"""
from __future__ import annotations

import datetime
from decimal import Decimal

from django.db.models import Sum
from django.db.models.functions import Coalesce
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from ..models import (
    AcademicSession,
    FeeStructure,
    Invoice,
    Level,
    Payment,
    SchoolClass,
    invoice_item_amount,
)

# Scope precedence, most specific first (spec §6).
SCOPE_PRECEDENCE = (
    FeeStructure.Scope.CLASS,
    FeeStructure.Scope.LEVEL,
    FeeStructure.Scope.SCHOOL,
)


def _decimal(value) -> Decimal:
    return value if isinstance(value, Decimal) else Decimal(str(value or 0))


def resolve_fee_structure(
    school,
    session: AcademicSession,
    school_class: SchoolClass | None = None,
    term: str = '',
) -> list[FeeStructure]:
    """Active fee rows that apply to a class in a session, most specific first.

    A fee defined only at class scope does not also apply to the whole level;
    each fee type resolves once, to the most specific row that defines it.
    """
    term = (term or '').strip()
    level: Level | None = school_class.level if school_class is not None else None
    queryset = FeeStructure.objects.filter(
        school=school,
        academic_session=session,
        is_active=True,
    )
    rows = [
        row for row in queryset
        if row.applies_to(term=term, school_class=school_class, level=level)
    ]

    resolved: list[FeeStructure] = []
    seen_fee_types: set[str] = set()
    for scope in SCOPE_PRECEDENCE:
        for row in rows:
            if row.scope != scope or row.fee_type in seen_fee_types:
                continue
            if not row.is_required:
                continue
            seen_fee_types.add(row.fee_type)
            resolved.append(row)
    return resolved


def build_invoice_snapshot(rows: list[FeeStructure]) -> tuple[list[dict], Decimal]:
    """Freeze fee rows into invoice line items plus their total.

    Amounts are normalised to strings so the JSON snapshot round-trips exactly
    and historical totals never depend on float formatting.
    """
    items = [
        {
            'feeStructureId': row.id,
            'feeType': row.fee_type,
            'label': row.label,
            'amount': str(_decimal(row.amount)),
            'scope': row.scope,
            'scopeKey': row.scope_key,
            'term': row.term,
            'isRequired': row.is_required,
        }
        for row in rows
    ]
    total = sum((invoice_item_amount(item) for item in items), Decimal('0'))
    return items, total


def snapshot_total(invoice: Invoice) -> Decimal:
    """An invoice's total is always its own snapshot, never today's fees."""
    if isinstance(invoice, Invoice):
        return _decimal(invoice.total)
    return sum((invoice_item_amount(item) for item in invoice or []), Decimal('0'))


def verified_paid_total(invoice_id: int) -> Decimal:
    """Sum of payments in the VERIFIED state only (spec §10, §14)."""
    return Payment.objects.filter(
        invoice_id=invoice_id, status=Payment.Status.VERIFIED,
    ).aggregate(total=Coalesce(Sum('amount'), Decimal('0')))['total']


def annotate_verified_paid(queryset):
    """Attach `verified_paid_total` so list endpoints avoid N+1 aggregates."""
    return queryset.annotate(
        verified_paid_total=Coalesce(
            Sum(
                'payments__amount',
                filter={'payments__status': Payment.Status.VERIFIED},
            ),
            Decimal('0'),
        ),
    )


def create_invoice_for_student(
    *,
    school,
    student,
    session: AcademicSession,
    school_class: SchoolClass | None = None,
    term: str = '',
    source: str = Invoice.Source.ADMISSION,
    due_date=None,
    items: list[dict] | None = None,
    total: Decimal | None = None,
) -> Invoice:
    """Create one invoice, snapshotting the applicable Payment Structure.

    `items`/`total` are only supplied by the migration workflow, which is
    bringing in the school's own historical figures rather than re-deriving
    them from today's fee configuration.
    """
    term = (term or '').strip()
    if items is None:
        rows = resolve_fee_structure(school, session, school_class, term)
        items, computed_total = build_invoice_snapshot(rows)
    else:
        items = [dict(item) for item in items]
        computed_total = snapshot_total(items)
    if total is not None:
        computed_total = _decimal(total)

    invoice, created = Invoice.objects.get_or_create(
        student=student,
        academic_session=session,
        term=term,
        defaults={
            'school': school,
            'source': source,
            'items': items,
            'total': computed_total,
            'due_date': due_date,
        },
    )
    return invoice


def assert_payment_within_outstanding(invoice: Invoice, amount: Decimal) -> None:
    """Reject a payment that would exceed the outstanding balance (spec §12).

    The project has no student-credit/advance mechanism, so overpayment is
    refused rather than silently creating money the ledger cannot represent.
    """
    outstanding = _decimal(invoice.total) - verified_paid_total(invoice.id)
    if amount > outstanding:
        raise ValidationError({
            'amount': (
                f'Amount exceeds the outstanding balance of '
                f'{outstanding:,.2f}.'
            ),
        })


def default_due_date(session: AcademicSession, *, days: int = 30):
    """A 30-day due date from issue, so OVERDUE is meaningful (§11)."""
    return timezone.now().date() + datetime.timedelta(days=days) if days else None
