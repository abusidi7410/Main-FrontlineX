"""Class-based fee collection views of the ledger.

Answers the two questions a bursar's dashboard asks:

* *How much has this class brought in, and how much is still owed?* — the
  per-class summary and the school-wide totals.
* *Which pupils in this class are behind?* — the per-student drilldown.

Everything is aggregated in Python from a single annotated invoice queryset
rather than with SQL ``SUM`` over a joined payment table, because summing an
invoice column across a ``payments`` join multiplies each invoice by its number
of payments. Correctness beats one fewer loop at these row counts.
"""
from __future__ import annotations

from decimal import Decimal

from ..models import Invoice, Payment
from . import balances, billing as billing_service


def _base_invoices(*, school, academic_session, term, class_name=''):
    """Live invoices for a session, optionally narrowed by term and class."""
    qs = (
        Invoice.objects
        .filter(school_id=school.id, is_cancelled=False)
        .select_related('student')
        .order_by('student__class_name', 'student__admission_number', 'id')
    )
    if academic_session is not None:
        qs = qs.filter(academic_session=academic_session)
    if term is not None:
        qs = qs.filter(term=(term or '').strip())
    if class_name:
        qs = qs.filter(student__class_name=class_name)
    return billing_service.annotate_verified_paid(qs)


def _summarise(invoices) -> dict:
    assessed = discounts = paid = outstanding = Decimal('0')
    for invoice in invoices:
        verified = invoice.verified_paid
        assessed += Decimal(invoice.total or 0)
        discounts += Decimal(invoice.discount_total or 0)
        paid += verified
        outstanding += balances.invoice_outstanding(invoice, verified)
    return {
        'assessed': assessed,
        'discounts': discounts,
        'paid': paid,
        'outstanding': outstanding,
    }


def collection_overview(*, school, academic_session, term=None, class_name='') -> dict:
    """School-wide (or one class's) fee position, with a per-class breakdown."""
    invoices = list(_base_invoices(
        school=school, academic_session=academic_session,
        term=term, class_name=class_name,
    ))

    by_class: dict[str, dict] = {}
    status_counts = {'paid': 0, 'partially_paid': 0, 'unpaid': 0, 'overdue': 0}
    seen_students: set[int] = set()
    for invoice in invoices:
        key = invoice.student.class_name or '—'
        bucket = by_class.setdefault(key, {
            'className': key,
            'studentIds': set(),
            'assessed': Decimal('0'),
            'discounts': Decimal('0'),
            'paid': Decimal('0'),
            'outstanding': Decimal('0'),
            'invoices': 0,
            'overdue': 0,
        })
        verified = invoice.verified_paid
        inv_out = balances.invoice_outstanding(invoice, verified)
        bucket['studentIds'].add(invoice.student_id)
        bucket['assessed'] += Decimal(invoice.total or 0)
        bucket['discounts'] += Decimal(invoice.discount_total or 0)
        bucket['paid'] += verified
        bucket['outstanding'] += inv_out
        bucket['invoices'] += 1
        status = invoice.status
        if status == 'overdue':
            bucket['overdue'] += 1
        status_counts[status] = status_counts.get(status, 0) + 1
        seen_students.add(invoice.student_id)

    classes = []
    for bucket in by_class.values():
        assessed = bucket['assessed']
        collected_pct = (
            float(bucket['paid'] / assessed * 100) if assessed > 0 else 0.0
        )
        classes.append({
            'className': bucket['className'],
            'students': len(bucket['studentIds']),
            'assessed': str(bucket['assessed']),
            'discounts': str(bucket['discounts']),
            'paid': str(bucket['paid']),
            'outstanding': str(bucket['outstanding']),
            'overdueInvoices': bucket['overdue'],
            'collectionRate': round(collected_pct, 1),
        })
    classes.sort(key=lambda row: row['className'])

    totals = _summarise(invoices)
    return {
        'sessionId': str(academic_session.id) if academic_session is not None else '',
        'session': academic_session.name if academic_session is not None else '',
        'term': term,
        'totals': {
            'assessed': str(totals['assessed']),
            'discounts': str(totals['discounts']),
            'paid': str(totals['paid']),
            'outstanding': str(totals['outstanding']),
            'students': len(seen_students),
            'invoices': len(invoices),
        },
        'statusCounts': status_counts,
        'classes': classes,
    }


def class_fee_rows(*, school, academic_session, term, class_name: str) -> dict:
    """One row per pupil in a class: assessed, discounted, paid, due, status."""
    invoices = list(_base_invoices(
        school=school, academic_session=academic_session,
        term=term, class_name=class_name,
    ))
    by_student: dict[int, dict] = {}
    for invoice in invoices:
        row = by_student.setdefault(invoice.student_id, {
            'studentId': str(invoice.student.public_id),
            'admissionNumber': invoice.student.admission_number,
            'name': f'{invoice.student.first_name} {invoice.student.last_name}'.strip(),
            'className': invoice.student.class_name,
            'arm': invoice.student.arm,
            'status': invoice.student.status,
            'assessed': Decimal('0'),
            'discounts': Decimal('0'),
            'paid': Decimal('0'),
            'outstanding': Decimal('0'),
            'invoices': 0,
            'overdue': False,
            'dueDate': '',
            'lastPaymentDate': '',
        })
        verified = invoice.verified_paid
        row['assessed'] += Decimal(invoice.total or 0)
        row['discounts'] += Decimal(invoice.discount_total or 0)
        row['paid'] += verified
        row['outstanding'] += balances.invoice_outstanding(invoice, verified)
        row['invoices'] += 1
        if invoice.status == 'overdue':
            row['overdue'] = True
        if invoice.due_date:
            due = invoice.due_date.isoformat()
            if not row['dueDate'] or due < row['dueDate']:
                row['dueDate'] = due

    from django.db.models import Max

    payment_query = (
        Payment.objects
        .filter(
            school_id=school.id,
            status=Payment.Status.VERIFIED,
            invoice__student_id__in=list(by_student),
        )
        .values('invoice__student_id')
        .annotate(latest=Max('created_at'))
    )
    if academic_session is not None:
        payment_query = payment_query.filter(invoice__academic_session=academic_session)
    last_payment = {
        entry['invoice__student_id']: entry['latest'] for entry in payment_query
    }

    out = []
    for student_id, row in by_student.items():
        latest = last_payment.get(student_id)
        row['lastPaymentDate'] = latest.date().isoformat() if latest else ''
        row['assessed'] = str(row['assessed'])
        row['discounts'] = str(row['discounts'])
        row['paid'] = str(row['paid'])
        row['outstanding'] = str(row['outstanding'])
        out.append(row)
    out.sort(key=lambda item: item['admissionNumber'])
    totals = _summarise(invoices)
    return {
        'className': class_name,
        'term': term,
        'sessionId': str(academic_session.id) if academic_session is not None else '',
        'session': academic_session.name if academic_session is not None else '',
        'totals': {
            'assessed': str(totals['assessed']),
            'discounts': str(totals['discounts']),
            'paid': str(totals['paid']),
            'outstanding': str(totals['outstanding']),
            'students': len(by_student),
        },
        'students': out,
    }
