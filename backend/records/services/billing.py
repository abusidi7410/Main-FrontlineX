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
    Student,
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


# ── The live Payment Structure (School.fee_structure) ──────────────────────
#
# There are two fee representations in this schema. The relational
# `FeeStructure` table is the spec model and everything above reads it, but
# nothing in the app writes it: the admin editor at `FeeStructureView` persists
# to `School.fee_structure` (JSON), so that is what a real school has rows in.
# Invoicing therefore has to resolve the JSON too, and both the bulk generator
# and admission use these two helpers so the rules cannot drift apart.


def school_fee_items(school, class_name: str = '') -> list[dict]:
    """Fee items from `School.fee_structure` that apply to a class.

    A row applies when its className is the wildcard or the class itself.
    Amounts become strings so the invoice snapshot round-trips exactly, the
    same way relational snapshots do.
    """
    class_name = (class_name or '').strip()
    items = []
    for row in school.fee_structure or []:
        scope = str(row.get('className', '*') or '*')
        if scope not in ('*', class_name):
            continue
        items.append({
            'label': str(row.get('label') or ''),
            'amount': str(_decimal(row.get('amount'))),
            'className': scope,
            'scope': 'school',
        })
    return items


def create_invoice_from_school_fees(
    *,
    school,
    student,
    term: str = '',
    due_date=None,
    source: str = Invoice.Source.ADMISSION,
) -> Invoice | None:
    """Issue a student's admission invoice from the school's configured fees.

    Returns None when the school has not configured any applicable fee, which
    is the normal state of a brand new school. Registration must still succeed
    in that case: the student simply stays PENDING_PAYMENT until fees are set
    and an invoice is raised, so nobody is locked out of enrolling a first
    student.
    """
    items = school_fee_items(school, student.class_name)
    if not items:
        return None
    total = sum((invoice_item_amount(item) for item in items), Decimal('0'))
    if total <= 0:
        return None
    invoice, _created = Invoice.objects.get_or_create(
        school=school,
        student=student,
        term=(term or '').strip(),
        defaults={
            'source': source,
            'items': items,
            'total': total,
            'due_date': due_date,
        },
    )
    return invoice


def live_invoices(student) -> list[Invoice]:
    """Invoices that actually still demand money (cancelled ones do not)."""
    return list(Invoice.objects.filter(
        school_id=student.school_id, student=student, is_cancelled=False,
    ))


def student_has_outstanding_balance(student) -> Decimal:
    """Unpaid money owed across a student's live invoices.

    Verified payments count against the total, so a pending payment does not
    make a student look paid (spec §10).
    """
    outstanding = Decimal('0')
    for invoice in live_invoices(student):
        outstanding += _decimal(invoice.total) - verified_paid_total(invoice.id)
    return max(outstanding, Decimal('0'))


def activate_student_if_fully_paid(student) -> bool:
    """Clear a PENDING_PAYMENT student once their invoice is settled.

    Requires at least one live invoice. "Nothing outstanding" is ambiguous when
    a student was never billed at all - a school with no fee structure yet
    registers students who legitimately have zero invoices - and treating that
    as settled would activate every one of them for free. Only ever promotes a
    student forward, so a school that later suspends somebody for unrelated
    reasons cannot have them silently reactivated by a stray payment.
    """
    if student.status != Student.Status.PENDING_PAYMENT:
        return False
    invoices = live_invoices(student)
    if not invoices:
        return False
    if student_has_outstanding_balance(student) > 0:
        return False
    student.status = Student.Status.ACTIVE
    student.save(update_fields=['status'])
    return True


def invoice_pending_students(school) -> int:
    """Raise the missing admission invoice for students registered before fees.

    A school can register its first students before anyone has set up the
    Payment Structure, and those students are then PENDING_PAYMENT with no
    invoice. The bulk generator only bills active students, so nothing else
    would ever invoice them and they could never be activated. Called when the
    fee structure is saved to close that gap. Returns how many were invoiced.
    """
    created = 0
    pending = Student.objects.filter(
        school=school, status=Student.Status.PENDING_PAYMENT,
    ).order_by('id')
    for student in pending:
        if live_invoices(student):
            continue
        if create_invoice_from_school_fees(school=school, student=student) is not None:
            created += 1
    return created
