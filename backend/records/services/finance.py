"""Payment recording, trusted verification and invoice recalculation.

The trusted flow (spec §16)::

    Frontend → payment reference → Backend → provider verification / webhook
             → payment marked VERIFIED → invoice recalculated
             → approval + enrollment when eligible

A client can never mark a payment successful by sending `payment_status:
success`; only :func:`apply_verified_payment` — reached from a provider
verification or a trusted webhook — promotes a payment to VERIFIED.

External provider calls happen *outside* the database transaction (spec §18),
and every write path is idempotent under retries and concurrent callbacks
(spec §17, §48).
"""
from __future__ import annotations

import secrets
from decimal import Decimal

from django.db import IntegrityError, transaction
from rest_framework.exceptions import ValidationError

from . import billing
from . import clearance
from ..models import Enrollment, Invoice, Payment, Registration

# Statuses that no longer represent money the school holds.
NON_COUNTING_STATUSES = frozenset({
    Payment.Status.PENDING,
    Payment.Status.FAILED,
    Payment.Status.CANCELLED,
    Payment.Status.REVERSED,
    Payment.Status.REFUNDED,
})


def generate_reference(prefix: str = 'PAY') -> str:
    return f'{prefix}-{secrets.token_hex(8).upper()}'


def _now():
    from django.utils import timezone
    return timezone.now()


def record_payment(
    *,
    invoice: Invoice,
    amount: Decimal,
    method: str,
    recorded_by=None,
    reference: str = '',
    provider_reference: str | None = None,
    provider: str = '',
    note: str = '',
    verified: bool = False,
    verified_by=None,
    is_migration_data: bool = False,
    payment_date=None,
) -> Payment:
    """Record a payment against an invoice (spec §13).

    `verified=True` is only ever set by a trusted path — an administrator
    confirming cash/POS at the bursar, or a provider confirmation. Self-service
    payments are recorded PENDING regardless of what the client claims.
    """
    amount = Decimal(amount)
    if amount <= 0:
        raise ValidationError({'amount': 'Amount must be greater than zero.'})
    if invoice.is_cancelled:
        raise ValidationError({'invoice': 'This invoice has been cancelled.'})

    with transaction.atomic():
        invoice = Invoice.objects.select_for_update().get(pk=invoice.pk)
        billing.assert_payment_within_outstanding(invoice, amount)
        try:
            return Payment.objects.create(
                school=invoice.school,
                invoice=invoice,
                amount=amount,
                method=method,
                status=Payment.Status.VERIFIED if verified else Payment.Status.PENDING,
                reference=reference or generate_reference(),
                provider=provider,
                provider_reference=provider_reference or None,
                is_migration_data=is_migration_data,
                payment_date=payment_date,
                recorded_by=recorded_by if getattr(recorded_by, 'school_id', None) else None,
                verified_by=verified_by if getattr(verified_by, 'school_id', None) else None,
                verified_at=_now() if verified else None,
                note=note,
            )
        except IntegrityError as exc:
            raise ValidationError({
                'reference': 'A payment with this reference already exists.',
            }) from exc


def find_payment_by_provider_reference(provider_reference: str):
    """Look up a payment the provider already told us about (spec §17)."""
    if not provider_reference:
        return None
    return Payment.objects.filter(provider_reference=provider_reference).first()


