"""Receipt issuance: numbering, immutable snapshots, void and reprint.

The money is *already* recorded and verified by the payments workflow; issuing a
receipt never changes a payment, an invoice balance or the wallet. It only
stamps a numbered, immutable document for the payment that exists.
"""
from __future__ import annotations

from decimal import Decimal

from django.db import DatabaseError, transaction
from django.utils import timezone
from rest_framework import status as http_status
from rest_framework.exceptions import ValidationError

from records.models import Invoice, Payment
from records.services import admission as admission_service
from records.services import billing as billing_service

from .amounts import amount_in_words
from .models import Receipt, ReceiptSequence, ReceiptSettings

SERIAL_WIDTH = 6


class ReceiptConflict(ValidationError):
    """A live receipt already exists for this payment (HTTP 409)."""

    status_code = http_status.HTTP_409_CONFLICT

    def __init__(self, receipt):
        super().__init__({
            'detail': (
                f'Receipt {receipt.receipt_number} has already been issued for '
                'this payment. Void it first if a replacement is required.'
            ),
            'receiptId': str(receipt.public_id),
            'receiptNumber': receipt.receipt_number,
        })
        self.receipt = receipt


def get_settings(school) -> ReceiptSettings:
    settings_obj, _ = ReceiptSettings.objects.get_or_create(school=school)
    return settings_obj


def _clean_prefix(value: str) -> str:
    prefix = ''.join(ch for ch in (value or '').upper() if ch.isalnum())
    return (prefix or 'RCPT')[:10]


def _lock_sequence(school, year: int) -> ReceiptSequence:
    try:
        with transaction.atomic():
            sequence, _ = ReceiptSequence.objects.get_or_create(
                school=school, year=year, defaults={'last_serial': 0},
            )
    except DatabaseError:
        sequence = ReceiptSequence.objects.get(school=school, year=year)
    return ReceiptSequence.objects.select_for_update().get(pk=sequence.pk)


def _next_number(school, year: int) -> str:
    code = admission_service.resolve_school_code(school)
    prefix = _clean_prefix(get_settings(school).prefix)
    sequence = _lock_sequence(school, year)
    sequence.last_serial += 1
    sequence.save(update_fields=['last_serial'])
    return f'{code}/{prefix}/{year}/{sequence.last_serial:0{SERIAL_WIDTH}d}'


def _purpose(invoice: Invoice) -> str:
    if invoice.source == Invoice.Source.ADMISSION:
        return 'Registration fee'
    term = (invoice.term or '').strip()
    return f'{term} school fees' if term else 'School fees'


def _school_snapshot(school, settings_obj: ReceiptSettings) -> dict:
    address = ', '.join(
        part for part in (school.address, school.lga, school.state) if part
    )
    return {
        'name': school.name,
        'code': school.code,
        'address': address,
        'phone': school.phone,
        'email': school.email,
        'logo': school.logo.name if (school.logo and settings_obj.show_logo) else '',
        'primaryColor': school.primary_color,
        'secondaryColor': school.secondary_color,
        'footerNote': settings_obj.footer_note,
        'paperSize': settings_obj.paper_size,
    }


def _payment_snapshot(payment: Payment) -> dict:
    return {
        'method': payment.get_method_display(),
        'reference': payment.reference,
        'providerReference': payment.provider_reference or '',
        'provider': payment.provider or '',
        'paymentDate': payment.payment_date.isoformat() if payment.payment_date else '',
        'verifiedAt': payment.verified_at.isoformat() if payment.verified_at else '',
        'verifiedBy': (
            payment.verified_by.get_full_name() if payment.verified_by else ''
        ),
        'recordedBy': (
            payment.recorded_by.get_full_name() if payment.recorded_by else ''
        ),
        'note': payment.note or '',
    }


def _invoice_snapshot(invoice: Invoice, balance_after: Decimal) -> dict:
    return {
        'id': str(invoice.pk),
        'term': invoice.term or '',
        'source': invoice.source,
        'session': invoice.academic_session.name if invoice.academic_session_id else '',
        'total': str(invoice.total),
        'paid': str(Decimal(invoice.total) - balance_after),
        'balanceAfter': str(balance_after),
        'items': [
            {
                'label': str(item.get('label') or ''),
                'amount': str(item.get('amount') or ''),
            }
            for item in (invoice.items or [])
            if isinstance(item, dict)
        ],
    }


