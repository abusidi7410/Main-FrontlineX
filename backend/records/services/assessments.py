"""Fee assessments: issuing a class's bills and reading a student's statement.

An *assessment* is the invoice a class is billed for a session and term. This
module owns the two operations the fee-tracking screens need:

* :func:`assess_class` — issue (or refresh) the term's bills for one class, and
* :func:`student_statement` — everything a family owes, was granted and paid.

It never invents an amount: every figure is resolved from the Payment Structure
and frozen into the invoice snapshot, exactly as the rest of the finance app
does.
"""
from __future__ import annotations

from decimal import Decimal

from django.db import transaction
from rest_framework.exceptions import ValidationError

from ..models import (
    AcademicSession,
    FeeAdjustment,
    FeeStructure,
    Invoice,
    Payment,
    Student,
    invoice_item_amount,
)
from . import balances, billing as billing_service


def _term_invoices(*, school, academic_session, term):
    return Invoice.objects.filter(
        school_id=school.id,
        academic_session=academic_session,
        term=(term or ''),
        is_cancelled=False,
    )


def assess_class(
    *,
    school,
    academic_session: AcademicSession,
    class_name: str,
    term: str,
    due_date=None,
    overwrite: bool = False,
    actor=None,
) -> dict:
    """Issue one class's term bills, idempotently.

    A student is charged at most once per session and term: an existing live
    assessment is left untouched (or refreshed in place when ``overwrite``), so
    running the assessment twice can never double-bill. The registration fee is
    excluded — it is a one-time admission charge billed through its own flow.
    """
    class_name = (class_name or '').strip()
    term = (term or '').strip()
    if not class_name:
        raise ValidationError({'className': 'Select a class to assess.'})
    if not term:
        raise ValidationError({'term': 'A term is required (e.g. First Term).'})
    if academic_session is None:
        raise ValidationError({'academicSessionId': 'Select an academic session.'})

    items = billing_service.resolve_invoice_items(
        school=school,
        class_name=class_name,
        session=academic_session,
        term=term,
        exclude_fee_types={FeeStructure.FeeType.REGISTRATION},
    )
    if not items:
        raise ValidationError({
            'className': (
                f'No fee structure is set up for {class_name}. Add one before assessing.'
            ),
        })
    total = sum((invoice_item_amount(item) for item in items), Decimal('0'))
    snapshot_due = billing_service.snapshot_due_date(items)
    if due_date is None and snapshot_due is not None:
        from django.utils.dateparse import parse_date

        due_date = parse_date(snapshot_due)
    if due_date is None:
        due_date = billing_service.default_due_date(academic_session)

    students = Student.objects.filter(
        school_id=school.id, class_name=class_name, status=Student.Status.ACTIVE,
    )
    roster = dict(students.order_by('id').values_list('id', 'admission_number'))
    existing = {
        invoice.student_id: invoice
        for invoice in _term_invoices(
            school=school, academic_session=academic_session, term=term,
        ).filter(student_id__in=list(roster))
    }
    generated = updated = 0
    to_create = []
    with transaction.atomic():
        for student_id, admission_number in roster.items():
            invoice = existing.get(student_id)
            if invoice is not None:
                if overwrite:
                    from . import policy as policy_service

                    policy_service.assert_invoice_rewritable(
                        invoice, f'Invoice for {admission_number} ({term})',
                    )
                    invoice.items = items
                    invoice.total = total
                    if invoice.due_date is None:
                        invoice.due_date = due_date
                    invoice.save(update_fields=['items', 'total', 'due_date'])
                    updated += 1
                continue
            to_create.append(Invoice(
                school_id=school.id,
                student_id=student_id,
                academic_session=academic_session,
                term=term,
                source=Invoice.Source.BULK,
                total=total,
                discount_total=Decimal('0'),
                paid=Decimal('0'),
                items=items,
                due_date=due_date,
            ))
        if to_create:
            Invoice.objects.bulk_create(to_create)
            generated = len(to_create)
    return {
        'generated': generated,
        'updated': updated,
        'totalStudents': len(roster),
        'term': term,
        'className': class_name,
        'total': total,
    }


