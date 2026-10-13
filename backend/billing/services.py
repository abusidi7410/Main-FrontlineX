"""Shared wallet, entitlement and alert-billing logic.

All money movement funnels through `credit_wallet` / `debit_wallet`: short
atomic transactions, wallet row locked, balance check under the lock, ledger
row written in the same transaction. Callers never touch `Wallet.balance_kobo`
directly.

Lock order everywhere in this module: Student -> Wallet. Deposit paths lock
Wallet only. No external API calls inside a locked transaction.
"""
from __future__ import annotations

import secrets
from datetime import date, timedelta

from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError


class InsufficientFunds(ValidationError):
    """Raised when the wallet cannot cover a charge. Carries figures for the UI."""

    def __init__(self, required_kobo: int, available_kobo: int, what: str = 'charge'):
        self.required_kobo = required_kobo
        self.available_kobo = available_kobo
        super().__init__({
            'wallet': (
                f'Insufficient wallet balance for this {what}: '
                f'required ₦{required_kobo / 100:,.2f}, '
                f'available ₦{available_kobo / 100:,.2f}. Fund the wallet and try again.'
            ),
            'requiredKobo': required_kobo,
            'availableKobo': available_kobo,
        })


def _ref(prefix: str) -> str:
    return f'{prefix}-{secrets.token_hex(8).upper()}'


def get_pricing():
    from .models import PlatformPricing
    pricing, _ = PlatformPricing.objects.get_or_create(pk=1)
    return pricing


def get_wallet(school):
    from .models import Wallet
    wallet, _ = Wallet.objects.get_or_create(school=school)
    return wallet


def _period_days() -> int:
    from django.conf import settings
    return int(getattr(settings, 'SUBSCRIPTION_PERIOD_DAYS', 30))


def credit_wallet(
    school, amount_kobo: int, *, category: str, description: str = '',
    provider_reference: str = '', message_reference: str = '',
    student=None, created_by=None,
):
    """Add funds. Returns (wallet, transaction). Idempotent only via caller-side
    reference checks — see deposit confirmation, which looks up by reference."""
    from .models import Wallet, WalletTransaction
    if amount_kobo <= 0:
        raise ValidationError({'amount': 'Amount must be greater than zero.'})
    with transaction.atomic():
        try:
            wallet, _ = Wallet.objects.select_for_update(of=('self',)).get_or_create(
                school=school,
            )
        except IntegrityError:
            wallet = Wallet.objects.select_for_update(of=('self',)).get(school=school)
        before = wallet.balance_kobo
        wallet.balance_kobo = before + amount_kobo
        wallet.save(update_fields=['balance_kobo', 'updated_at'])
        entry = WalletTransaction.objects.create(
            school=school,
            reference=_ref('WTX'),
            direction=WalletTransaction.Direction.CREDIT,
            amount_kobo=amount_kobo,
            category=category,
            status=WalletTransaction.Status.SUCCESS,
            student=student,
            message_reference=message_reference or '',
            provider_reference=provider_reference or '',
            balance_before_kobo=before,
            balance_after_kobo=wallet.balance_kobo,
            description=description or '',
            created_by=created_by if getattr(created_by, 'school_id', None) else None,
        )
    return wallet, entry


def debit_wallet(
    school, amount_kobo: int, *, category: str, description: str = '',
    provider_reference: str = '', message_reference: str = '',
    student=None, created_by=None, what: str = 'charge',
):
    """Remove funds, refusing overdrafts. Raises InsufficientFunds."""
    from .models import Wallet, WalletTransaction
    if amount_kobo <= 0:
        raise ValidationError({'amount': 'Amount must be greater than zero.'})
    with transaction.atomic():
        try:
            wallet, _ = Wallet.objects.select_for_update(of=('self',)).get_or_create(
                school=school,
            )
        except IntegrityError:
            wallet = Wallet.objects.select_for_update(of=('self',)).get(school=school)
        if wallet.balance_kobo < amount_kobo:
            raise InsufficientFunds(amount_kobo, wallet.balance_kobo, what)
        before = wallet.balance_kobo
        wallet.balance_kobo = before - amount_kobo
        wallet.save(update_fields=['balance_kobo', 'updated_at'])
        entry = WalletTransaction.objects.create(
            school=school,
            reference=_ref('WTX'),
            direction=WalletTransaction.Direction.DEBIT,
            amount_kobo=amount_kobo,
            category=category,
            status=WalletTransaction.Status.SUCCESS,
            student=student,
            message_reference=message_reference or '',
            provider_reference=provider_reference or '',
            balance_before_kobo=before,
            balance_after_kobo=wallet.balance_kobo,
            description=description or '',
            created_by=created_by if getattr(created_by, 'school_id', None) else None,
        )
    return wallet, entry


