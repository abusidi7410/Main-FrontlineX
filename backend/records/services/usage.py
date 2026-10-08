"""Centralized usage tracking and allowance enforcement.

All paid operations (SMS, OTP, AI) must go through this service to:
- Check per-school allowances before executing
- Record usage in the centralized ledger
- Enforce exhaustion policies (block or allow based on policy)
"""

from decimal import Decimal
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from ..models import (
    School,
    UsageRecord,
    Student,
    Invoice,
    Payment,
    ResultSheet,
)
from schools.models import SubscriptionPlan
from . import billing as billing_service
from . import sms as sms_service

from rest_framework.exceptions import ValidationError, PermissionDenied


class AllowanceExhausted(Exception):
    """Raised when a school's allowance for a resource is exhausted."""
    def __init__(self, resource_type: str, allowance: int, used: int):
        self.resource_type = resource_type
        self.allowance = allowance
        self.used = used
        super().__init__(
            f'{resource_type.upper()} allowance exhausted: {used}/{allowance} used'
        )


class UsageService:
    """Central service for usage tracking and allowance enforcement."""

    # AI operation credit costs (configurable per operation type)
    AI_COSTS = {
        'simple_request': 1,
        'normal_analysis': 3,
        'report_analysis': 5,
        'large_analysis': 10,
    }

    def __init__(self):
        pass

    # ---------------------------------------------------------------------
    # Allowance checking
    # ---------------------------------------------------------------------
    def _get_school_plan(self, school: 'School') -> SubscriptionPlan:
        """Get the school's active subscription plan."""
        from schools.models import SchoolSubscription
        try:
            subscription = SchoolSubscription.objects.select_related('plan').get(
                school_id=school.id,
                status='active',
            )
            return subscription.plan
        except Exception:
            # Return default plan if none
            return SubscriptionPlan.objects.first() or SubscriptionPlan(
                monthly_sms_allowance=0,
                monthly_otp_allowance=0,
                monthly_ai_allowance=0,
                ai_credits=0,
            )

    def _get_monthly_usage(self, school: 'School', resource_type: str) -> int:
        """Get the school's usage for the current billing month."""
        from django.db.models import Sum
        from django.db.models.functions import TruncMonth
        from schools.models import SchoolSubscription

        try:
            subscription = SchoolSubscription.objects.get(school_id=school.id, status='active')
            billing_start = subscription.starts_at.replace(day=1)
        except Exception:
            # Fallback: current month
            billing_start = timezone.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)

        resource_type_map = {
            'sms': UsageRecord.ResourceType.SMS,
            'otp': UsageRecord.ResourceType.OTP,
            'ai': UsageRecord.ResourceType.AI,
        }

        agg = UsageRecord.objects.filter(
            school_id=school.id,
            resource_type=resource_type_map.get(resource_type, resource_type),
            created_at__gte=billing_start,
        ).aggregate(total=Sum('quantity'))

        return agg['total'] or 0

    def check_allowance(self, school: 'School', resource_type: str, quantity: int = 1) -> bool:
        """Check if the school has enough allowance for the requested quantity."""
        plan = self._get_school_plan(school)
        used = self._get_monthly_usage(school, resource_type)

        if resource_type == 'sms':
            allowance = plan.monthly_sms_allowance
        elif resource_type == 'otp':
            allowance = plan.monthly_otp_allowance
        elif resource_type == 'ai':
            allowance = plan.monthly_ai_allowance
        else:
            return True  # Unknown resource, allow by default

        return (used + quantity) <= allowance

    def enforce_allowance(self, school: 'School', resource_type: str, quantity: int = 1) -> None:
        """Raise AllowanceExhausted if the school doesn't have enough allowance."""
        plan = self._get_school_plan(school)
        used = self._get_monthly_usage(school, resource_type)

        if resource_type == 'sms':
            allowance = plan.monthly_sms_allowance
        elif resource_type == 'otp':
            allowance = plan.monthly_otp_allowance
        elif resource_type == 'ai':
            allowance = plan.monthly_ai_allowance
        else:
            return

        if (used + quantity) > allowance:
            raise AllowanceExhausted(resource_type, allowance, used)

    # ---------------------------------------------------------------------
    # Usage recording
    # ---------------------------------------------------------------------
    def record_usage(
        self,
        school,
        resource_type: str,
        action_type: str,
        quantity: int = 1,
        credits_used: int = 0,
        provider: str = '',
        provider_reference: str = '',
        estimated_cost: int = 0,
        actual_cost: int = 0,
        status: str = 'succeeded',
        student=None,
        user=None,
        invoice=None,
        payment=None,
        result_sheet=None,
    ):
        """Record a usage event in the centralized ledger."""
        from . import billing as billing_service

        # Map resource type
        resource_type_map = {
            'sms': UsageRecord.ResourceType.SMS,
            'otp': UsageRecord.ResourceType.OTP,
            'ai': UsageRecord.ResourceType.AI,
        }

        action_type_map = {
            'payment_notification': UsageRecord.ActionType.PAYMENT_NOTIFICATION,
            'balance_reminder': UsageRecord.ActionType.BALANCE_REMINDER,
            'otp_send': UsageRecord.ActionType.OTP_SEND,
            'ai_request': UsageRecord.ActionType.AI_REQUEST,
            'ai_proposal': UsageRecord.ActionType.AI_PROPOSAL,
            'ai_confirmation': UsageRecord.ActionType.AI_CONFIRMATION,
        }

        UsageRecord.objects.create(
            school=school,
            resource_type=resource_type_map.get(resource_type, resource_type),
            action_type=action_type_map.get(action_type, action_type),
            quantity=quantity,
            credits_used=credits_used,
            provider=provider,
            provider_reference=provider_reference,
            estimated_cost=estimated_cost,
            actual_cost=actual_cost,
            status=status,
            student=student,
            user=user,
            invoice=invoice,
            payment=payment,
            result_sheet=result_sheet,
        )

    # ---------------------------------------------------------------------
    # SMS operations
    # ---------------------------------------------------------------------
    def send_sms(self, school, to: str, message: str, action_type: str,
                 student=None, user=None, invoice=None, payment=None) -> bool:
        """Send an SMS with allowance checking and usage recording.

        Exhaustion raises `AllowanceExhausted` *after* an `exhausted` ledger
        row is written, so blocked sends are visible in the profit report and
        a caller can tell "provider failed" from "allowance gone". A provider
        failure raises DRF `ValidationError` after the `failed` row is written.
        """
        from django.conf import settings

        plan = self._get_school_plan(school)
        estimated = getattr(plan, 'sms_cost_per_unit', 0) or 0

        # Check allowance
        if not self.check_allowance(school, 'sms', 1):
            self.record_usage(
                school=school,
                resource_type='sms',
                action_type=action_type,
                status='exhausted',
                estimated_cost=0,
                student=student,
                user=user,
                invoice=invoice,
                payment=payment,
            )
            raise AllowanceExhausted(
                'sms',
                plan.monthly_sms_allowance,
                self._get_monthly_usage(school, 'sms'),
            )

        # Get provider
        provider = sms_service.get_sms_provider()
        sender_id = getattr(settings, 'TERMII_SENDER_ID', '') or 'SchoolOS'

        # Send
        result = provider.send(
            to=to, message=message, sender_id=sender_id
        )

        # Record usage
        self.record_usage(
            school=school,
            resource_type='sms',
            action_type=action_type,
            status='succeeded' if result.succeeded else 'failed',
            provider=provider.__class__.__name__,
            provider_reference=result.provider_reference,
            estimated_cost=estimated,
            actual_cost=result.cost,
            student=student,
            user=user,
            invoice=invoice,
            payment=payment,
        )

        if not result.succeeded:
            raise ValidationError({'sms': result.error})

        return True

    # OTP abuse controls (configurable per deployment; all server-side).
    OTP_WINDOW_MINUTES = 15     # per-user request window
    OTP_MAX_PER_WINDOW = 5      # requests allowed inside the window
    OTP_RESEND_COOLDOWN_SECONDS = 60  # minimum gap between two sends
    OTP_EXPIRY_MINUTES = 10

    def send_otp(self, user, school, purpose: str, channel: str = 'sms') -> 'OTPCode':
        """Generate and send an OTP code, with abuse controls.

        Order: per-user rate limit -> school OTP allowance -> create -> send.
        Every path that consumes a unit (succeeded or failed) writes a ledger
        row; a rejected request writes none because nothing was spent.
        """
        import hashlib
        import random
        from datetime import timedelta

        from django.db.models import Count, Max
        from django.utils import timezone

        from accounts.models import OTPCode

        now = timezone.now()
        window_start = now - timedelta(minutes=self.OTP_WINDOW_MINUTES)

        recent = OTPCode.objects.filter(
            user=user, purpose=purpose, created_at__gte=window_start,
        )
        stats = recent.aggregate(n=Count('id'), latest=Max('created_at'))
        if stats['n'] >= self.OTP_MAX_PER_WINDOW:
            raise ValidationError({
                'otp': 'Too many OTP requests. Try again later.',
            })
        if stats['latest'] and (
            now - stats['latest']
        ).total_seconds() < self.OTP_RESEND_COOLDOWN_SECONDS:
            raise ValidationError({
                'otp': 'Please wait before requesting another code.',
            })

        # Check allowance
        if not self.check_allowance(school, 'otp', 1):
            raise AllowanceExhausted(
                'otp',
                self._get_school_plan(school).monthly_otp_allowance,
                self._get_monthly_usage(school, 'otp'),
            )

        # Generate code
        code = f'{random.randint(100000, 999999):06d}'
        code_hash = hashlib.sha256(code.encode()).hexdigest()

        # Create OTP record
        otp = OTPCode.objects.create(
            user=user,
            school=school,
            code_hash=code_hash,
            purpose=purpose,
            channel=channel,
            expires_at=now + timedelta(minutes=self.OTP_EXPIRY_MINUTES),
        )

        estimated = getattr(
            self._get_school_plan(school), 'otp_cost_per_unit', 0,
        ) or 0

        # Send via SMS if requested
        if channel == 'sms' and user.phone:
            provider = sms_service.get_sms_provider()
            result = provider.send(
                to=user.phone,
                message=f'Your verification code is {code}. '
                        f'It expires in {self.OTP_EXPIRY_MINUTES} minutes.',
            )

            self.record_usage(
                school=school,
                resource_type='otp',
                action_type='otp_send',
                status='succeeded' if result.succeeded else 'failed',
                provider=provider.__class__.__name__,
                provider_reference=result.provider_reference,
                estimated_cost=estimated,
                actual_cost=result.cost,
                user=user,
            )

            if not result.succeeded:
                otp.status = 'failed'
                otp.save(update_fields=['status'])
                raise ValidationError({'otp': result.error})
        else:
            # No SMS channel: the code was still generated and must be paid for.
            self.record_usage(
                school=school,
                resource_type='otp',
                action_type='otp_send',
                status='succeeded',
                estimated_cost=estimated,
                user=user,
            )

        return otp

    def verify_otp(self, user, school, code: str, purpose: str) -> bool:
        """Verify an OTP code."""
        import hashlib
        from accounts.models import OTPCode
        from django.db.models import F
        from django.utils import timezone

        code_hash = hashlib.sha256(code.encode()).hexdigest()

        try:
            otp = OTPCode.objects.get(
                user=user,
                school=school,
                code_hash=code_hash,
                purpose=purpose,
                status='pending',
            )
        except OTPCode.DoesNotExist:
            # Increment attempts on existing pending OTP for rate limiting
            OTPCode.objects.filter(
                user=user, school=school, purpose=purpose, status='pending'
            ).update(attempts=F('attempts') + 1)
            raise ValidationError({'otp': 'Invalid or expired code.'})

        if otp.expires_at < timezone.now():
            otp.status = 'expired'
            otp.save(update_fields=['status'])
            raise ValidationError({'otp': 'Code has expired.'})

        if otp.attempts >= otp.max_attempts:
            otp.status = 'failed'
            otp.save(update_fields=['status'])
            raise ValidationError({'otp': 'Too many attempts. Request a new code.'})

        # Mark as verified
        otp.status = 'verified'
        otp.verified_at = timezone.now()
        otp.save(update_fields=['status', 'verified_at'])
        return True

    # ---------------------------------------------------------------------
    # AI operations
    # ---------------------------------------------------------------------
    def check_ai_allowance(self, school, operation_type: str) -> int:
        """Check AI allowance and return credits needed for the operation."""
        credits_needed = self.AI_COSTS.get(operation_type, 1)
        if not self.check_allowance(school, 'ai', credits_needed):
            raise ValidationError({
                'ai': f'Insufficient AI credits for {operation_type}. Need {credits_needed} credits.'
            })
        return credits_needed

    def record_ai_usage(
        self,
        school,
        operation_type: str,
        credits_used: int,
        action_type: str,
        user=None,
        result_sheet=None,
        status='succeeded',
    ):
        """Record AI usage."""
        self.record_usage(
            school=school,
            resource_type='ai',
            action_type=action_type,
            quantity=1,
            credits_used=credits_used,
            provider='internal',
            status=status,
            user=user,
            result_sheet=result_sheet,
        )


# Singleton instance
usage_service = UsageService()