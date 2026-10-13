"""School-facing wallet & billing endpoints.

Every financial action re-checks school scope, role permission and balance on
the server. The frontend never decides amounts: prices come from
PlatformPricing, debits happen inside `billing.services`.
"""
from __future__ import annotations

import json

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import User
from accounts.permissions import HasSchool, require_permissions
from accounts.utils import audit, paginate
from records.models import Student
from schools import paystack as paystack_client

from . import services
from .models import (
    SchoolMessaging,
    SmsAlert,
    StudentEntitlement,
    WalletDeposit,
    WalletTransaction,
)
from .serializers import (
    SmsAlertSerializer,
    StudentAccessSerializer,
    WalletTransactionSerializer,
)


def _wallet_payload(school) -> dict:
    wallet = services.get_wallet(school)
    pricing = services.get_pricing()
    gate = services.alert_gate(school)
    return {
        'balanceKobo': wallet.balance_kobo,
        'balance': wallet.balance_kobo / 100,
        'studentPriceKobo': pricing.student_price_kobo,
        'studentPrice': pricing.student_price_kobo / 100,
        'smsPriceKobo': pricing.sms_price_kobo,
        'smsPrice': pricing.sms_price_kobo / 100,
        'graceDays': pricing.grace_days,
        'autoRenew': pricing.auto_renew,
        'minDepositKobo': pricing.min_deposit_kobo,
        'minDeposit': pricing.min_deposit_kobo / 100,
        'maxDepositKobo': pricing.max_deposit_kobo,
        'sms': gate,
    }


class WalletView(APIView):
    permission_classes = [IsAuthenticated, HasSchool]

    def get(self, request):
        return Response(_wallet_payload(request.user.school))


class WalletTransactionListView(APIView):
    permission_classes = [IsAuthenticated, HasSchool]

    def get(self, request):
        transactions = WalletTransaction.objects.filter(
            school=request.user.school,
        ).select_related('student')
        category = (request.query_params.get('category') or '').strip()
        if category:
            transactions = transactions.filter(category=category)
        return Response(paginate(transactions, request, WalletTransactionSerializer))


