"""Financial clearance: has this student paid enough to join a class?

The rule the bursar configures lives on `School.activation_requires_full_settlement`:

* ``False`` - paying the **registration fee** is enough. This is the common
  Nigerian school arrangement: the admission charge is settled up front and
  tuition is arranged with the family afterwards.
* ``True`` - the **whole required fee** must be settled first.

Payment on its own never makes a student an active class member. The chain is::

    Payment -> Financial clearance -> Enrollment -> ACTIVE

so this module answers "is this student cleared?" and
:mod:`records.services.finance` uses that answer to decide whether it may
approve a registration and activate an enrollment.

Amounts are always read from *verified* payments (see
:mod:`records.services.finance`), so a pending or reversed payment never clears
a student, and the answers are derived from the database rather than from any
number a client sent.
"""
from __future__ import annotations

from decimal import Decimal

from . import billing
from ..models import Enrollment, Invoice, Registration, Student


def _zero() -> Decimal:
    return Decimal('0')


def invoice_registration_fee(invoice: Invoice) -> Decimal:
    """Sum of the invoice's required registration-fee lines."""
    from ..models import FeeStructure

    return sum(
        (
            billing.invoice_item_amount(item)
            for item in invoice.items or []
            if item.get('feeType') == FeeStructure.FeeType.REGISTRATION
            and item.get('isRequired', True)
        ),
        _zero(),
    )


def invoice_required_total(invoice: Invoice) -> Decimal:
    """Sum of every required fee line on the invoice."""
    return sum(
        (
            billing.invoice_item_amount(item)
            for item in invoice.items or []
            if item.get('isRequired', True)
        ),
        _zero(),
    )


def outstanding_against(invoice: Invoice, required_only: bool) -> Decimal:
    """Money still owed on the lines the clearance policy cares about.

    `required_only=False` means the whole invoice counts, which is what the
    strict full-settlement policy needs; the lax policy only looks at the
    registration lines.
    """
    total = invoice_required_total(invoice) if required_only else billing.snapshot_total(invoice)
    return max(total - billing.verified_paid_total(invoice.id), _zero())


def is_invoice_cleared(invoice: Invoice, *, requires_full_settlement: bool) -> bool:
    """Whether this invoice satisfies the school's clearance policy."""
    if invoice.is_cancelled:
        return False
    if requires_full_settlement:
        return outstanding_against(invoice, required_only=False) <= 0
    registration = invoice_registration_fee(invoice)
    if registration <= 0:
        # A school that does not charge a registration fee cannot gate on one.
        # Fall back to the whole invoice rather than clearing everyone free.
        return outstanding_against(invoice, required_only=False) <= 0
    paid = billing.verified_paid_total(invoice.id)
    return paid >= registration


def financial_clearance(student: Student) -> dict:
    """The student's current financial position, from verified money only.

    Returns the outstanding balance, the policy in force and whether the student
    is cleared. Used by the bursary screens and the AI assistant so both quote
    the same numbers.
    """
    school = student.school
    invoices = (
        Invoice.objects
        .filter(school=school, student=student, is_cancelled=False)
        .exclude(status=Invoice.Status.PAID)
        .order_by('-created_at')
    )
    requires_full = school.activation_requires_full_settlement
    outstanding = sum(
        (outstanding_against(invoice, required_only=requires_full) for invoice in invoices),
        _zero(),
    )
    cleared = not invoices.exists() or all(
        is_invoice_cleared(invoice, requires_full_settlement=requires_full)
        for invoice in invoices
    )
    return {
        'student': student,
        'requiresFullSettlement': requires_full,
        'outstanding': outstanding,
        'cleared': cleared,
        'invoices': list(invoices),
    }


def is_student_cleared(student: Student) -> bool:
    return financial_clearance(student)['cleared']


def pending_clearance_registrations(school, academic_session=None) -> list[Registration]:
    """Registrations that are approved financially but have no enrollment yet.

    This is the queue an administrator works through when a family pays
    partially and the school waives the remainder, or when a student is
    registered before any fees were configured.
    """
    queryset = Registration.objects.filter(
        school=school, status=Registration.Status.PENDING,
    ).select_related('student', 'academic_session', 'intended_class', 'intended_section')
    if academic_session is not None:
        queryset = queryset.filter(academic_session=academic_session)
    return [
        registration for registration in queryset
        if registration.invoice_id is None
        or is_invoice_cleared(
            registration.invoice, requires_full_settlement=school.activation_requires_full_settlement,
        )
    ]


def has_active_enrollment(student: Student, academic_session) -> bool:
    """The gate payment must not bypass: a roster row still has to exist."""
    return Enrollment.objects.filter(
        student=student,
        academic_session=academic_session,
        status=Enrollment.Status.ACTIVE,
    ).exists()
