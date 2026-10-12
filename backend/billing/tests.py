"""Wallet billing, student access, renewals, grace and SME alert acceptance tests.

Covers the billing acceptance criteria end to end: deposits credit exactly
once, per-student ₦115 debits with a ₦500→4-active-₦40 story, renewals that
are independent per student, grace behaviour, gated SME alerts with refunds,
tenant isolation and audited adjustments.
"""
from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from django.core.management import call_command
from django.db import IntegrityError
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.exceptions import ValidationError
from rest_framework.test import APIClient

from accounts.models import User
from billing import services
from billing.models import (
    PlatformPricing,
    SchoolMessaging,
    SmsAlert,
    StudentEntitlement,
    Wallet,
    WalletDeposit,
    WalletTransaction,
)
from records.models import Student
from records.tests.base import SchoolTestCase
from schools.models import AuditLog, School


def _ok_verify(reference, amount=0, currency='NGN'):
    return {
        'status': 'success',
        'reference': reference,
        'amount': amount,
        'currency': currency,
        'channel': 'card',
    }


class WalletDepositTests(SchoolTestCase):
    def setUp(self):
        super().setUp()
        self.auth(self.admin)

    def test_deposit_below_minimum_is_rejected(self):
        response = self.client.post(
            '/api/v1/billing/deposits/', {'amountKobo': 5000}, format='json',
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(WalletDeposit.objects.count(), 0)

    def test_unverified_payment_does_not_credit(self):
        with patch(
            'billing.views.paystack_client.initialize_transaction',
            return_value={
                'access_code': 'ac', 'authorization_url': 'https://checkout.paystack.com/ac',
                'reference': 'gw-1',
            },
        ):
            start = self.client.post(
                '/api/v1/billing/deposits/', {'amountKobo': 50000}, format='json',
            )
        self.assertEqual(start.status_code, 200)
        reference = start.data['reference']
        with patch(
            'billing.views.paystack_client.verify_transaction',
            return_value={'status': 'abandoned', 'reference': reference},
        ):
            verify = self.client.get(f'/api/v1/billing/deposits/verify/{reference}/')
        self.assertEqual(verify.data['status'], 'failed')
        self.assertEqual(services.get_wallet(self.school).balance_kobo, 0)

    @override_settings(PAYSTACK_SECRET_KEY='test-secret')
    def test_verified_payment_credits_exactly_once(self):
        with patch(
            'billing.views.paystack_client.initialize_transaction',
            return_value={
                'access_code': 'ac', 'authorization_url': 'https://checkout.paystack.com/ac',
                'reference': 'gw-1',
            },
        ):
            start = self.client.post(
                '/api/v1/billing/deposits/', {'amountKobo': 50000}, format='json',
            )
        reference = start.data['reference']
        with patch(
            'billing.views.paystack_client.verify_transaction',
            return_value=_ok_verify('gw-1', amount=50000),
        ):
            first = self.client.get(f'/api/v1/billing/deposits/verify/{reference}/')
            second = self.client.get(f'/api/v1/billing/deposits/verify/{reference}/')
        self.assertEqual(first.data['status'], 'success')
        self.assertEqual(second.data['status'], 'success')
        self.assertEqual(services.get_wallet(self.school).balance_kobo, 50000)
        credits = WalletTransaction.objects.filter(
            school=self.school,
            category=WalletTransaction.Category.DEPOSIT,
            status=WalletTransaction.Status.SUCCESS,
        )
        self.assertEqual(credits.count(), 1)
        entry = credits.get()
        self.assertEqual(entry.amount_kobo, 50000)
        self.assertEqual(entry.balance_before_kobo, 0)
        self.assertEqual(entry.balance_after_kobo, 50000)

    @override_settings(PAYSTACK_SECRET_KEY='test-secret')
    def test_duplicate_webhook_does_not_double_credit(self):
        import hashlib
        import hmac
        import json

        with patch(
            'billing.views.paystack_client.initialize_transaction',
            return_value={
                'access_code': 'ac', 'authorization_url': 'https://checkout.paystack.com/ac',
                'reference': 'gw-1',
            },
        ):
            start = self.client.post(
                '/api/v1/billing/deposits/', {'amountKobo': 50000}, format='json',
            )
        reference = start.data['reference']

        def _post():
            body = json.dumps({
                'event': 'charge.success',
                'data': {
                    'status': 'success', 'reference': reference,
                    'amount': 50000, 'currency': 'NGN',
                },
            })
            signature = hmac.new(
                b'test-secret', body.encode('utf-8'), hashlib.sha512,
            ).hexdigest()
            return APIClient().post(
                '/api/v1/billing/deposits/webhook/', body,
                content_type='application/json',
                HTTP_X_PAYSTACK_SIGNATURE=signature,
            )

        with patch(
            'billing.views.paystack_client.verify_transaction',
            return_value=_ok_verify('gw-1', amount=50000),
        ) as verify:
            first = _post()
            second = _post()
        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        verify.assert_called_once()
        self.assertEqual(services.get_wallet(self.school).balance_kobo, 50000)

    def test_ledger_is_immutable_once_settled(self):
        from django.core.exceptions import ValidationError as DjangoValidationError
        services.credit_wallet(
            self.school, 50000, category=WalletTransaction.Category.DEPOSIT,
        )
        entry = WalletTransaction.objects.get(school=self.school)
        entry.description = 'rewritten history'
        with self.assertRaises(DjangoValidationError):
            entry.save()


class StudentBillingTests(SchoolTestCase):
    def setUp(self):
        super().setUp()
        self.auth(self.admin)
        services.credit_wallet(
            self.school, 50000, category=WalletTransaction.Category.DEPOSIT,
            description='Test funding ₦500.',
        )

    def _activate(self, student):
        return self.client.post(
            f'/api/v1/billing/students/{student.public_id}/activate/',
        )

    def test_activation_deducts_default_price(self):
        student = self.make_student(admission_number='W1')
        response = self._activate(student)
        self.assertEqual(response.status_code, 200, response.data)
        self.assertTrue(response.data['created'])
        self.assertEqual(response.data['amountKobo'], 11500)
        self.assertEqual(services.get_wallet(self.school).balance_kobo, 38500)

    def test_500_naira_activates_four_leaving_40(self):
        students = [self.make_student(admission_number=f'W{i}') for i in range(4)]
        for student in students:
            response = self._activate(student)
            self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(services.get_wallet(self.school).balance_kobo, 4000)
        fifth = self.make_student(admission_number='W5')
        denied = self._activate(fifth)
        self.assertEqual(denied.status_code, 402)
        self.assertEqual(denied.data['requiredKobo'], 11500)
        self.assertEqual(denied.data['availableKobo'], 4000)
        self.assertFalse(
            StudentEntitlement.objects.filter(student=fifth).exists(),
        )

    def test_paid_student_is_not_charged_twice(self):
        student = self.make_student(admission_number='W1')
        first = self._activate(student)
        second = self._activate(student)
        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertFalse(second.data['created'])
        self.assertEqual(services.get_wallet(self.school).balance_kobo, 38500)
        self.assertEqual(
            StudentEntitlement.objects.filter(student=student).count(), 1,
        )

    def test_read_only_views_do_not_charge(self):
        before = WalletTransaction.objects.filter(school=self.school).count()
        listed = self.client.get('/api/v1/billing/students/')
        self.assertEqual(listed.status_code, 200)
        self.assertEqual(
            WalletTransaction.objects.filter(school=self.school).count(), before,
        )

    def test_duplicate_period_is_rejected_by_the_database(self):
        student = self.make_student(admission_number='W1')
        self._activate(student)
        entitlement = StudentEntitlement.objects.get(student=student)
        with self.assertRaises(IntegrityError):
            StudentEntitlement.objects.create(
                student=student, school=self.school,
                period_start=entitlement.period_start,
                period_end=entitlement.period_end,
                amount_kobo=11500,
            )

    def test_teacher_cannot_activate(self):
        self.auth(self.teacher)
        student = self.make_student(admission_number='W1')
        response = self._activate(student)
        self.assertEqual(response.status_code, 403)

    def test_other_school_student_is_not_found(self):
        other = Student.objects.create(
            school=self.other_school, admission_number='RVC/T/X1',
            first_name='Other', last_name='Child', gender=Student.Gender.FEMALE,
            class_name='JSS 1',
        )
        response = self._activate(other)
        self.assertEqual(response.status_code, 404)

    def test_grace_and_expiry_labels(self):
        pricing = services.get_pricing()
        student = self.make_student(admission_number='W1')
        today = timezone.localdate()
        active = StudentEntitlement.objects.create(
            student=student, school=self.school,
            period_start=today - timedelta(days=29), period_end=today + timedelta(days=1),
            amount_kobo=11500,
        )
        grace = StudentEntitlement.objects.create(
            student=self.make_student(admission_number='W2'), school=self.school,
            period_start=today - timedelta(days=32), period_end=today - timedelta(days=2),
            amount_kobo=11500,
        )
        expired = StudentEntitlement.objects.create(
            student=self.make_student(admission_number='W3'), school=self.school,
            period_start=today - timedelta(days=60), period_end=today - timedelta(days=10),
            amount_kobo=11500,
        )
        self.assertEqual(
            services.entitlement_status(active, grace_days=pricing.grace_days),
            'ExpiringSoon',
        )
        self.assertEqual(
            services.entitlement_status(grace, grace_days=pricing.grace_days),
            'GracePeriod',
        )
        self.assertEqual(
            services.entitlement_status(expired, grace_days=pricing.grace_days),
            'Expired',
        )
        # Expiry never deletes the student or their record.
        self.assertTrue(Student.objects.filter(pk=expired.student_id).exists())


class RenewalSweepTests(SchoolTestCase):
    def test_renewals_are_independent_when_funds_run_out(self):
        services.credit_wallet(
            self.school, 20000, category=WalletTransaction.Category.DEPOSIT,
        )
        today = timezone.localdate()
        olds = []
        for i in range(2):
            student = self.make_student(admission_number=f'R{i}')
            olds.append(StudentEntitlement.objects.create(
                student=student, school=self.school,
                period_start=today - timedelta(days=31),
                period_end=today - timedelta(days=1),
                amount_kobo=11500,
            ))
        call_command('sweep_renewals', f'--school={self.school.pk}')
        renewed = StudentEntitlement.objects.filter(
            school=self.school, renewed_from__isnull=False,
        )
        # ₦200 covers exactly one ₦115 renewal, not two.
        self.assertEqual(renewed.count(), 1)
        self.assertEqual(services.get_wallet(self.school).balance_kobo, 8500)
        # Successful renewal stays valid; the other student is untouched.
        self.assertEqual(
            StudentEntitlement.objects.filter(
                student=olds[0].student,
            ).count()
            + StudentEntitlement.objects.filter(student=olds[1].student).count(),
            3,
        )

    def test_rerun_does_not_double_renew(self):
        services.credit_wallet(
            self.school, 50000, category=WalletTransaction.Category.DEPOSIT,
        )
        today = timezone.localdate()
        student = self.make_student(admission_number='R1')
        StudentEntitlement.objects.create(
            student=student, school=self.school,
            period_start=today - timedelta(days=31),
            period_end=today - timedelta(days=1),
            amount_kobo=11500,
        )
        call_command('sweep_renewals', f'--school={self.school.pk}')
        call_command('sweep_renewals', f'--school={self.school.pk}')
        self.assertEqual(
            StudentEntitlement.objects.filter(student=student).count(), 2,
        )


class SmsAlertTests(SchoolTestCase):
    def setUp(self):
        super().setUp()
        self.auth(self.admin)
        services.credit_wallet(
            self.school, 50000, category=WalletTransaction.Category.DEPOSIT,
        )

    def _send(self, **overrides):
        payload = {
            'recipient': '+2348000000001',
            'message': 'Fee reminder for tomorrow.',
            'reference': 'SMS-TEST-1',
        }
        payload.update(overrides)
        return self.client.post('/api/v1/billing/alerts/', payload, format='json')

    def _ok_provider(self):
        from records.services import sms as sms_module

        class _Provider:
            def send(self, to, message, sender_id=None):
                return sms_module.SMSResult(
                    succeeded=True, provider_reference='termii-123', cost=0,
                )

        return patch.object(sms_module, 'get_sms_provider', return_value=_Provider())

    def test_global_switch_off_blocks_everyone(self):
        pricing = services.get_pricing()
        pricing.sms_enabled_global = False
        pricing.save()
        with self._ok_provider():
            response = self._send()
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.data['reasonCode'], 'global_disabled')

    def test_platform_block_beats_school_setting(self):
        messaging, _ = SchoolMessaging.objects.get_or_create(school=self.school)
        messaging.platform_blocked = True
        messaging.save()
        with self._ok_provider():
            response = self._send()
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.data['reasonCode'], 'school_blocked')

    def test_school_admin_can_disable_own_alerts(self):
        response = self.client.patch(
            '/api/v1/billing/messaging/', {'schoolEnabled': False}, format='json',
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.data['schoolEnabled'])
        with self._ok_provider():
            blocked = self._send()
        self.assertEqual(blocked.status_code, 403)

    def test_insufficient_funds_prevents_send(self):
        wallet = services.get_wallet(self.school)
        wallet.balance_kobo = 500
        wallet.save()
        with self._ok_provider():
            response = self._send()
        self.assertEqual(response.status_code, 402)
        self.assertEqual(SmsAlert.objects.count(), 0)

    def test_legitimate_alert_charges_configured_price(self):
        with self._ok_provider():
            response = self._send()
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data['customer_kobo'], 1000)
        self.assertIsNone(response.data['provider_cost_kobo'])
        self.assertEqual(services.get_wallet(self.school).balance_kobo, 49000)
        entry = WalletTransaction.objects.get(
            message_reference='SMS-TEST-1',
            category=WalletTransaction.Category.SMS_ALERT,
        )
        self.assertEqual(entry.amount_kobo, 1000)

    def test_retry_with_same_reference_does_not_recharge(self):
        with self._ok_provider():
            first = self._send()
            second = self._send()
        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 201)
        self.assertEqual(
            WalletTransaction.objects.filter(
                message_reference='SMS-TEST-1',
                category=WalletTransaction.Category.SMS_ALERT,
            ).count(),
            1,
        )
        self.assertEqual(services.get_wallet(self.school).balance_kobo, 49000)

    def test_provider_rejection_refunds(self):
        from records.services import sms as sms_module

        class _Rejecting:
            def send(self, to, message, sender_id=None):
                return sms_module.SMSResult(
                    succeeded=False, error='Insufficient Termii balance',
                )

        with patch.object(
            sms_module, 'get_sms_provider', return_value=_Rejecting(),
        ):
            response = self._send()
        self.assertEqual(response.status_code, 400)
        alert = SmsAlert.objects.get(reference='SMS-TEST-1')
        self.assertEqual(alert.status, SmsAlert.Status.REFUNDED)
        # Charge refunded in full: balance back to ₦500.
        self.assertEqual(services.get_wallet(self.school).balance_kobo, 50000)


