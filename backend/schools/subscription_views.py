"""Subscription payments and the platform manager's subscription controls.

Two jobs live here:

1. The money path for a paid subscription — start a checkout, verify it, and
   accept Paystack's webhook. All three funnel through :func:`activate_subscription`
   so a school is switched on in exactly one place, no matter how the payment
   was confirmed.

2. The platform manager's controls over the commercial structure: the plan
   editor, per-school subscription management (including a complimentary
   override), the transactions ledger, and the plan catalogue.
"""
from __future__ import annotations

import json
import secrets
from datetime import timedelta

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import User
from accounts.permissions import HasSchool, IsSuperAdmin, require_permissions
from accounts.utils import audit, paginate
from . import paystack
from .models import School, SchoolSubscription, SubscriptionPayment, SubscriptionPlan
from .platform_views import _platform_school_detail
from .serializers import (
    PlatformPlanSerializer,
    PublicPlanSerializer,
    SubscriptionPaymentSerializer,
)


# ── Shared helpers ──────────────────────────────────────────────────────────

def _period_days() -> int:
    return int(getattr(settings, 'SUBSCRIPTION_PERIOD_DAYS', 30))


def _amount_kobo(plan: SubscriptionPlan) -> int:
    return int((plan.monthly_price or 0) * 100)


def _new_reference(school: School) -> str:
    return f'SUB-{school.slug[:16].upper()}-{secrets.token_hex(4).upper()}'


def _resolve_plan(plan_id):
    if not plan_id:
        return None
    return (
        SubscriptionPlan.objects.filter(code=plan_id).first()
        or SubscriptionPlan.objects.filter(name=plan_id).first()
    )


def _parse_datetime(value):
    if value in (None, ''):
        return None
    parsed = parse_datetime(str(value))
    if parsed is not None and timezone.is_naive(parsed):
        parsed = timezone.make_aware(parsed, timezone.get_current_timezone())
    return parsed


def activate_subscription(payment: SubscriptionPayment, *, occurred_at=None) -> SchoolSubscription:
    """Mark a payment successful and switch the school on.

    Idempotent: called from both the browser verification and the webhook, and
    safe to run twice. A renewal extends from the current expiry when that is
    still in the future, so paying early never loses time; otherwise it starts
    from now.
    """
    now = occurred_at or timezone.now()
    with transaction.atomic():
        subscription, _ = (
            SchoolSubscription.objects.select_for_update()
            .get_or_create(school=payment.school)
        )
        if payment.plan_id:
            subscription.plan = payment.plan
        base = subscription.expires_at if (
            subscription.expires_at and subscription.expires_at > now
        ) else now
        subscription.status = SchoolSubscription.Status.ACTIVE
        subscription.starts_at = subscription.starts_at or now
        subscription.expires_at = base + timedelta(days=_period_days())
        # A successful payment supersedes any complimentary override.
        subscription.override_active = False
        subscription.override_until = None
        subscription.save()

        school = payment.school
        if not school.is_active:
            school.is_active = True
            school.save(update_fields=['is_active'])
        # Any administrator account that was parked awaiting payment can sign in.
        school.users.filter(role=User.Role.SCHOOL_ADMIN).update(
            is_active=True, is_verified=True,
        )

        if payment.status != SubscriptionPayment.Status.SUCCESS:
            payment.status = SubscriptionPayment.Status.SUCCESS
            payment.paid_at = now
            payment.save(update_fields=['status', 'paid_at', 'updated_at'])
    return subscription


def _checkout_payload(payment: SubscriptionPayment, email: str) -> dict:
    public_key = getattr(settings, 'PAYSTACK_PUBLIC_KEY', '') or ''
    return {
        'reference': payment.reference,
        'amountKobo': payment.amount_kobo,
        'amount': float(payment.amount_kobo) / 100,
        'currency': payment.currency,
        'email': email,
        'accessCode': payment.access_code,
        'authorizationUrl': payment.authorization_url,
        'publicKey': public_key,
        'planId': (payment.plan.code or payment.plan.name) if payment.plan_id else None,
        'planLabel': payment.plan.name if payment.plan_id else '',
        'schoolId': str(payment.school_id),
        'schoolName': payment.school.name,
        'purpose': payment.purpose,
    }


