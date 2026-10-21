"""Discounts, scholarships and waivers applied to a student's assessment.

An adjustment never edits the invoice snapshot: it records *why* a family owes
less, who authorised it, and when. The invoice's ``discount_total`` is then
rebuilt from the active rows (see :mod:`records.services.balances`), which is
what the payment guards, clearance and the collection screens read.

Every write is audited because reducing a fee is a privileged, reviewable act.
"""
from __future__ import annotations

from decimal import Decimal

from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from ..models import FeeAdjustment, FeeStructure, Invoice, Student
from . import balances

VALID_FEE_TYPES = set(FeeStructure.FeeType.values)


def _invoice_for(*, school, student, academic_session, term) -> Invoice | None:
    return (
        Invoice.objects.select_for_update()
        .filter(
            school_id=school.id,
            student_id=student.id,
            academic_session_id=getattr(academic_session, 'id', None),
            term=(term or ''),
            is_cancelled=False,
        )
        .first()
    )


def active_total(invoice: Invoice) -> Decimal:
    from django.db.models import Sum

    return (
        balances.active_adjustments_for_invoice(invoice)
        .aggregate(total=Sum('amount'))['total']
        or Decimal('0')
    )


def create_adjustment(
    *,
    school,
    student: Student,
    academic_session,
    term: str = '',
    fee_type: str = '',
    kind: str,
    amount,
    reason: str = '',
    actor=None,
):
    """Grant a discount/scholarship/waiver against one assessment.

    The assessment (invoice) must already exist — fees are waived against a
    specific bill, not against an intention to bill — and the running total may
    not exceed the amount originally assessed, so an invoice can never go
    negative.
    """
    if student.school_id != school.id:
        raise ValidationError({'studentId': 'That student is not in this school.'})
    if kind not in FeeAdjustment.Kind.values:
        raise ValidationError({'kind': 'Choose discount, scholarship or waiver.'})
    fee_type = (fee_type or '').strip()
    if fee_type and fee_type not in VALID_FEE_TYPES:
        raise ValidationError({'feeType': f'"{fee_type}" is not a valid fee category.'})
    try:
        amount = Decimal(str(amount))
    except (TypeError, ValueError, ArithmeticError):
        raise ValidationError({'amount': 'Enter a valid amount.'})
    if amount <= 0:
        raise ValidationError({'amount': 'Amount must be greater than zero.'})

    with transaction.atomic():
        invoice = _invoice_for(
            school=school, student=student,
            academic_session=academic_session, term=term,
        )
        if invoice is None:
            raise ValidationError({
                'term': (
                    'No fee assessment exists for this student in that session and '
                    'term. Generate the assessment first.'
                ),
            })
        already = active_total(invoice)
        if already + amount > Decimal(invoice.total or 0):
            remaining = max(Decimal(invoice.total or 0) - already, Decimal('0'))
            raise ValidationError({
                'amount': (
                    f'Adjustments would exceed the assessed fee. '
                    f'You can still reduce by {remaining:,.2f}.'
                ),
            })
        adjustment = FeeAdjustment.objects.create(
            school=school,
            student=student,
            academic_session=academic_session,
            term=(term or ''),
            fee_type=fee_type,
            kind=kind,
            amount=amount,
            reason=(reason or '').strip()[:255],
            is_active=True,
            created_by=actor if getattr(actor, 'school_id', None) else None,
            approved_by=actor if getattr(actor, 'school_id', None) else None,
            approved_at=timezone.now(),
        )
        balances.recompute_invoice_discount(invoice)
    return adjustment


def revoke_adjustment(adjustment: FeeAdjustment, *, actor=None, reason: str = '') -> FeeAdjustment:
    """Reverse an adjustment; the invoice's discount is rebuilt from the rest."""
    if not adjustment.is_active:
        raise ValidationError({'detail': 'This adjustment has already been revoked.'})
    with transaction.atomic():
        adjustment.is_active = False
        adjustment.revoked_by = actor if getattr(actor, 'school_id', None) else None
        adjustment.revoked_at = timezone.now()
        adjustment.revoke_reason = (reason or '').strip()[:255]
        adjustment.save(update_fields=[
            'is_active', 'revoked_by', 'revoked_at', 'revoke_reason', 'updated_at',
        ])
        invoice = Invoice.objects.filter(
            school_id=adjustment.school_id,
            student_id=adjustment.student_id,
            academic_session_id=adjustment.academic_session_id,
            term=adjustment.term or '',
            is_cancelled=False,
        ).first()
        if invoice is not None:
            balances.recompute_invoice_discount(invoice)
    return adjustment