def reverse_transaction(entry, *, reason: str = '', created_by=None):
    """Refund a settled debit with a linked credit. Original is marked reversed."""
    from .models import WalletTransaction
    if entry.direction != WalletTransaction.Direction.DEBIT:
        raise ValidationError({'transaction': 'Only debits can be refunded.'})
    if entry.status != WalletTransaction.Status.SUCCESS:
        raise ValidationError({'transaction': 'Only successful charges can be refunded.'})
    wallet, refund = credit_wallet(
        entry.school, entry.amount_kobo,
        category=WalletTransaction.Category.REFUND,
        description=f'Refund of {entry.reference}. {reason}'.strip(),
        student=entry.student,
        created_by=created_by,
    )
    entry.status = WalletTransaction.Status.REVERSED
    entry.save(update_fields=['status'])
    return wallet, refund


# ── Student entitlements ───────────────────────────────────────────────

def live_entitlement(student, on: date | None = None):
    """The entitlement covering `on` (default today), or None."""
    from .models import StudentEntitlement
    on = on or timezone.localdate()
    return StudentEntitlement.objects.filter(
        student=student, period_start__lte=on, period_end__gte=on,
    ).order_by('-period_end').first()


def entitlement_status(entitlement, *, grace_days: int, on: date | None = None) -> str:
    """Active | ExpiringSoon (≤3 days left) | GracePeriod | Expired."""
    on = on or timezone.localdate()
    if on <= entitlement.period_end:
        if (entitlement.period_end - on).days <= 3:
            return 'ExpiringSoon'
        return 'Active'
    if on <= entitlement.period_end + timedelta(days=grace_days):
        return 'GracePeriod'
    return 'Expired'


def activate_student(school, student, *, actor=None):
    """Charge the wallet and open a rolling monthly period, atomically.

    Returns (entitlement, created). Already-paid students return the existing
    entitlement with created=False and no charge. Raises InsufficientFunds
    without writing anything when the balance is short.
    """
    from records.models import Student

    from .models import StudentEntitlement
    if student.school_id != school.id:
        raise ValidationError({'student': 'That student belongs to another school.'})
    pricing = get_pricing()
    today = timezone.localdate()
    with transaction.atomic():
        # Lock order Student -> Wallet, always in this order.
        student = Student.objects.select_for_update(of=('self',)).get(pk=student.pk)
        existing = live_entitlement(student, today)
        if existing is not None:
            return existing, False
        wallet = _lock_wallet(school)
        if wallet.balance_kobo < pricing.student_price_kobo:
            raise InsufficientFunds(
                pricing.student_price_kobo, wallet.balance_kobo, 'student activation',
            )
        period_end = today + timedelta(days=_period_days())
        try:
            with transaction.atomic():
                entitlement = StudentEntitlement.objects.create(
                    student=student,
                    school=school,
                    period_start=today,
                    period_end=period_end,
                    amount_kobo=pricing.student_price_kobo,
                    created_by=actor if getattr(actor, 'school_id', None) else None,
                )
        except IntegrityError:
            # A concurrent activation won the same window: reuse it, no charge.
            existing = live_entitlement(student, today)
            if existing is None:  # pragma: no cover - defensive
                raise
            return existing, False
        before = wallet.balance_kobo
        wallet.balance_kobo = before - pricing.student_price_kobo
        wallet.save(update_fields=['balance_kobo', 'updated_at'])
        from .models import WalletTransaction
        entry = WalletTransaction.objects.create(
            school=school,
            reference=_ref('WTX'),
            direction=WalletTransaction.Direction.DEBIT,
            amount_kobo=pricing.student_price_kobo,
            category=WalletTransaction.Category.STUDENT_ACTIVATION,
            status=WalletTransaction.Status.SUCCESS,
            student=student,
            balance_before_kobo=before,
            balance_after_kobo=wallet.balance_kobo,
            description=(
                f'Student access activation for {student} '
                f'({today} – {period_end}).'
            ),
            created_by=actor if getattr(actor, 'school_id', None) else None,
        )
        entitlement.wallet_transaction = entry
        entitlement.save(update_fields=['wallet_transaction'])
    return entitlement, True