def _payment_dict(payment: Payment) -> dict:
    return {
        'invoiceId': str(payment.invoice_id),
        'id': str(payment.pk),
        'amount': str(payment.amount),
        'method': payment.get_method_display(),
        'status': payment.status,
        'reference': payment.reference,
        'date': payment.created_at.date().isoformat() if payment.created_at else '',
        'verifiedAt': payment.verified_at.isoformat() if payment.verified_at else '',
        'recordedBy': payment.recorded_by.get_full_name() if payment.recorded_by else '',
        'note': payment.note or '',
    }


def student_statement(*, school, student: Student, academic_session=None) -> dict:
    """A student's full fee position: assessed, adjusted, paid, outstanding.

    Read entirely from persisted rows — the snapshot on each invoice, the active
    adjustments and the verified payments — so the statement can never disagree
    with the collection dashboard.
    """
    invoices = (
        Invoice.objects
        .filter(school_id=school.id, student_id=student.id, is_cancelled=False)
        .select_related('academic_session')
        .order_by('created_at', 'id')
    )
    if academic_session is not None:
        invoices = invoices.filter(academic_session=academic_session)
    invoices = list(invoices)

    adjustments = FeeAdjustment.objects.filter(
        school_id=school.id, student_id=student.id, is_active=True,
    ).select_related('approved_by', 'created_by')
    if academic_session is not None:
        adjustments = adjustments.filter(academic_session=academic_session)
    adjustments = list(adjustments)

    payments = (
        Payment.objects
        .filter(
            school_id=school.id,
            invoice_id__in=[invoice.id for invoice in invoices] or [-1],
        )
        .select_related('recorded_by', 'verified_by')
        .order_by('-created_at', '-id')
    )

    assessed = discounts = paid = outstanding = Decimal('0')
    assessments = []
    for invoice in invoices:
        verified = invoice.verified_paid
        inv_outstanding = balances.invoice_outstanding(invoice, verified)
        assessed += Decimal(invoice.total or 0)
        discounts += Decimal(invoice.discount_total or 0)
        paid += verified
        outstanding += inv_outstanding
        assessments.append({
            'invoiceId': str(invoice.pk),
            'sessionId': str(invoice.academic_session_id or ''),
            'session': invoice.academic_session.name if invoice.academic_session_id else '',
            'term': invoice.term or '',
            'source': invoice.source,
            'status': invoice.status,
            'dueDate': invoice.due_date.isoformat() if invoice.due_date else '',
            'total': str(invoice.total),
            'discountTotal': str(invoice.discount_total or 0),
            'netTotal': str(invoice.net_total),
            'paid': str(verified),
            'outstanding': str(inv_outstanding),
            'items': [
                {
                    'label': str(item.get('label') or ''),
                    'feeType': str(item.get('feeType') or ''),
                    'amount': str(invoice_item_amount(item)),
                    'dueDate': str(item.get('dueDate') or ''),
                    'isRequired': bool(item.get('isRequired', True)),
                }
                for item in (invoice.items or [])
                if isinstance(item, dict)
            ],
        })

    return {
        'student': {
            'id': str(student.public_id),
            'admissionNumber': student.admission_number,
            'name': f'{student.first_name} {student.last_name}'.strip(),
            'className': student.class_name,
            'arm': student.arm,
            'status': student.status,
            'guardianName': student.guardian_name,
            'guardianPhone': student.guardian_phone,
        },
        'sessionId': str(academic_session.id) if academic_session is not None else '',
        'session': academic_session.name if academic_session is not None else '',
        'totals': {
            'assessed': str(assessed),
            'discounts': str(discounts),
            'paid': str(paid),
            'outstanding': str(outstanding),
        },
        'assessments': assessments,
        'adjustments': [
            {
                'id': str(adjustment.pk),
                'kind': adjustment.kind,
                'feeType': adjustment.fee_type,
                'amount': str(adjustment.amount),
                'reason': adjustment.reason,
                'approvedBy': (
                    adjustment.approved_by.get_full_name() if adjustment.approved_by else ''
                ),
                'approvedAt': (
                    adjustment.approved_at.isoformat() if adjustment.approved_at else ''
                ),
                'createdAt': adjustment.created_at.isoformat(),
            }
            for adjustment in adjustments
        ],
        'payments': [_payment_dict(payment) for payment in payments],
    }
