"""Prepaid wallet billing: school wallets, student entitlements, SME alerts.

Money is held in kobo (integer minor units) on every field — never floats.
The `WalletTransaction` ledger is append-only: rows are created in their final
state, or move pending → final exactly once. Ordinary code must never update
or delete a settled row; use a reversing entry instead.
"""
from __future__ import annotations

from django.core.exceptions import ValidationError
from django.db import models


class Wallet(models.Model):
    """One prepaid balance per school. The only mutable money field."""

    school = models.OneToOneField(
        'schools.School', on_delete=models.CASCADE, related_name='wallet',
    )
    balance_kobo = models.BigIntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(balance_kobo__gte=0),
                name='wallet_balance_non_negative',
            ),
        ]

    def __str__(self):
        return f'Wallet({self.school_id}, {self.balance_kobo})'


class WalletTransaction(models.Model):
    """Immutable ledger entry. Created final, or pending → final exactly once."""

    class Direction(models.TextChoices):
        CREDIT = 'credit', 'Credit'
        DEBIT = 'debit', 'Debit'

    class Category(models.TextChoices):
        DEPOSIT = 'deposit', 'Wallet deposit'
        STUDENT_ACTIVATION = 'student_activation', 'Student access activation'
        STUDENT_RENEWAL = 'student_renewal', 'Student monthly renewal'
        SMS_ALERT = 'sms_alert', 'SME alert charge'
        REFUND = 'refund', 'Refund'
        ADJUSTMENT = 'adjustment', 'Authorized adjustment'

    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending'
        SUCCESS = 'success', 'Successful'
        FAILED = 'failed', 'Failed'
        REVERSED = 'reversed', 'Reversed'

    school = models.ForeignKey(
        'schools.School', on_delete=models.CASCADE, related_name='wallet_transactions',
    )
    reference = models.CharField(max_length=64, unique=True)
    direction = models.CharField(max_length=10, choices=Direction.choices)
    amount_kobo = models.PositiveBigIntegerField()
    category = models.CharField(max_length=20, choices=Category.choices)
    status = models.CharField(
        max_length=10, choices=Status.choices, default=Status.SUCCESS,
    )
    student = models.ForeignKey(
        'records.Student', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='wallet_transactions',
    )
    message_reference = models.CharField(max_length=64, blank=True, default='')
    provider_reference = models.CharField(max_length=100, blank=True, default='')
    balance_before_kobo = models.BigIntegerField(default=0)
    balance_after_kobo = models.BigIntegerField(default=0)
    description = models.CharField(max_length=255, blank=True, default='')
    created_by = models.ForeignKey(
        'accounts.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='wallet_transactions',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at', '-id']
        indexes = [
            models.Index(fields=['school', '-created_at']),
            models.Index(fields=['school', 'category']),
            models.Index(fields=['school', 'status']),
            models.Index(fields=['student', '-created_at']),
            # Transaction lists filter school + category, newest first.
            models.Index(fields=['school', 'category', '-created_at']),
        ]

    def save(self, *args, **kwargs):
        # Append-only ledger: settled rows are frozen. Two transitions exist:
        # pending → final (success/failed), and success → reversed (refunds,
        # which always pair with a new credit entry). Anything else is a bug.
        if self.pk is not None:
            update_fields = kwargs.get('update_fields')
            current = WalletTransaction.objects.filter(pk=self.pk).values_list(
                'status', flat=True,
            ).first()
            allowed = (
                update_fields is not None
                and set(update_fields) == {'status'}
                and (
                    (
                        current == self.Status.PENDING
                        and self.status in (
                            self.Status.SUCCESS, self.Status.FAILED,
                            self.Status.REVERSED,
                        )
                    )
                    or (
                        current == self.Status.SUCCESS
                        and self.status == self.Status.REVERSED
                    )
                )
            )
            if not allowed:
                raise ValidationError(
                    'Wallet transactions are immutable once settled.',
                )
        super().save(*args, **kwargs)

    def __str__(self):
        return f'{self.reference} ({self.direction} {self.amount_kobo})'


class StudentEntitlement(models.Model):
    """One paid monthly access period for one student. Rolling month from activation."""

    student = models.ForeignKey(
        'records.Student', on_delete=models.CASCADE, related_name='entitlements',
    )
    school = models.ForeignKey(
        'schools.School', on_delete=models.CASCADE, related_name='entitlements',
    )
    period_start = models.DateField()
    period_end = models.DateField()
    amount_kobo = models.PositiveBigIntegerField()
    # Complimentary access: granted free by a platform manager (reason +
    # granter recorded, never a fake payment). amount stays 0.
    is_complimentary = models.BooleanField(default=False)
    comp_reason = models.CharField(max_length=255, blank=True, default='')
    granted_by = models.ForeignKey(
        'accounts.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='granted_complimentary_access',
    )
    wallet_transaction = models.ForeignKey(
        WalletTransaction, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='entitlements',
    )
    renewed_from = models.ForeignKey(
        'self', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='renewals',
    )
    created_by = models.ForeignKey(
        'accounts.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='granted_entitlements',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-period_end', '-id']
        constraints = [
            # One charge per student per period: concurrent activations for the
            # same window collide here instead of double-charging.
            models.UniqueConstraint(
                fields=['student', 'period_start'],
                name='unique_entitlement_per_student_period',
            ),
        ]
        indexes = [
            models.Index(fields=['school', 'period_end']),
            models.Index(fields=['student', '-period_end']),
        ]

    def __str__(self):
        return f'{self.student_id} {self.period_start}→{self.period_end}'