def _lock_wallet(school):
    from .models import Wallet
    try:
        wallet, _ = Wallet.objects.select_for_update(of=('self',)).get_or_create(
            school=school,
        )
    except IntegrityError:
        wallet = Wallet.objects.select_for_update(of=('self',)).get(school=school)
    return wallet


# ── Access enforcement ─────────────────────────────────────────────

class StudentAccessRequired(ValidationError):
    """Raised when a student feature is used for an unpaid student."""

    def __init__(self, student, required_kobo: int, available_kobo: int):
        name = f'{student.first_name} {student.last_name}'.strip() or 'This student'
        super().__init__({
            'student': (
                f'{name} has no active access. Activate them from Wallet & Billing '
                f'(₦{required_kobo / 100:,.2f}; wallet holds ₦{available_kobo / 100:,.2f}).'
            ),
            'reasonCode': 'student_access_required',
            'requiredKobo': required_kobo,
            'availableKobo': available_kobo,
        })


def student_has_access(student, on: date | None = None) -> bool:
    """True when the student may use paid features: a live entitlement, or one
    inside the grace window. Grace maintains temporary access by policy."""
    from .models import StudentEntitlement
    on = on or timezone.localdate()
    pricing = get_pricing()
    return StudentEntitlement.objects.filter(
        student=student,
        period_start__lte=on,
        period_end__gte=on - timedelta(days=pricing.grace_days),
    ).exists()


def students_with_access(student_ids, on: date | None = None) -> set:
    """Bulk version of `student_has_access`. One query for a whole roster."""
    from .models import StudentEntitlement
    on = on or timezone.localdate()
    pricing = get_pricing()
    if not pricing.enforce_student_access:
        return set(student_ids)
    return set(StudentEntitlement.objects.filter(
        student_id__in=list(student_ids),
        period_start__lte=on,
        period_end__gte=on - timedelta(days=pricing.grace_days),
    ).values_list('student_id', flat=True))


def check_student_access(student, on: date | None = None) -> None:
    """Block unpaid students from paid features. Staff unblock by activating
    (which debits the wallet). No-op when enforcement is switched off."""
    pricing = get_pricing()
    if not pricing.enforce_student_access:
        return
    if student_has_access(student, on):
        return
    wallet = get_wallet(student.school)
    raise StudentAccessRequired(student, pricing.student_price_kobo, wallet.balance_kobo)


def ensure_student_access(school, student, *, actor=None, on: date | None = None):
    """Auto-debit workflow: grant access, charging the wallet once if needed.

    Read paths must keep using `check_student_access` (viewing must never
    charge). Write paths (result recording, attendance, ...) call this so the
    first real use of a student in a billing period debits the configured
    `student_price_kobo` exactly once via `activate_student` (atomic +
    idempotent under concurrency). Returns (entitlement, created).
    Raises InsufficientFunds when the wallet cannot cover the charge, and
    StudentAccessRequired is never raised here — callers surface the
    InsufficientFunds message with a fund-the-wallet path instead.
    """
    pricing = get_pricing()
    if not pricing.enforce_student_access:
        return live_entitlement(student, on), False
    if student_has_access(student, on):
        return live_entitlement(student, on), False
    return activate_student(school, student, actor=actor)