def _student_snapshot(student) -> dict:
    return {
        'id': str(student.public_id),
        'name': f'{student.first_name} {student.last_name}'.strip(),
        'firstName': student.first_name,
        'lastName': student.last_name,
        'admissionNumber': student.admission_number,
        'className': student.class_name,
        'arm': student.arm,
        'guardianName': student.guardian_name,
        'guardianPhone': student.guardian_phone,
    }


def issue_receipt(payment: Payment, *, actor=None, replace: bool = False):
    """Issue the official receipt for a verified payment.

    Locks the payment row, re-checks its status and the existing live receipt
    under that lock, then allocates the next number. Two simultaneous clicks
    therefore cannot produce two receipts for one payment.
    """
    with transaction.atomic():
        payment = (
            Payment.objects.select_for_update()
            .select_related(
                'school', 'invoice__student', 'invoice__academic_session',
                'verified_by', 'recorded_by',
            )
            .get(pk=payment.pk)
        )
        if payment.status != Payment.Status.VERIFIED:
            raise ValidationError({
                'detail': 'Only a verified payment can be receipted.',
            })

        existing = (
            Receipt.objects.select_for_update()
            .filter(payment=payment, status=Receipt.Status.ISSUED)
            .first()
        )
        if existing is not None:
            if not replace:
                raise ReceiptConflict(existing)
            existing.status = Receipt.Status.VOIDED
            existing.voided_by = actor if getattr(actor, 'school_id', None) else None
            existing.voided_at = timezone.now()
            existing.void_reason = 'Voided and replaced by a corrected receipt.'
            existing.save(update_fields=[
                'status', 'voided_by', 'voided_at', 'void_reason',
            ])

        invoice = payment.invoice
        student = invoice.student
        paid = billing_service.verified_paid_total(invoice.pk)
        balance_after = max(Decimal(invoice.total) - paid, Decimal('0'))
        amount = Decimal(payment.amount)
        year = timezone.localtime().year
        receipt_settings = get_settings(payment.school)
        number = _next_number(payment.school, year)
        payer_name = (student.guardian_name or '').strip() or (
            f'{student.first_name} {student.last_name}'.strip()
        )

        receipt = Receipt.objects.create(
            school=payment.school,
            payment=payment,
            receipt_number=number,
            payer_name=payer_name[:200],
            amount=amount,
            amount_in_words=amount_in_words(amount),
            purpose=_purpose(invoice),
            balance_after=balance_after,
            school_snapshot=_school_snapshot(payment.school, receipt_settings),
            student_snapshot=_student_snapshot(student),
            invoice_snapshot=_invoice_snapshot(invoice, balance_after),
            payment_snapshot=_payment_snapshot(payment),
            issued_by=actor if getattr(actor, 'school_id', None) else None,
            replaces=existing if existing is not None else None,
        )
    return receipt


def reprint_receipt(receipt: Receipt, *, actor=None) -> Receipt:
    receipt.reprint_count += 1
    receipt.last_reprinted_at = timezone.now()
    receipt.last_reprinted_by = actor if getattr(actor, 'school_id', None) else None
    receipt.save(update_fields=[
        'reprint_count', 'last_reprinted_at', 'last_reprinted_by',
    ])
    return receipt


def void_receipt(receipt: Receipt, *, reason: str, actor=None) -> Receipt:
    if receipt.status == Receipt.Status.VOIDED:
        raise ValidationError({'detail': 'This receipt is already void.'})
    reason = (reason or '').strip()
    if not reason:
        raise ValidationError({'reason': 'Give a reason for voiding this receipt.'})
    receipt.status = Receipt.Status.VOIDED
    receipt.voided_by = actor if getattr(actor, 'school_id', None) else None
    receipt.voided_at = timezone.now()
    receipt.void_reason = reason[:255]
    receipt.save(update_fields=['status', 'voided_by', 'voided_at', 'void_reason'])
    return receipt
