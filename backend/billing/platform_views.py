"""Platform Manager billing controls: pricing, school messaging, margin overview."""

from __future__ import annotations

from django.db.models import Count, Q, Sum
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.permissions import IsSuperAdmin
from accounts.utils import audit, paginate
from records.models import Student, UsageRecord
from records.services import public_refs
from schools.models import School

from .models import PlatformPricing, SchoolMessaging, SmsAlert, WalletTransaction
from .serializers import (
    PlatformTransactionSerializer,
    SmsAlertSerializer,
    WalletTransactionSerializer,
)
from . import services


class PricingView(APIView):
    """GET/PATCH /platform/billing/pricing/ — the billable numbers, one place."""

    permission_classes = [IsAuthenticated, IsSuperAdmin]

    def get(self, request):
        pricing = services.get_pricing()
        return Response(_pricing_payload(pricing))

    def patch(self, request):
        pricing = services.get_pricing()
        before = _pricing_payload(pricing)
        allowed = {
            'studentPriceKobo': 'student_price_kobo',
            'smsPriceKobo': 'sms_price_kobo',
            'graceDays': 'grace_days',
            'autoRenew': 'auto_renew',
            'smsEnabledGlobal': 'sms_enabled_global',
            'minDepositKobo': 'min_deposit_kobo',
            'maxDepositKobo': 'max_deposit_kobo',
        }
        changed = False
        for api_name, field in allowed.items():
            if api_name not in request.data:
                continue
            value = request.data.get(api_name)
            if field in (
                'student_price_kobo', 'sms_price_kobo', 'min_deposit_kobo',
            ):
                try:
                    value = int(value)
                except (TypeError, ValueError):
                    return Response(
                        {'detail': f'{api_name} must be a whole kobo amount.'},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                if value <= 0:
                    return Response(
                        {'detail': f'{api_name} must be greater than zero.'},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
            if field == 'max_deposit_kobo' and value in (None, ''):
                value = None
            elif field == 'max_deposit_kobo':
                try:
                    value = int(value)
                except (TypeError, ValueError):
                    return Response(
                        {'detail': 'maxDepositKobo must be a whole kobo amount.'},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
            if field == 'grace_days':
                try:
                    value = int(value)
                except (TypeError, ValueError):
                    return Response(
                        {'detail': 'graceDays must be a whole number of days.'},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                if value < 0 or value > 30:
                    return Response(
                        {'detail': 'graceDays must be between 0 and 30.'},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
            setattr(pricing, field, value)
            changed = True
        if changed:
            pricing.price_changed_at = timezone.now()
            pricing.changed_by = request.user
            pricing.save()
            audit(
                request, 'billing.pricing.updated', 'platform pricing',
                'Platform billing policy changed.',
                severity='warning', entity='platform_pricing', entity_id='1',
                before=before, after=_pricing_payload(pricing),
            )
        return Response(_pricing_payload(pricing))


def _pricing_payload(pricing) -> dict:
    return {
        'studentPriceKobo': pricing.student_price_kobo,
        'smsPriceKobo': pricing.sms_price_kobo,
        'graceDays': pricing.grace_days,
        'autoRenew': pricing.auto_renew,
        'smsEnabledGlobal': pricing.sms_enabled_global,
        'minDepositKobo': pricing.min_deposit_kobo,
        'maxDepositKobo': pricing.max_deposit_kobo,
        'priceChangedAt': (
            pricing.price_changed_at.isoformat() if pricing.price_changed_at else None
        ),
    }


class SchoolMessagingView(APIView):
    """GET/PATCH /platform/schools/<pk>/messaging/ — per-school alert control."""

    permission_classes = [IsAuthenticated, IsSuperAdmin]

    def get(self, request, pk):
        school = School.objects.filter(pk=pk).first()
        if school is None:
            return Response(
                {'detail': 'School not found.'}, status=status.HTTP_404_NOT_FOUND,
            )
        messaging, _ = SchoolMessaging.objects.get_or_create(school=school)
        return Response(_messaging_payload(school, messaging))

    def patch(self, request, pk):
        school = School.objects.filter(pk=pk).first()
        if school is None:
            return Response(
                {'detail': 'School not found.'}, status=status.HTTP_404_NOT_FOUND,
            )
        messaging, _ = SchoolMessaging.objects.get_or_create(school=school)
        before = _messaging_payload(school, messaging)
        if 'platformBlocked' in request.data:
            messaging.platform_blocked = bool(request.data.get('platformBlocked'))
        if 'schoolEnabled' in request.data:
            # Platform may also flip the school switch (e.g. abuse freeze).
            messaging.school_enabled = bool(request.data.get('schoolEnabled'))
        messaging.save()
        audit(
            request, 'billing.messaging.updated', school.name,
            'School messaging controls changed by platform manager.',
            severity='warning', entity='school', entity_id=str(school.pk),
            before=before, after=_messaging_payload(school, messaging),
        )
        return Response(_messaging_payload(school, messaging))


def _messaging_payload(school, messaging) -> dict:
    gate = services.alert_gate(school)
    usage = SmsAlert.objects.filter(school=school).aggregate(
        total=Count('id'),
        sent=Count('id', filter=Q(status=SmsAlert.Status.SENT)),
        failed=Count('id', filter=Q(status__in=[
            SmsAlert.Status.FAILED, SmsAlert.Status.PROVIDER_REJECTED,
        ])),
        refunded=Count('id', filter=Q(status=SmsAlert.Status.REFUNDED)),
        charged=Sum('customer_kobo', filter=Q(status=SmsAlert.Status.SENT)),
    )
    return {
        'schoolId': str(school.pk),
        'schoolName': school.name,
        'platformBlocked': messaging.platform_blocked,
        'schoolEnabled': messaging.school_enabled,
        **gate,
        'usage': {
            'total': usage['total'] or 0,
            'sent': usage['sent'] or 0,
            'failed': usage['failed'] or 0,
            'refunded': usage['refunded'] or 0,
            'chargedKobo': usage['charged'] or 0,
        },
    }


class MessagingOverviewView(APIView):
    """GET /platform/billing/messaging/ — totals, charges vs known provider costs."""

    permission_classes = [IsAuthenticated, IsSuperAdmin]

    def get(self, request):
        alerts = SmsAlert.objects.all()
        totals = alerts.aggregate(
            total=Count('id'),
            sent=Count('id', filter=Q(status=SmsAlert.Status.SENT)),
            failed=Count('id', filter=Q(status__in=[
                SmsAlert.Status.FAILED, SmsAlert.Status.PROVIDER_REJECTED,
            ])),
            chargedKobo=Sum('customer_kobo', filter=Q(status=SmsAlert.Status.SENT)),
            knownCostKobo=Sum(
                'provider_cost_kobo',
                filter=Q(
                    status=SmsAlert.Status.SENT,
                    provider_cost_kobo__isnull=False,
                ),
            ),
            unknownCost=Count('id', filter=Q(
                status=SmsAlert.Status.SENT, provider_cost_kobo__isnull=True,
            )),
        )
        provider_usage = UsageRecord.objects.filter(
            resource_type=UsageRecord.ResourceType.SMS,
        ).aggregate(
            total=Count('id'),
            succeeded=Count('id', filter=Q(status=UsageRecord.Status.SUCCEEDED)),
            failed=Count('id', filter=Q(status=UsageRecord.Status.FAILED)),
            exhausted=Count('id', filter=Q(status=UsageRecord.Status.EXHAUSTED)),
        )
        return Response({
            'alerts': {
                'total': totals['total'] or 0,
                'sent': totals['sent'] or 0,
                'failed': totals['failed'] or 0,
                'chargedKobo': totals['chargedKobo'] or 0,
                # Gross margin is only meaningful where the provider reported a
                # cost; unknown-cost messages are counted separately, never
                # assumed free.
                'knownCostKobo': totals['knownCostKobo'] or 0,
                'unknownCostCount': totals['unknownCost'] or 0,
            },
            'providerUsage': {
                'total': provider_usage['total'] or 0,
                'succeeded': provider_usage['succeeded'] or 0,
                'failed': provider_usage['failed'] or 0,
                'exhausted': provider_usage['exhausted'] or 0,
            },
            'globalEnabled': services.get_pricing().sms_enabled_global,
        })


class ManualAdjustmentView(APIView):
    """POST /platform/billing/adjustments/ — justified, audited wallet fixes only."""

    permission_classes = [IsAuthenticated, IsSuperAdmin]

    def post(self, request):
        school = School.objects.filter(pk=request.data.get('schoolId')).first()
        if school is None:
            return Response(
                {'detail': 'School not found.'}, status=status.HTTP_404_NOT_FOUND,
            )
        try:
            amount_kobo = int(request.data.get('amountKobo') or 0)
        except (TypeError, ValueError):
            return Response(
                {'detail': 'amountKobo must be a whole kobo amount.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        reason = str(request.data.get('reason') or '').strip()
        if not reason:
            return Response(
                {'detail': 'A written reason is required for manual adjustments.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if amount_kobo == 0:
            return Response(
                {'detail': 'Amount cannot be zero.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            if amount_kobo > 0:
                _, entry = services.credit_wallet(
                    school, amount_kobo,
                    category=WalletTransaction.Category.ADJUSTMENT,
                    description=f'Manual adjustment by platform: {reason}',
                    created_by=request.user,
                )
            else:
                _, entry = services.debit_wallet(
                    school, -amount_kobo,
                    category=WalletTransaction.Category.ADJUSTMENT,
                    description=f'Manual adjustment by platform: {reason}',
                    created_by=request.user,
                    what='manual adjustment',
                )
        except services.InsufficientFunds as exc:
            return Response(
                {'detail': services.error_message(exc)},
                status=status.HTTP_402_PAYMENT_REQUIRED,
            )
        audit(
            request, 'wallet.adjustment', school.name,
            f'Manual wallet adjustment of ₦{amount_kobo / 100:,.2f}. Reason: {reason}.',
            severity='warning', entity='school', entity_id=str(school.pk),
            after={'amountKobo': amount_kobo, 'reference': entry.reference},
        )
        wallet = services.get_wallet(school)
        return Response({
            'reference': entry.reference,
            'balanceKobo': wallet.balance_kobo,
        }, status=status.HTTP_201_CREATED)


class ComplimentaryAccessView(APIView):
    """POST /billing/platform/complimentary/ — authorized free student access.

    Body: {schoolId, studentId (public UUID), reason}. Creates a zero-amount
    entitlement flagged complimentary — never a fake deposit or payment. Only
    platform managers; every grant is audited with school, student, reason
    and granter.
    """

    permission_classes = [IsAuthenticated, IsSuperAdmin]

    def post(self, request):
        school = School.objects.filter(pk=request.data.get('schoolId')).first()
        if school is None:
            return Response(
                {'detail': 'School not found.'}, status=status.HTTP_404_NOT_FOUND,
            )
        try:
            public_id = public_refs.required_public_id(request.data.get('studentId') or '')
        except Exception:
            public_id = None
        student = (
            Student.objects.filter(public_id=public_id, school=school).first()
            if public_id is not None else None
        )
        if student is None:
            return Response(
                {'detail': 'Student not found.'}, status=status.HTTP_404_NOT_FOUND,
            )
        reason = str(request.data.get('reason') or '').strip()
        if not reason:
            return Response(
                {'detail': 'A written reason is required for complimentary access.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        entitlement, created = services.grant_complimentary_access(
            school, student, reason=reason, actor=request.user,
        )
        name = f'{student.first_name} {student.last_name}'.strip() or str(student.pk)
        audit(
            request, 'wallet.access.complimentary', name,
            f'Complimentary access {"granted" if created else "already active"} '
            f'({entitlement.period_start} – {entitlement.period_end}). Reason: {reason}.',
            severity='warning', entity='student', entity_id=str(student.pk),
            after={
                'schoolId': str(school.pk),
                'reason': reason,
                'periodStart': entitlement.period_start.isoformat(),
                'periodEnd': entitlement.period_end.isoformat(),
            },
        )
        return Response({
            'created': created,
            'periodStart': entitlement.period_start.isoformat(),
            'periodEnd': entitlement.period_end.isoformat(),
            'reason': entitlement.comp_reason,
        }, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)


class PlatformTransactionListView(APIView):
    """GET /billing/platform/transactions/ — every school's wallet ledger.

    The platform manager's transaction trace: deposits in, access charges,
    renewals, SME charges, refunds and manual adjustments, across all
    schools, newest first. Filters: `school` (pk), `category`, `direction`,
    `status`, `search` (reference, provider reference, description or school
    name). The `summary` block totals the *filtered* set (not just the page)
    so the dashboard chips stay truthful while paging.

    Platform-only. School staff keep the school-scoped
    `GET /billing/transactions/` which can never see another tenant.
    """

    permission_classes = [IsAuthenticated, IsSuperAdmin]

    def get(self, request):
        transactions = WalletTransaction.objects.select_related(
            'school', 'student',
        ).all()
        school_id = (request.query_params.get('school') or '').strip()
        if school_id:
            transactions = transactions.filter(school_id=school_id)
        category = (request.query_params.get('category') or '').strip()
        if category:
            transactions = transactions.filter(category=category)
        direction = (request.query_params.get('direction') or '').strip()
        if direction:
            transactions = transactions.filter(direction=direction)
        txn_status = (request.query_params.get('status') or '').strip()
        if txn_status:
            transactions = transactions.filter(status=txn_status)
        search = (request.query_params.get('search') or '').strip()
        if search:
            transactions = transactions.filter(
                Q(reference__icontains=search)
                | Q(provider_reference__icontains=search)
                | Q(description__icontains=search)
                | Q(school__name__icontains=search),
            )
        totals = transactions.aggregate(
            count=Count('id'),
            creditsKobo=Sum(
                'amount_kobo',
                filter=Q(
                    direction=WalletTransaction.Direction.CREDIT,
                    status=WalletTransaction.Status.SUCCESS,
                ),
            ),
            debitsKobo=Sum(
                'amount_kobo',
                filter=Q(
                    direction=WalletTransaction.Direction.DEBIT,
                    status=WalletTransaction.Status.SUCCESS,
                ),
            ),
        )
        page = paginate(transactions, request, PlatformTransactionSerializer)
        page['summary'] = {
            'count': totals['count'] or 0,
            'creditsKobo': totals['creditsKobo'] or 0,
            'debitsKobo': totals['debitsKobo'] or 0,
        }
        return Response(page)