def ensure_many_student_access(school, students, *, actor=None, on: date | None = None):
    """Batch auto-debit for whole-class operations (e.g. attendance submit).

    Same one-charge-per-student-per-period guarantee as `ensure_student_access`,
    but one wallet lock, one entitlement lookup, `bulk_create` writes and a
    single wallet UPDATE for the whole batch: ~6 queries for 60 students
    instead of ~420. Students are processed in the given order (callers pass
    roster order so partial funds cover the top of the visible list).

    Returns {'activated': [students charged now], 'already': [students with
    access], 'unfunded': [students skipped for lack of funds]}. Never raises
    InsufficientFunds: shortfall is reported, not thrown, so one broke wallet
    never blocks the rest of the register.
    """
    from .models import StudentEntitlement, WalletTransaction

    students = [s for s in students if s.school_id == school.id]
    if not students:
        return {'activated': [], 'already': [], 'unfunded': []}
    pricing = get_pricing()
    today = timezone.localdate()
    on = on or today
    if not pricing.enforce_student_access:
        return {'activated': [], 'already': list(students), 'unfunded': []}
    price = pricing.student_price_kobo
    grace = timedelta(days=pricing.grace_days)
    with transaction.atomic():
        wallet = _lock_wallet(school)
        covered_ids = set(StudentEntitlement.objects.filter(
            student_id__in=[s.id for s in students],
            period_start__lte=on,
            period_end__gte=on - grace,
        ).values_list('student_id', flat=True))
        activated, unfunded = [], []
        new_entitlements, new_entries = [], []
        balance = wallet.balance_kobo
        by = actor if getattr(actor, 'school_id', None) else None
        for student in students:
            if student.id in covered_ids:
                continue
            if balance < price:
                unfunded.append(student)
                continue
            period_end = today + timedelta(days=_period_days())
            try:
                with transaction.atomic():
                    entitlement = StudentEntitlement.objects.create(
                        student=student,
                        school=school,
                        period_start=today,
                        period_end=period_end,
                        amount_kobo=price,
                        created_by=by,
                    )
            except IntegrityError:
                # A concurrent activation won this window: reuse, no charge.
                covered_ids.add(student.id)
                continue
            before = balance
            balance -= price
            entry = WalletTransaction(
                school=school,
                reference=_ref('WTX'),
                direction=WalletTransaction.Direction.DEBIT,
                amount_kobo=price,
                category=WalletTransaction.Category.STUDENT_ACTIVATION,
                status=WalletTransaction.Status.SUCCESS,
                student=student,
                balance_before_kobo=before,
                balance_after_kobo=balance,
                description=(
                    f'Student access activation for {student} '
                    f'({today} – {period_end}).'
                ),
                created_by=by,
            )
            new_entitlements.append(entitlement)
            new_entries.append(entry)
            activated.append(student)
            covered_ids.add(student.id)
        if new_entries:
            WalletTransaction.objects.bulk_create(new_entries)
            for entitlement, entry in zip(new_entitlements, new_entries):
                entitlement.wallet_transaction = entry
            StudentEntitlement.objects.bulk_update(
                new_entitlements, ['wallet_transaction'],
            )
            wallet.balance_kobo = balance
            wallet.save(update_fields=['balance_kobo', 'updated_at'])
    already = [s for s in students if s.id in covered_ids and s not in activated]
    return {'activated': activated, 'already': already, 'unfunded': unfunded}


# ── SME alerts ─────────────────────────────────────────────────────────

class AlertBlocked(ValidationError):
    """Raised when an alert fails a control-gate check. Message is user-facing."""

    def __init__(self, message: str, code: str):
        self.code = code
        super().__init__({'alert': message, 'reasonCode': code})


def alert_gate(school) -> dict:
    """Evaluate the control chain. Returns flags; raises nothing."""
    from .models import SchoolMessaging
    pricing = get_pricing()
    messaging, _ = SchoolMessaging.objects.get_or_create(school=school)
    wallet = get_wallet(school)
    return {
        'globalEnabled': bool(pricing.sms_enabled_global),
        'platformBlocked': bool(messaging.platform_blocked),
        'schoolEnabled': bool(messaging.school_enabled),
        'balanceKobo': wallet.balance_kobo,
        'priceKobo': pricing.sms_price_kobo,
        'canSend': bool(
            pricing.sms_enabled_global
            and not messaging.platform_blocked
            and messaging.school_enabled
            and wallet.balance_kobo >= pricing.sms_price_kobo
        ),
    }


def _check_alert_gate(school) -> tuple:
    pricing = get_pricing()
    if not pricing.sms_enabled_global:
        raise AlertBlocked(
            'SME alerts are currently disabled for the whole platform.', 'global_disabled',
        )
    from .models import SchoolMessaging
    messaging, _ = SchoolMessaging.objects.get_or_create(school=school)
    if messaging.platform_blocked:
        raise AlertBlocked(
            'SME alerts are blocked for your school by the platform manager.',
            'school_blocked',
        )
    if not messaging.school_enabled:
        raise AlertBlocked(
            'SME alerts are switched off for your school. Switch them on to send.',
            'school_disabled',
        )
    return pricing, messaging