class DepositCheckoutView(APIView):
    """POST /billing/deposits/ {amountKobo} → Paystack checkout.

    Free-form amount within configured min/max and Paystack's own floor.
    The wallet is NOT credited here — only after verification.
    """

    permission_classes = [
        IsAuthenticated, HasSchool, require_permissions('finance.payment'),
    ]

    def post(self, request):
        school = request.user.school
        try:
            amount_kobo = int(request.data.get('amountKobo') or 0)
        except (TypeError, ValueError):
            return Response(
                {'detail': 'Enter a valid deposit amount.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        pricing = services.get_pricing()
        if amount_kobo < pricing.min_deposit_kobo:
            return Response(
                {'detail': (
                    f'Minimum deposit is ₦{pricing.min_deposit_kobo / 100:,.2f}.'
                )},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if pricing.max_deposit_kobo and amount_kobo > pricing.max_deposit_kobo:
            return Response(
                {'detail': (
                    f'Maximum deposit is ₦{pricing.max_deposit_kobo / 100:,.2f}.'
                )},
                status=status.HTTP_400_BAD_REQUEST,
            )
        deposit = WalletDeposit.objects.create(
            school=school,
            reference=f'DEP-{school.slug[:16].upper()}-{services._ref("x")[4:12]}',
            amount_kobo=amount_kobo,
            created_by=request.user,
        )
        email = school.email or request.user.email
        try:
            data = paystack_client.initialize_transaction(
                email=email,
                amount_kobo=amount_kobo,
                reference=deposit.reference,
                callback_url=f'{_frontend_base()}/wallet',
                currency=deposit.currency,
                metadata={
                    'schoolId': str(school.id),
                    'schoolName': school.name,
                    'purpose': 'wallet_deposit',
                },
            )
            if not data.get('authorization_url'):
                raise paystack_client.PaystackError(
                    'Paystack did not return a checkout URL.',
                )
        except paystack_client.PaystackConfigError as exc:
            deposit.status = WalletDeposit.Status.FAILED
            deposit.save(update_fields=['status'])
            return Response({'detail': str(exc)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        except paystack_client.PaystackError as exc:
            deposit.status = WalletDeposit.Status.FAILED
            deposit.save(update_fields=['status'])
            return Response({'detail': str(exc)}, status=status.HTTP_502_BAD_GATEWAY)
        deposit.access_code = data.get('access_code', '') or ''
        deposit.authorization_url = data.get('authorization_url', '') or ''
        deposit.paystack_reference = data.get('reference', '') or deposit.reference
        try:
            deposit.save(update_fields=[
                'access_code', 'authorization_url', 'paystack_reference',
            ])
        except IntegrityError:
            deposit.status = WalletDeposit.Status.FAILED
            deposit.save(update_fields=['status'])
            return Response(
                {'detail': 'The provider returned a conflicting reference. Please try again.'},
                status=status.HTTP_502_BAD_GATEWAY,
            )
        public_key = getattr(settings, 'PAYSTACK_PUBLIC_KEY', '') or ''
        return Response({
            'reference': deposit.reference,
            'amountKobo': deposit.amount_kobo,
            'amount': deposit.amount_kobo / 100,
            'currency': deposit.currency,
            'email': email,
            'accessCode': deposit.access_code,
            'authorizationUrl': deposit.authorization_url,
            'publicKey': public_key,
        })


def _frontend_base() -> str:
    raw = getattr(settings, 'PAYSTACK_CALLBACK_URL', 'https://frontlinex.ng/wallet')
    base = raw.rsplit('/subscription', 1)[0] if '/subscription' in raw else raw.rsplit('/wallet', 1)[0]
    return base or 'https://frontlinex.ng'


def _confirm_deposit(deposit: WalletDeposit, request) -> Response:
    """Verify with Paystack, then credit exactly once. Shared by browser
    verification and the webhook (spec: never credit on redirect alone)."""
    try:
        data = paystack_client.verify_transaction(deposit.reference)
    except paystack_client.PaystackConfigError as exc:
        return Response({'detail': str(exc)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
    except paystack_client.PaystackError as exc:
        return Response({'detail': str(exc)}, status=status.HTTP_502_BAD_GATEWAY)

    if data.get('status') != 'success':
        if deposit.status == WalletDeposit.Status.PENDING:
            deposit.status = WalletDeposit.Status.FAILED
            deposit.raw = data
            deposit.save(update_fields=['status', 'raw'])
        return Response({'status': 'failed', 'reference': deposit.reference})

    gateway_reference = data.get('reference')
    matches = (
        int(data.get('amount') or 0) == deposit.amount_kobo
        and data.get('currency') == deposit.currency
        and gateway_reference in {deposit.reference, deposit.paystack_reference}
    )
    if not matches:
        deposit.status = WalletDeposit.Status.FAILED
        deposit.raw = data
        deposit.save(update_fields=['status', 'raw'])
        audit(
            request, 'wallet.deposit.verification_mismatch', deposit.school.name,
            'Gateway verification did not match the expected reference, amount, and currency.',
            severity='critical', entity='school', entity_id=str(deposit.school_id),
        )
        return Response({'status': 'failed', 'reference': deposit.reference})

    with transaction.atomic():
        locked = WalletDeposit.objects.select_for_update(of=('self',)).get(
            pk=deposit.pk,
        )
        if locked.status == WalletDeposit.Status.SUCCESS:
            wallet = services.get_wallet(deposit.school)
            return Response({
                'status': 'success',
                'reference': deposit.reference,
                'balanceKobo': wallet.balance_kobo,
            })
        locked.status = WalletDeposit.Status.SUCCESS
        locked.raw = data
        locked.save(update_fields=['status', 'raw'])
        wallet, entry = services.credit_wallet(
            deposit.school, deposit.amount_kobo,
            category=WalletTransaction.Category.DEPOSIT,
            description=f'Wallet deposit via Paystack ({deposit.reference}).',
            provider_reference=str(gateway_reference or ''),
            created_by=request.user if getattr(request, 'user', None) else None,
        )
    audit(
        request, 'wallet.deposit.verified', deposit.school.name,
        f'Wallet credited ₦{deposit.amount_kobo / 100:,.2f}.',
        entity='school', entity_id=str(deposit.school_id),
        after={'amount': deposit.amount_kobo / 100, 'reference': deposit.reference},
    )
    return Response({
        'status': 'success',
        'reference': deposit.reference,
        'balanceKobo': wallet.balance_kobo,
    })


class DepositVerifyView(APIView):
    """GET /billing/deposits/verify/<reference>/ — confirm a checkout."""

    permission_classes = [IsAuthenticated, HasSchool]

    def get(self, request, reference):
        deposit = WalletDeposit.objects.filter(
            reference=reference, school=request.user.school,
        ).first()
        if deposit is None:
            return Response(
                {'detail': 'Deposit not found.'}, status=status.HTTP_404_NOT_FOUND,
            )
        return _confirm_deposit(deposit, request)


class DepositWebhookView(APIView):
    """POST /billing/deposits/webhook/ — Paystack server callback. Unsigned or
    mismatched events never credit. Duplicate deliveries are no-ops."""

    permission_classes = []
    authentication_classes = []

    def post(self, request):
        signature = request.headers.get('x-paystack-signature', '')
        if not paystack_client.verify_webhook_signature(request.body, signature):
            return Response(
                {'detail': 'Invalid signature.'}, status=status.HTTP_401_UNAUTHORIZED,
            )
        try:
            payload = json.loads(request.body.decode('utf-8'))
        except (ValueError, UnicodeDecodeError):
            return Response(
                {'detail': 'Malformed payload.'}, status=status.HTTP_400_BAD_REQUEST,
            )
        if payload.get('event') == 'charge.success':
            data = payload.get('data') or {}
            reference = data.get('reference')
            deposit = WalletDeposit.objects.filter(
                reference=reference,
            ).first() or WalletDeposit.objects.filter(
                paystack_reference=reference,
            ).exclude(paystack_reference='').first()
            if deposit is not None and deposit.status != WalletDeposit.Status.SUCCESS:
                if (
                    data.get('status') == 'success'
                    and int(data.get('amount') or 0) == deposit.amount_kobo
                    and data.get('currency') == deposit.currency
                ):
                    return _confirm_deposit(deposit, request)
        return Response({'received': True})


class StudentAccessListView(APIView):
    """GET /billing/students/ — every student with current access status."""

    permission_classes = [IsAuthenticated, HasSchool]

    def get(self, request):
        school = request.user.school
        pricing = services.get_pricing()
        students = Student.objects.filter(school=school).order_by(
            'last_name', 'first_name', 'id',
        )
        search = (request.query_params.get('search') or '').strip()
        if search:
            students = students.filter(
                models_Q_name(search),
            )
        payload = []
        for student in students:
            entitlement = services.live_entitlement(student)
            payload.append(StudentAccessSerializer(
                {
                    'student': student,
                    'entitlement': entitlement,
                    'status': (
                        services.entitlement_status(
                            entitlement, grace_days=pricing.grace_days,
                        ) if entitlement else 'NeverActivated'
                    ),
                    'priceKobo': pricing.student_price_kobo,
                },
            ).data)
        return Response({'results': payload, 'count': len(payload)})


def models_Q_name(search):
    from django.db.models import Q
    return (
        Q(first_name__icontains=search)
        | Q(last_name__icontains=search)
        | Q(admission_number__icontains=search)
    )


class StudentActivateView(APIView):
    """POST /billing/students/<pk>/activate/ — charge wallet, open period."""

    permission_classes = [
        IsAuthenticated, HasSchool, require_permissions('finance.payment'),
    ]

    def post(self, request, pk):
        from records.services import public_refs
        school = request.user.school
        public_id = public_refs.required_public_id(pk)
        student = Student.objects.filter(
            public_id=public_id, school=school,
        ).first()
        if student is None:
            return Response(
                {'detail': 'Student not found.'}, status=status.HTTP_404_NOT_FOUND,
            )
        try:
            entitlement, created = services.activate_student(
                school, student, actor=request.user,
            )
        except services.InsufficientFunds as exc:
            return Response(
                {
                    'detail': str(exc),
                    'requiredKobo': exc.required_kobo,
                    'availableKobo': exc.available_kobo,
                },
                status=status.HTTP_402_PAYMENT_REQUIRED,
            )
        pricing = services.get_pricing()
        audit(
            request, 'wallet.student.activated', student_name(student),
            f'Student access {"activated" if created else "already active"} '
            f'({entitlement.period_start} – {entitlement.period_end}).',
            entity='student', entity_id=str(student.pk),
        )
        return Response({
            'created': created,
            'periodStart': entitlement.period_start.isoformat(),
            'periodEnd': entitlement.period_end.isoformat(),
            'amountKobo': entitlement.amount_kobo,
            'status': services.entitlement_status(
                entitlement, grace_days=pricing.grace_days,
            ),
        })


def student_name(student) -> str:
    return f'{student.first_name} {student.last_name}'.strip() or str(student.pk)


class MessagingView(APIView):
    """GET/PATCH /billing/messaging/ — school's own alert switch + availability."""

    permission_classes = [IsAuthenticated, HasSchool]

    def get(self, request):
        school = request.user.school
        messaging, _ = SchoolMessaging.objects.get_or_create(school=school)
        gate = services.alert_gate(school)
        return Response({
            'schoolEnabled': messaging.school_enabled,
            'platformBlocked': messaging.platform_blocked,
            **gate,
        })

    def patch(self, request):
        if request.user.role != 'school_admin':
            return Response(
                {'detail': 'Only the school administrator can change this setting.'},
                status=status.HTTP_403_FORBIDDEN,
            )
        school = request.user.school
        messaging, _ = SchoolMessaging.objects.get_or_create(school=school)
        if 'schoolEnabled' in request.data:
            messaging.school_enabled = bool(request.data.get('schoolEnabled'))
            messaging.save(update_fields=['school_enabled', 'updated_at'])
            audit(
                request, 'messaging.school_setting', school.name,
                f"SME alerts for the school switched {'on' if messaging.school_enabled else 'off'}.",
                entity='school', entity_id=str(school.pk),
            )
        return Response({
            'schoolEnabled': messaging.school_enabled,
            'platformBlocked': messaging.platform_blocked,
            **services.alert_gate(school),
        })


class AlertSendView(APIView):
    """POST /billing/alerts/ {recipient, message, reference?} — bill and send."""

    permission_classes = [
        IsAuthenticated, HasSchool, require_permissions('communication.write'),
    ]

    def post(self, request):
        school = request.user.school
        try:
            alert, created = services.request_alert(
                school,
                recipient=request.data.get('recipient', ''),
                message=request.data.get('message', ''),
                reference=(request.data.get('reference') or '').strip(),
                actor=request.user,
            )
        except services.AlertBlocked as exc:
            return Response(
                {'detail': str(exc), 'reasonCode': exc.code},
                status=status.HTTP_403_FORBIDDEN,
            )
        except services.InsufficientFunds as exc:
            return Response(
                {
                    'detail': str(exc),
                    'requiredKobo': exc.required_kobo,
                    'availableKobo': exc.available_kobo,
                },
                status=status.HTTP_402_PAYMENT_REQUIRED,
            )
        audit(
            request, 'messaging.alert.sent', school.name,
            f'SME alert to {alert.recipient} ({alert.reference}).',
            entity='sms_alert', entity_id=str(alert.pk),
        )
        return Response(SmsAlertSerializer(alert).data, status=status.HTTP_201_CREATED)


class AlertListView(APIView):
    permission_classes = [IsAuthenticated, HasSchool]

    def get(self, request):
        alerts = SmsAlert.objects.filter(school=request.user.school)
        return Response(paginate(alerts, request, SmsAlertSerializer))