class PlatformBillingTests(SchoolTestCase):
    def _platform(self):
        platform = User.objects.create_user(
            email='platform@example.com', password='Strong-Pass-1!',
            first_name='Platform', last_name='Manager',
            role=User.Role.PLATFORM_MANAGER, school=None,
            is_active=True, is_verified=True,
        )
        self.client.force_authenticate(platform)
        return platform

    def test_school_admin_cannot_change_pricing(self):
        self.auth(self.admin)
        response = self.client.patch(
            '/api/v1/billing/platform/pricing/',
            {'studentPriceKobo': 20000}, format='json',
        )
        self.assertEqual(response.status_code, 403)

    def test_platform_can_change_pricing_with_audit(self):
        self._platform()
        response = self.client.patch(
            '/api/v1/billing/platform/pricing/',
            {'studentPriceKobo': 20000, 'graceDays': 5}, format='json',
        )
        self.assertEqual(response.status_code, 200, response.data)
        pricing = PlatformPricing.objects.get(pk=1)
        self.assertEqual(pricing.student_price_kobo, 20000)
        self.assertEqual(pricing.grace_days, 5)
        self.assertTrue(
            AuditLog.objects.filter(action='billing.pricing.updated').exists(),
        )

    def test_pricing_validation(self):
        self._platform()
        response = self.client.patch(
            '/api/v1/billing/platform/pricing/',
            {'graceDays': 99}, format='json',
        )
        self.assertEqual(response.status_code, 400)

    def test_cross_school_wallet_isolation(self):
        services.credit_wallet(
            self.school, 50000, category=WalletTransaction.Category.DEPOSIT,
        )
        self.auth(self.other_admin)
        own = self.client.get('/api/v1/billing/wallet/')
        self.assertEqual(own.status_code, 200)
        self.assertEqual(own.data['balanceKobo'], 0)
        txns = self.client.get('/api/v1/billing/transactions/')
        self.assertEqual(txns.data['count'], 0)

    def test_manual_adjustment_requires_reason_and_audits(self):
        self._platform()
        denied = self.client.post(
            '/api/v1/billing/platform/adjustments/',
            {'schoolId': str(self.school.pk), 'amountKobo': 10000, 'reason': ''},
            format='json',
        )
        self.assertEqual(denied.status_code, 400)
        allowed = self.client.post(
            '/api/v1/billing/platform/adjustments/',
            {
                'schoolId': str(self.school.pk), 'amountKobo': 10000,
                'reason': 'Goodwill credit for outage.',
            },
            format='json',
        )
        self.assertEqual(allowed.status_code, 201, allowed.data)
        self.assertEqual(services.get_wallet(self.school).balance_kobo, 10000)
        self.assertTrue(
            AuditLog.objects.filter(action='wallet.adjustment').exists(),
        )

    def test_messaging_overview_separates_charges_from_costs(self):
        self._platform()
        response = self.client.get('/api/v1/billing/platform/messaging/')
        self.assertEqual(response.status_code, 200)
        self.assertIn('chargedKobo', response.data['alerts'])
        self.assertIn('unknownCostCount', response.data['alerts'])


class EntitlementModelTests(TestCase):
    def test_school_admin_role_value_exists(self):
        self.assertTrue(User.Role.SCHOOL_ADMIN)
        self.assertTrue(hasattr(School, 'wallet'))