class PlatformPricing(models.Model):
    """Singleton platform billing policy, edited only by the Platform Manager."""

    student_price_kobo = models.PositiveBigIntegerField(default=11500)
    sms_price_kobo = models.PositiveBigIntegerField(default=1000)
    grace_days = models.PositiveIntegerField(default=3)
    auto_renew = models.BooleanField(default=True)
    sms_enabled_global = models.BooleanField(default=True)
    # When True, unpaid students (no live or grace-period entitlement) are
    # blocked from student features until staff activate them. Staff unblock
    # via the activation endpoint, which debits the wallet atomically.
    enforce_student_access = models.BooleanField(default=True)
    min_deposit_kobo = models.PositiveBigIntegerField(default=10000)
    max_deposit_kobo = models.PositiveBigIntegerField(null=True, blank=True)
    price_changed_at = models.DateTimeField(null=True, blank=True)
    changed_by = models.ForeignKey(
        'accounts.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='pricing_changes',
    )
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return 'PlatformPricing'


class SchoolMessaging(models.Model):
    """Per-school SME alert switches. Platform block always wins."""

    school = models.OneToOneField(
        'schools.School', on_delete=models.CASCADE, related_name='messaging',
    )
    school_enabled = models.BooleanField(default=True)
    platform_blocked = models.BooleanField(default=False)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f'Messaging({self.school_id})'


class WalletDeposit(models.Model):
    """One wallet top-up attempt via Paystack. Credited only after verification."""

    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending'
        SUCCESS = 'success', 'Successful'
        FAILED = 'failed', 'Failed'

    school = models.ForeignKey(
        'schools.School', on_delete=models.CASCADE, related_name='wallet_deposits',
    )
    reference = models.CharField(max_length=64, unique=True)
    amount_kobo = models.PositiveBigIntegerField()
    currency = models.CharField(max_length=8, default='NGN')
    paystack_reference = models.CharField(max_length=100, blank=True, default='')
    access_code = models.CharField(max_length=100, blank=True, default='')
    authorization_url = models.URLField(blank=True, default='')
    status = models.CharField(
        max_length=10, choices=Status.choices, default=Status.PENDING,
    )
    raw = models.JSONField(default=dict, blank=True)
    created_by = models.ForeignKey(
        'accounts.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='wallet_deposits',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at', '-id']
        indexes = [
            models.Index(fields=['school', '-created_at']),
            models.Index(fields=['status']),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['paystack_reference'],
                condition=~models.Q(paystack_reference=''),
                name='unique_wallet_deposit_paystack_reference',
            ),
        ]

    def __str__(self):
        return f'{self.reference} ({self.status})'


class SmsAlert(models.Model):
    """One billable SME alert. Customer charge and provider cost tracked separately."""

    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending'
        SENT = 'sent', 'Sent'
        PROVIDER_REJECTED = 'provider_rejected', 'Rejected by provider'
        FAILED = 'failed', 'Failed'
        REFUNDED = 'refunded', 'Refunded'

    school = models.ForeignKey(
        'schools.School', on_delete=models.CASCADE, related_name='sms_alerts',
    )
    # Idempotency key: client-supplied or generated. Retries reuse the row,
    # so neither the customer charge nor the provider submission duplicates.
    reference = models.CharField(max_length=64, unique=True)
    recipient = models.CharField(max_length=32)
    message = models.TextField()
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.PENDING,
    )
    customer_kobo = models.PositiveBigIntegerField(default=0)
    # Null means unknown — Termii does not return per-message cost. Never
    # invent a provider cost; margin reports treat null as unknown.
    provider_cost_kobo = models.PositiveIntegerField(null=True, blank=True)
    provider_reference = models.CharField(max_length=100, blank=True, default='')
    provider_error = models.CharField(max_length=255, blank=True, default='')
    wallet_transaction = models.ForeignKey(
        WalletTransaction, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='sms_alerts',
    )
    created_by = models.ForeignKey(
        'accounts.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='sms_alerts',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at', '-id']
        indexes = [
            models.Index(fields=['school', '-created_at']),
            models.Index(fields=['school', 'status']),
        ]

    def __str__(self):
        return f'{self.reference} ({self.status})'