def apply_verified_payment(
    payment: Payment,
    *,
    actor=None,
    provider_reference: str | None = None,
) -> dict:
    """Promote a payment to VERIFIED and run the downstream consequences.

    Runs entirely inside one short transaction (spec §47):

    1. payment → VERIFIED
    2. invoice recalculated (derived, never a client number)
    3. registration auto-approved when the invoice is now fully paid
    4. enrollment activated when the registration was approved

    Already-verified payments return the same result without double-counting,
    which is what makes a replayed webhook safe (spec §17, §48).
    """
    from . import enrollment as enrollment_service

    with transaction.atomic():
        payment = Payment.objects.select_for_update().select_related(
            'invoice', 'invoice__student',
        ).get(pk=payment.pk)

        if payment.status in (
            Payment.Status.REVERSED, Payment.Status.REFUNDED,
            Payment.Status.CANCELLED, Payment.Status.FAILED,
        ):
            raise ValidationError({
                'payment': f'A {payment.status} payment cannot be verified.',
            })

        if provider_reference and payment.provider_reference != provider_reference:
            payment.provider_reference = provider_reference

        if payment.status != Payment.Status.VERIFIED:
            # Re-check under the invoice lock: another payment may have landed
            # between recording and verification and consumed the balance.
            invoice_locked = Invoice.objects.select_for_update().get(pk=payment.invoice_id)
            already_paid = billing.verified_paid_total(invoice_locked.id)
            outstanding = Decimal(invoice_locked.total) - already_paid
            if payment.amount > outstanding:
                raise ValidationError({
                    'amount': (
                        f'Amount exceeds the outstanding balance of {outstanding:,.2f}.'
                    ),
                })
            payment.status = Payment.Status.VERIFIED
            payment.verified_at = _now()
            payment.verified_by = actor if getattr(actor, 'school_id', None) else None
            payment.save(update_fields=[
                'status', 'verified_at', 'verified_by', 'provider_reference',
            ])

        invoice = payment.invoice
        invoice.refresh_from_db()
        outcome = {
            'payment': payment,
            'invoice': invoice,
            'registration': None,
            'enrollment': None,
            'autoApproved': False,
            'awaitingFullSettlement': False,
        }

        if invoice.status != 'paid':
            return outcome

        registration = (
            Registration.objects
            .filter(invoice=invoice, status=Registration.Status.PENDING)
            .select_related('student', 'academic_session', 'intended_class', 'intended_section',
                            'school')
            .first()
        )
        if registration is None:
            return outcome

        # The school's own clearance policy decides whether this payment is
        # enough. Under full settlement a registration fee on its own clears
        # nothing; under the default policy the registration charge stands in
        # for the whole invoice. Either way payment still only *allows* the
        # enrollment - it never creates one by itself.
        if not clearance.is_invoice_cleared(
            invoice,
            requires_full_settlement=registration.school.activation_requires_full_settlement,
        ):
            outcome['awaitingFullSettlement'] = True
            return outcome

        # Full payment auto-approves a *valid pending* registration only. A
        # rejected/cancelled registration is an administrative decision and is
        # never silently overridden by a payment callback (spec §34).
        active = enrollment_service.activate_enrollment(
            student=registration.student,
            academic_session=registration.academic_session,
            class_obj=registration.intended_class,
            section=registration.intended_section,
            source=Enrollment.ActivationSource.FULL_PAYMENT,
            actor=actor,
        )
        registration.status = Registration.Status.APPROVED
        registration.approved_at = _now()
        registration.decision_reason = 'Automatically approved on full payment.'
        registration.save(update_fields=[
            'status', 'approved_at', 'decision_reason', 'updated_at',
        ])
        enrollment_service.sync_student_class_mirror(registration.student, active)

        outcome['registration'] = registration
        outcome['enrollment'] = active
        outcome['autoApproved'] = True
        return outcome


def reverse_payment(payment: Payment, *, actor=None, reason: str = '') -> dict:
    """Reverse a verified payment and correct the invoice (spec §43).

    Returns a result dict with the updated `payment`, the re-derived `invoice`
    and, when applicable, the `enrollment` that was flagged for review. The
    reversed payment stops counting toward the verified total and the invoice
    status is re-derived, so an invoice never stays PAID on reversed money.
    """
    from . import enrollment as enrollment_service

    with transaction.atomic():
        payment = Payment.objects.select_for_update().select_related(
            'invoice', 'invoice__student',
        ).get(pk=payment.pk)
        if payment.status != Payment.Status.VERIFIED:
            raise ValidationError({
                'payment': 'Only verified payments can be reversed.',
            })

        payment.status = Payment.Status.REVERSED
        payment.reversal_reason = reason[:255]
        payment.verified_at = None
        payment.save(update_fields=['status', 'reversal_reason', 'verified_at'])

        invoice = payment.invoice
        invoice.refresh_from_db()

        # A full-payment activation that is no longer backed by verified money
        # keeps the student enrolled but goes on the administrator's desk
        # (§44). Enrollment history is never rewritten here.
        flagged = None
        registration = (
            Registration.objects
            .filter(invoice=invoice)
            .select_related('student', 'academic_session')
            .order_by('-approved_at')
            .first()
        )
        if registration is not None:
            active = enrollment_service.get_active_enrollment(
                registration.student, registration.academic_session,
            )
            if active is not None and billing.verified_paid_total(invoice.id) < Decimal(invoice.total):
                enrollment_service.flag_enrollment_for_review(
                    active,
                    'Payment reversed after enrollment was activated — review required.',
                )
                flagged = active

        return {'payment': payment, 'invoice': invoice, 'enrollment': flagged}