def request_alert(
    school, *, recipient: str, message: str, actor=None, reference: str = '',
):
    """Bill and send one SME alert. Retry-safe via the idempotency reference.

    Flow: gate checks → get_or_create SmsAlert by reference → debit wallet
    (reserve) → provider send OUTSIDE any transaction → settle or refund.
    A provider rejection (no billable event) refunds the customer charge.
    Provider cost is recorded only when the provider reports one, else null.
    """
    from records.services.sms import get_sms_provider

    from .models import SmsAlert
    pricing, _ = _check_alert_gate(school)
    recipient = (recipient or '').strip()
    message = (message or '').strip()
    if not recipient:
        raise ValidationError({'recipient': 'A recipient phone number is required.'})
    if not message:
        raise ValidationError({'message': 'Message text is required.'})
    if len(message) > 480:
        raise ValidationError({'message': 'Message is too long (480 characters max).'})
    reference = reference or _ref('SMS')

    with transaction.atomic():
        alert, created = SmsAlert.objects.get_or_create(
            school=school,
            reference=reference,
            defaults={
                'recipient': recipient,
                'message': message,
                'customer_kobo': pricing.sms_price_kobo,
                'created_by': actor if getattr(actor, 'school_id', None) else None,
            },
        )
        if not created and alert.status == SmsAlert.Status.SENT:
            return alert, False
        if not created and alert.status not in (
            SmsAlert.Status.PENDING, SmsAlert.Status.FAILED,
        ):
            raise ValidationError(
                {'reference': 'This alert reference was already used.'},
            )
        wallet = _lock_wallet(school)
        if wallet.balance_kobo < pricing.sms_price_kobo:
            raise InsufficientFunds(
                pricing.sms_price_kobo, wallet.balance_kobo, 'SME alert',
            )
        before = wallet.balance_kobo
        wallet.balance_kobo = before - pricing.sms_price_kobo
        wallet.save(update_fields=['balance_kobo', 'updated_at'])
        from .models import WalletTransaction
        entry = WalletTransaction.objects.create(
            school=school,
            reference=_ref('WTX'),
            direction=WalletTransaction.Direction.DEBIT,
            amount_kobo=pricing.sms_price_kobo,
            category=WalletTransaction.Category.SMS_ALERT,
            status=WalletTransaction.Status.SUCCESS,
            message_reference=alert.reference,
            balance_before_kobo=before,
            balance_after_kobo=wallet.balance_kobo,
            description=f'SME alert to {recipient}.',
            created_by=actor if getattr(actor, 'school_id', None) else None,
        )
        alert.wallet_transaction = entry
        alert.customer_kobo = pricing.sms_price_kobo
        alert.save(update_fields=['wallet_transaction', 'customer_kobo'])

    # Provider submission happens outside the transaction: a slow gateway must
    # never hold the wallet lock.
    try:
        provider = get_sms_provider()
        sender = getattr(__import__('django.conf', fromlist=['settings']).settings,
                         'TERMII_SENDER_ID', '') or 'SchoolOS'
        result = provider.send(to=recipient, message=message, sender_id=sender)
    except Exception as exc:  # provider client blew up: refund, record, report
        _refund_alert(alert, entry, f'Provider error: {exc}')
        raise ValidationError(
            {'alert': 'The message provider failed. The charge was refunded.'},
        ) from exc

    from records.models import UsageRecord
    if result.succeeded:
        alert.status = SmsAlert.Status.SENT
        alert.provider_reference = result.provider_reference or ''
        # Termii reports no per-message cost: record unknown (null), never invent.
        alert.provider_cost_kobo = (result.cost or None) if result.cost else None
        alert.save(update_fields=[
            'status', 'provider_reference', 'provider_cost_kobo',
        ])
        UsageRecord.objects.create(
            school=school,
            resource_type=UsageRecord.ResourceType.SMS,
            action_type='payment_notification',
            quantity=1,
            provider='termii' if 'console' not in (result.provider_reference or '') else 'console',
            provider_reference=result.provider_reference or '',
            estimated_cost=pricing.sms_price_kobo,
            actual_cost=result.cost or 0,
            status=UsageRecord.Status.SUCCEEDED,
        )
        return alert, created

    # Rejected: no billable event occurred, so the customer is refunded.
    _refund_alert(alert, entry, result.error or 'Provider rejected the request')
    UsageRecord.objects.create(
        school=school,
        resource_type=UsageRecord.ResourceType.SMS,
        action_type='payment_notification',
        quantity=1,
        provider='termii',
        provider_reference='',
        estimated_cost=pricing.sms_price_kobo,
        actual_cost=0,
        status=UsageRecord.Status.FAILED,
    )
    raise ValidationError(
        {'alert': f'The provider rejected this message ({result.error}). The charge was refunded.'},
    )


def _refund_alert(alert, entry, error: str):
    from .models import SmsAlert
    _, refund = reverse_transaction(entry, reason='Provider did not accept the alert.')
    alert.status = SmsAlert.Status.REFUNDED
    alert.provider_error = str(error)[:255]
    alert.save(update_fields=['status', 'provider_error'])
    return refund