def _start_checkout(school, plan, *, purpose, user=None) -> Response:
    payment = SubscriptionPayment.objects.create(
        school=school,
        plan=plan,
        reference=_new_reference(school),
        amount_kobo=_amount_kobo(plan),
        purpose=purpose,
        created_by=user,
    )
    email = school.email or (user.email if user else '')
    try:
        data = paystack.initialize_transaction(
            email=email,
            amount_kobo=payment.amount_kobo,
            reference=payment.reference,
            metadata={
                'schoolId': str(school.id),
                'schoolName': school.name,
                'plan': plan.code or plan.name,
            },
        )
    except paystack.PaystackConfigError as exc:
        payment.status = SubscriptionPayment.Status.FAILED
        payment.save(update_fields=['status', 'updated_at'])
        return Response({'detail': str(exc)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
    except paystack.PaystackError as exc:
        payment.status = SubscriptionPayment.Status.FAILED
        payment.save(update_fields=['status', 'updated_at'])
        return Response({'detail': str(exc)}, status=status.HTTP_502_BAD_GATEWAY)

    payment.access_code = data.get('access_code', '') or ''
    payment.authorization_url = data.get('authorization_url', '') or ''
    payment.paystack_reference = data.get('reference', '') or payment.reference
    payment.save(update_fields=['access_code', 'authorization_url', 'paystack_reference'])
    return Response(_checkout_payload(payment, email))


def _verify_and_confirm(payment: SubscriptionPayment, request) -> Response:
    try:
        data = paystack.verify_transaction(payment.reference)
    except paystack.PaystackConfigError as exc:
        return Response({'detail': str(exc)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
    except paystack.PaystackError as exc:
        return Response({'detail': str(exc)}, status=status.HTTP_502_BAD_GATEWAY)

    if data.get('status') != 'success':
        if payment.status == SubscriptionPayment.Status.PENDING:
            payment.status = SubscriptionPayment.Status.ABANDONED
            payment.raw = data
            payment.save(update_fields=['status', 'raw', 'updated_at'])
        return Response({'status': 'pending', 'reference': payment.reference})

    if int(data.get('amount') or 0) != payment.amount_kobo:
        # The gateway confirmed a payment, but not for the amount we asked for.
        # Never switch the school on from a mismatched amount.
        payment.status = SubscriptionPayment.Status.FAILED
        payment.raw = data
        payment.save(update_fields=['status', 'raw', 'updated_at'])
        audit(
            request, 'subscription.payment.amount_mismatch', payment.school.name,
            f'Expected {payment.amount_kobo} kobo, gateway reported {data.get("amount")}.',
            severity='critical', entity='school', entity_id=str(payment.school_id),
        )
        return Response({'status': 'failed', 'reference': payment.reference})

    subscription = activate_subscription(payment)
    audit(
        request, 'subscription.payment.verified', payment.school.name,
        f'{payment.purpose} payment confirmed for {(payment.plan.name if payment.plan_id else "plan")}.',
        entity='school', entity_id=str(payment.school_id),
        after={
            'amount': float(payment.amount_kobo) / 100,
            'reference': payment.reference,
            'expiresAt': subscription.expires_at.isoformat() if subscription.expires_at else '',
        },
    )
    return Response({
        'status': 'success',
        'reference': payment.reference,
        'expiresAt': subscription.expires_at.isoformat() if subscription.expires_at else None,
    })


# ── Payment endpoints ───────────────────────────────────────────────────────

class SubscriptionCheckoutView(APIView):
    """POST /schools/subscriptions/checkout/ → a Paystack checkout to open.

    Starts (or restarts) a payment for the caller's school. The plan is taken
    from the request when supplied, otherwise the school's current plan; the
    amount always comes from the plan row, never from the client.
    """

    permission_classes = [
        IsAuthenticated, HasSchool, require_permissions('subscription.write'),
    ]

    def post(self, request):
        school = request.user.school
        plan = _resolve_plan(request.data.get('planId'))
        if plan is None:
            subscription = SchoolSubscription.objects.filter(school=school).first()
            plan = subscription.plan if subscription and subscription.plan_id else None
        if plan is None:
            plan = SubscriptionPlan.objects.filter(is_active=True).order_by(
                'sort_order', 'min_students',
            ).first()
        if plan is None:
            return Response(
                {'detail': 'No subscription plan is available to purchase.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return _start_checkout(
            school, plan, purpose=SubscriptionPayment.Purpose.RENEWAL, user=request.user,
        )


class SubscriptionVerifyView(APIView):
    """GET /schools/subscriptions/verify/<reference>/ → confirm a checkout."""

    permission_classes = [IsAuthenticated, HasSchool]

    def get(self, request, reference):
        payment = SubscriptionPayment.objects.filter(
            reference=reference, school=request.user.school,
        ).first()
        if payment is None:
            return Response({'detail': 'Payment not found.'}, status=status.HTTP_404_NOT_FOUND)
        return _verify_and_confirm(payment, request)


class SubscriptionWebhookView(APIView):
    """POST /schools/subscriptions/webhook/ → Paystack's server callback.

    Unauthenticated by design; the signed body is the only credential. DRF views
    are already CSRF-exempt. We only act on ``charge.success`` and re-verify the
    amount ourselves before touching the subscription, so a forged or stale
    event cannot switch a school on.
    """

    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        signature = request.headers.get('x-paystack-signature', '')
        if not paystack.verify_webhook_signature(request.body, signature):
            return Response({'detail': 'Invalid signature.'}, status=status.HTTP_401_UNAUTHORIZED)
        try:
            payload = json.loads(request.body.decode('utf-8'))
        except (ValueError, UnicodeDecodeError):
            return Response({'detail': 'Malformed payload.'}, status=status.HTTP_400_BAD_REQUEST)

        if payload.get('event') == 'charge.success':
            data = payload.get('data') or {}
            reference = data.get('reference')
            payment = SubscriptionPayment.objects.filter(reference=reference).first()
            if payment is not None and payment.status != SubscriptionPayment.Status.SUCCESS:
                if int(data.get('amount') or 0) == payment.amount_kobo:
                    activate_subscription(payment)
        # Always 200 so Paystack does not retry an event we have handled.
        return Response({'received': True})


# ── Platform: plan management ────────────────────────────────────────────────

class PlatformPlanListCreateView(APIView):
    permission_classes = [IsAuthenticated, IsSuperAdmin]

    def get(self, request):
        plans = SubscriptionPlan.objects.all().order_by('sort_order', 'min_students', 'id')
        return Response({
            'results': PlatformPlanSerializer(plans, many=True).data,
            'catalogue': PublicPlanSerializer(
                SubscriptionPlan.objects.filter(is_active=True).order_by(
                    'sort_order', 'min_students',
                ),
                many=True,
            ).data,
        })

    def post(self, request):
        serializer = PlatformPlanSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            plan = serializer.save()
        except IntegrityError:
            return Response(
                {'detail': 'A plan with that code or name already exists.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        audit(
            request, 'subscription.plan.created', plan.name,
            f'Plan {plan.name} created.', entity='subscription_plan', entity_id=str(plan.pk),
            after=PlatformPlanSerializer(plan).data,
        )
        return Response(PlatformPlanSerializer(plan).data, status=status.HTTP_201_CREATED)


class PlatformPlanDetailView(APIView):
    permission_classes = [IsAuthenticated, IsSuperAdmin]

    def get_object(self, pk):
        return SubscriptionPlan.objects.filter(pk=pk).first()

    def patch(self, request, pk):
        plan = self.get_object(pk)
        if plan is None:
            return Response({'detail': 'Plan not found.'}, status=status.HTTP_404_NOT_FOUND)
        before = PlatformPlanSerializer(plan).data
        serializer = PlatformPlanSerializer(plan, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        try:
            plan = serializer.save()
        except IntegrityError:
            return Response(
                {'detail': 'A plan with that code or name already exists.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        audit(
            request, 'subscription.plan.updated', plan.name,
            'Plan updated.', entity='subscription_plan', entity_id=str(plan.pk),
            before=before, after=PlatformPlanSerializer(plan).data,
        )
        return Response(PlatformPlanSerializer(plan).data)

    def delete(self, request, pk):
        plan = self.get_object(pk)
        if plan is None:
            return Response({'detail': 'Plan not found.'}, status=status.HTTP_404_NOT_FOUND)
        in_use = SchoolSubscription.objects.filter(plan=plan).exists()
        if in_use:
            # Never delete a plan a school is on: that would silently strand the
            # school. Deactivating keeps existing schools intact.
            return Response(
                {'detail': 'This plan is in use. Deactivate it instead of deleting.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        name = plan.name
        plan.delete()
        audit(
            request, 'subscription.plan.deleted', name, 'Plan deleted.',
            severity='warning', entity='subscription_plan', entity_id=str(pk),
        )
        return Response({'deleted': name})


# ── Platform: per-school subscription ────────────────────────────────────────

class PlatformSchoolSubscriptionView(APIView):
    """PATCH /platform/schools/<pk>/subscription/ — the commercial controls."""

    permission_classes = [IsAuthenticated, IsSuperAdmin]

    def patch(self, request, pk):
        school = School.objects.filter(id=pk).first()
        if school is None:
            return Response({'detail': 'School not found.'}, status=status.HTTP_404_NOT_FOUND)

        subscription, _ = SchoolSubscription.objects.get_or_create(school=school)
        before = {
            'plan': subscription.plan.name if subscription.plan_id else '',
            'status': subscription.status,
            'expiresAt': subscription.expires_at.isoformat() if subscription.expires_at else None,
            'overrideActive': subscription.override_active,
            'overrideUntil': subscription.override_until.isoformat() if subscription.override_until else None,
        }
        now = timezone.now()

        if 'planId' in request.data:
            plan = _resolve_plan(request.data.get('planId'))
            if plan is None and request.data.get('planId'):
                return Response({'detail': 'Unknown plan.'}, status=status.HTTP_400_BAD_REQUEST)
            subscription.plan = plan

        status_value = request.data.get('status')
        if status_value:
            valid = {choice for choice, _ in SchoolSubscription.Status.choices}
            if status_value not in valid:
                return Response({'detail': 'Invalid status.'}, status=status.HTTP_400_BAD_REQUEST)
            subscription.status = status_value

        if 'expiresAt' in request.data:
            subscription.expires_at = _parse_datetime(request.data.get('expiresAt'))

        extend_days = request.data.get('extendDays')
        if extend_days not in (None, ''):
            try:
                days = int(extend_days)
            except (TypeError, ValueError):
                return Response({'detail': 'extendDays must be a number.'}, status=status.HTTP_400_BAD_REQUEST)
            base = subscription.expires_at if (
                subscription.expires_at and subscription.expires_at > now
            ) else now
            subscription.expires_at = base + timedelta(days=days)

        if 'overrideActive' in request.data or 'overrideUntil' in request.data or 'note' in request.data:
            if 'overrideActive' in request.data:
                subscription.override_active = bool(request.data.get('overrideActive'))
            if 'overrideUntil' in request.data:
                subscription.override_until = _parse_datetime(request.data.get('overrideUntil'))
            if 'note' in request.data:
                subscription.override_note = str(request.data.get('note') or '')[:200]
            if subscription.override_active:
                subscription.override_by = request.user
                subscription.override_at = now

        subscription.save()

        # The school's own `is_active` gate follows the platform status so a
        # reinstate actually lets staff back in, and a suspension actually locks
        # them out. Suspension is the one status that overrides a grant.
        subscription.refresh_from_db()
        granted = subscription.status in (
            SchoolSubscription.Status.ACTIVE, SchoolSubscription.Status.TRIAL,
        ) or subscription.override_current
        if subscription.status == SchoolSubscription.Status.SUSPENDED:
            granted = False
        if school.is_active != granted:
            school.is_active = granted
            school.save(update_fields=['is_active'])

        audit(
            request, 'subscription.updated', school.name,
            'Subscription updated by platform manager.', severity='warning',
            entity='school', entity_id=str(school.pk), before=before,
            after={
                'plan': subscription.plan.name if subscription.plan_id else '',
                'status': subscription.status,
                'expiresAt': subscription.expires_at.isoformat() if subscription.expires_at else None,
            },
        )
        # The overview rollup embeds subscription state and is cached for a few
        # minutes; drop the global rollups so the change is reflected at once.
        from django.core.cache import cache
        for days in (7, 30, 90):
            cache.delete(f'platform:overview:{days}:all')
        return Response(_platform_school_detail(school))


# ── Platform: transactions ledger ────────────────────────────────────────────

class PlatformPaymentListView(APIView):
    permission_classes = [IsAuthenticated, IsSuperAdmin]

    def get(self, request):
        payments = SubscriptionPayment.objects.select_related('school', 'plan')
        status_filter = (request.query_params.get('status') or '').strip()
        if status_filter:
            payments = payments.filter(status=status_filter)
        school_id = (request.query_params.get('schoolId') or '').strip()
        if school_id:
            payments = payments.filter(school_id=school_id)
        search = (request.query_params.get('search') or '').strip()
        if search:
            payments = payments.filter(reference__icontains=search) | payments.filter(
                school__name__icontains=search,
            )
        return Response(paginate(payments, request, SubscriptionPaymentSerializer))
