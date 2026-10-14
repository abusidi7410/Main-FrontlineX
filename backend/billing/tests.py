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
from django.test import TestCase, TransactionTestCase, override_settings, skipUnlessDBFeature
from django.utils import timezone
from rest_framework.exceptions import ValidationError
from rest_framework.test import APIClient

from accounts.models import User
from billing import services
from billing.models import (
    PlatformPricing,
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

    def test_student_list_returns_public_ids_usable_for_activation(self):
        student = self.make_student(admission_number='W1')
        listed = self.client.get('/api/v1/billing/students/')
        self.assertEqual(listed.status_code, 200)
        row = next(
            r for r in listed.data['results']
            if r['studentId'] == str(student.public_id)
        )
        # The list id must be the public UUID the activate endpoint expects —
        # numeric pks 404 there, which used to break wallet activation.
        self.assertEqual(row['studentId'], str(student.public_id))
        self.assertIn('summary', listed.data)
        activated = self.client.post(
            f"/api/v1/billing/students/{row['studentId']}/activate/",
        )
        self.assertEqual(activated.status_code, 200, activated.data)
        self.assertTrue(activated.data['created'])

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
    """SME messaging is retired: sends are refused, history stays readable."""

    def setUp(self):
        super().setUp()
        self.auth(self.admin)
        services.credit_wallet(
            self.school, 50000, category=WalletTransaction.Category.DEPOSIT,
        )

    def test_send_is_disabled_platform_wide(self):
        before = services.get_wallet(self.school).balance_kobo
        response = self.client.post(
            '/api/v1/billing/alerts/',
            {
                'recipient': '+2348000000001',
                'message': 'Fee reminder for tomorrow.',
                'reference': 'SMS-TEST-1',
            },
            format='json',
        )
        self.assertEqual(response.status_code, 403, response.data)
        self.assertEqual(response.data['reasonCode'], 'sms_disabled')
        self.assertEqual(services.get_wallet(self.school).balance_kobo, before)
        self.assertFalse(SmsAlert.objects.filter(reference='SMS-TEST-1').exists())

    def test_school_toggle_is_disabled(self):
        response = self.client.patch(
            '/api/v1/billing/messaging/', {'schoolEnabled': False}, format='json',
        )
        self.assertEqual(response.status_code, 403, response.data)

    def test_alert_history_stays_readable(self):
        response = self.client.get('/api/v1/billing/alerts/history/')
        self.assertEqual(response.status_code, 200, response.data)


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

    def test_platform_transaction_trace_sees_every_school(self):
        services.credit_wallet(
            self.school, 50000, category=WalletTransaction.Category.DEPOSIT,
            description='School A deposit',
        )
        services.credit_wallet(
            self.other_school, 30000, category=WalletTransaction.Category.DEPOSIT,
            description='School B deposit',
        )
        services.debit_wallet(
            self.other_school, 11500,
            category=WalletTransaction.Category.STUDENT_ACTIVATION,
            description='School B activation', what='student access',
        )
        self._platform()
        response = self.client.get('/api/v1/billing/platform/transactions/')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['count'], 3)
        names = {row['schoolName'] for row in response.data['results']}
        self.assertEqual(names, {'Success Academy', 'Rival College'})
        self.assertEqual(response.data['summary']['creditsKobo'], 80000)
        self.assertEqual(response.data['summary']['debitsKobo'], 11500)

    def test_platform_transaction_trace_filters_by_school(self):
        services.credit_wallet(
            self.school, 50000, category=WalletTransaction.Category.DEPOSIT,
        )
        services.credit_wallet(
            self.other_school, 30000, category=WalletTransaction.Category.DEPOSIT,
        )
        self._platform()
        response = self.client.get(
            '/api/v1/billing/platform/transactions/',
            {'school': str(self.other_school.pk)},
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['count'], 1)
        self.assertEqual(
            response.data['results'][0]['schoolName'], 'Rival College',
        )
        searched = self.client.get(
            '/api/v1/billing/platform/transactions/', {'search': 'Rival'},
        )
        self.assertEqual(searched.data['count'], 1)

    def test_platform_transaction_trace_is_platform_only(self):
        self.auth(self.admin)
        response = self.client.get('/api/v1/billing/platform/transactions/')
        self.assertEqual(response.status_code, 403)
        self.client.force_authenticate(user=None)
        response = self.client.get('/api/v1/billing/platform/transactions/')
        self.assertEqual(response.status_code, 401)


class AccessEnforcementTests(SchoolTestCase):
    """Unpaid students are blocked from paid features until staff activate them.

    Enforcement is on here (the shared base runs unenforced). Each block
    carries a reason code and figures; activation unblocks immediately.
    """

    def setUp(self):
        super().setUp()
        pricing = PlatformPricing.objects.get(pk=1)
        pricing.enforce_student_access = True
        pricing.save(update_fields=['enforce_student_access'])
        self.auth(self.admin)
        services.credit_wallet(
            self.school, 50000, category=WalletTransaction.Category.DEPOSIT,
        )

    def test_student_detail_is_blocked_until_activation(self):
        student = self.make_student(admission_number='B1')
        blocked = self.client.get(f'/api/v1/students/{student.public_id}/')
        self.assertEqual(blocked.status_code, 400)
        self.assertEqual(
            blocked.data['fieldErrors']['reasonCode'], 'student_access_required',
        )
        activated = self.client.post(
            f'/api/v1/billing/students/{student.public_id}/activate/',
        )
        self.assertEqual(activated.status_code, 200)
        allowed = self.client.get(f'/api/v1/students/{student.public_id}/')
        self.assertEqual(allowed.status_code, 200)

    def test_result_recording_auto_activates_and_debits_once(self):
        from records.models import Enrollment
        from records.services import results as results_service
        from billing.models import Wallet
        student = self.make_student(admission_number='B1')
        Enrollment.objects.create(
            school=self.school, student=student,
            academic_session=self.session, class_obj=self.jss1,
            status=Enrollment.Status.ACTIVE,
        )
        sheet = results_service.create_sheet(
            school=self.school, academic_session=self.session,
            class_obj=self.jss1, subject='Mathematics',
            assessment='First Term Test',
        )
        before = Wallet.objects.get(school=self.school).balance_kobo
        updated = results_service.record_scores(
            sheet, {str(student.public_id): 75},
        )
        self.assertEqual(updated, 1)
        # Auto-debited exactly once: second write reuses the entitlement.
        pricing = PlatformPricing.objects.get(pk=1)
        after = Wallet.objects.get(school=self.school).balance_kobo
        self.assertEqual(before - after, pricing.student_price_kobo)
        updated_again = results_service.record_scores(
            sheet, {str(student.public_id): 80},
        )
        self.assertEqual(updated_again, 1)
        self.assertEqual(
            Wallet.objects.get(school=self.school).balance_kobo, after,
        )

    def test_result_recording_without_funds_reports_insufficient(self):
        from records.models import Enrollment
        from records.services import results as results_service
        from billing.models import Wallet
        from billing import services as billing_services
        Wallet.objects.filter(school=self.school).update(balance_kobo=0)
        student = self.make_student(admission_number='B1')
        Enrollment.objects.create(
            school=self.school, student=student,
            academic_session=self.session, class_obj=self.jss1,
            status=Enrollment.Status.ACTIVE,
        )
        sheet = results_service.create_sheet(
            school=self.school, academic_session=self.session,
            class_obj=self.jss1, subject='Mathematics',
            assessment='First Term Test',
        )
        with self.assertRaises(billing_services.InsufficientFunds):
            results_service.record_scores(
                sheet, {str(student.public_id): 75},
            )

    def test_attendance_auto_activates_funded_students(self):
        from records.services import attendance as attendance_service
        from records.models import AcademicSession, Enrollment
        paid = self.make_student(admission_number='B1')
        unpaid = self.make_student(admission_number='B2')
        services.activate_student(self.school, paid, actor=self.admin)
        for student in (paid, unpaid):
            Enrollment.objects.create(
                school=self.school, student=student,
                academic_session=self.session, class_obj=self.jss1,
                status=Enrollment.Status.ACTIVE,
            )
        # A school day inside the paid student's entitlement window.
        day = timezone.localdate()
        for _ in range(14):
            if attendance_service.is_school_day(self.school, day):
                break
            day += timedelta(days=1)
        result = attendance_service.submit_register(
            user=self.admin, school=self.school, class_obj=self.jss1,
            day=day,
            records=[
                {'studentId': str(paid.public_id), 'status': 'present'},
                {'studentId': str(unpaid.public_id), 'status': 'present'},
            ],
        )
        # Funded wallet: the unpaid student is auto-activated, both saved.
        self.assertEqual(result.saved, 2)
        self.assertEqual(result.skipped, 0)
        self.assertTrue(services.student_has_access(unpaid))

    def test_attendance_with_empty_wallet_is_blocked_with_message(self):
        from records.services import attendance as attendance_service
        from records.models import AcademicSession, Enrollment
        from billing.models import Wallet
        from billing import services as billing_services
        Wallet.objects.filter(school=self.school).update(balance_kobo=0)
        unpaid = self.make_student(admission_number='B2')
        Enrollment.objects.create(
            school=self.school, student=unpaid,
            academic_session=self.session, class_obj=self.jss1,
            status=Enrollment.Status.ACTIVE,
        )
        day = timezone.localdate()
        for _ in range(14):
            if attendance_service.is_school_day(self.school, day):
                break
            day += timedelta(days=1)
        with self.assertRaises(billing_services.UnfundedStudents):
            attendance_service.submit_register(
                user=self.admin, school=self.school, class_obj=self.jss1,
                day=day,
                records=[
                    {'studentId': str(unpaid.public_id), 'status': 'present'},
                ],
            )

    def test_attendance_with_full_cover_marks_and_charges_once(self):
        from records.services import attendance as attendance_service
        from records.models import AcademicSession, Enrollment
        from billing.models import Wallet
        students = [self.make_student(admission_number=f'F{i}') for i in range(2)]
        for student in students:
            Enrollment.objects.create(
                school=self.school, student=student,
                academic_session=self.session, class_obj=self.jss1,
                status=Enrollment.Status.ACTIVE,
            )
        day = timezone.localdate()
        for _ in range(14):
            if attendance_service.is_school_day(self.school, day):
                break
            day += timedelta(days=1)
        result = attendance_service.submit_register(
            user=self.admin, school=self.school, class_obj=self.jss1,
            day=day,
            records=[
                {'studentId': str(s.public_id), 'status': 'present'} for s in students
            ],
        )
        self.assertEqual(result.saved, 2)
        self.assertEqual(result.skipped, 0)
        self.assertEqual(len(result.activated), 2)
        self.assertEqual(result.charged_kobo, 23000)
        self.assertEqual(
            Wallet.objects.get(school=self.school).balance_kobo, 50000 - 23000,
        )

    def test_result_recording_names_the_unpaid_student(self):
        from records.models import Enrollment
        from records.services import results as results_service
        from billing.models import Wallet
        from billing import services as billing_services
        Wallet.objects.filter(school=self.school).update(balance_kobo=0)
        student = self.make_student(admission_number='N1')
        Enrollment.objects.create(
            school=self.school, student=student,
            academic_session=self.session, class_obj=self.jss1,
            status=Enrollment.Status.ACTIVE,
        )
        sheet = results_service.create_sheet(
            school=self.school, academic_session=self.session,
            class_obj=self.jss1, subject='Mathematics',
            assessment='First Term Test',
        )
        with self.assertRaises(billing_services.InsufficientFunds) as raised:
            results_service.record_scores(
                sheet, {str(student.public_id): 75},
            )
        self.assertIn('Test Student', raised.exception.detail['wallet'])
        self.assertIn('Fund the wallet', raised.exception.detail['wallet'])

    def test_partial_funds_block_submit_and_name_the_students(self):
        from records.services import attendance as attendance_service
        from records.models import Enrollment
        from billing.models import Wallet
        from billing import services as billing_services
        # ₦300 covers 2 of 3 at ₦115 — fail closed: nothing marked, nothing charged.
        Wallet.objects.filter(school=self.school).update(balance_kobo=30000)
        students = [self.make_student(admission_number=f'P{i}') for i in range(3)]
        for student in students:
            Enrollment.objects.create(
                school=self.school, student=student,
                academic_session=self.session, class_obj=self.jss1,
                status=Enrollment.Status.ACTIVE,
            )
        day = timezone.localdate()
        for _ in range(14):
            if attendance_service.is_school_day(self.school, day):
                break
            day += timedelta(days=1)
        with self.assertRaises(billing_services.UnfundedStudents) as raised:
            attendance_service.submit_register(
                user=self.admin, school=self.school, class_obj=self.jss1,
                day=day,
                records=[
                    {'studentId': str(s.public_id), 'status': 'present'} for s in students
                ],
            )
        message = raised.exception.detail['students']
        self.assertIn('no paid access', message)
        self.assertIn('Nothing was marked', message)
        self.assertIn('Fund', message)
        self.assertEqual(raised.exception.detail['reasonCode'], 'wallet_topup_required')
        self.assertEqual(int(raised.exception.detail['shortfallKobo']), 4500)
        # Nothing charged, nothing created.
        self.assertEqual(
            Wallet.objects.get(school=self.school).balance_kobo, 30000,
        )
        self.assertFalse(
            StudentEntitlement.objects.filter(school=self.school).exists(),
        )
        self.assertEqual(
            WalletTransaction.objects.filter(
                school=self.school,
                category=WalletTransaction.Category.STUDENT_ACTIVATION,
            ).count(),
            0,
        )

    def test_batch_activation_is_idempotent_on_retry(self):
        from records.models import Enrollment
        students = [self.make_student(admission_number=f'Q{i}') for i in range(3)]
        first = services.ensure_many_student_access(
            self.school, students, actor=self.admin,
        )
        second = services.ensure_many_student_access(
            self.school, students, actor=self.admin,
        )
        self.assertEqual(len(first['activated']), 3)
        self.assertEqual(len(second['activated']), 0)
        self.assertEqual(len(second['already']), 3)
        self.assertEqual(
            StudentEntitlement.objects.filter(school=self.school).count(), 3,
        )

    def test_create_student_blocked_until_wallet_funded(self):
        from billing.models import Wallet
        from records.models import Student
        Wallet.objects.filter(school=self.school).update(balance_kobo=0)
        payload = {
            'firstName': 'Ada', 'lastName': 'Nwosu', 'gender': 'female',
            'admissionNumber': 'SUA/JSS/2026/009001', 'className': 'JSS 1',
            'arm': 'A', 'guardianName': 'Mrs Nwosu',
            'guardianPhone': '+2348000001234', 'dateOfBirth': '2014-05-02',
        }
        blocked = self.client.post('/api/v1/students/', payload, format='json')
        self.assertEqual(blocked.status_code, 402, blocked.content)
        self.assertIn('wallet', blocked.data['detail'].lower())
        self.assertFalse(
            Student.objects.filter(
                school=self.school, admission_number='SUA/JSS/2026/009001',
            ).exists(),
        )
        services.credit_wallet(
            self.school, 50000, category=WalletTransaction.Category.DEPOSIT,
        )
        allowed = self.client.post('/api/v1/students/', payload, format='json')
        self.assertEqual(allowed.status_code, 201, allowed.content)
        # Atomic charge-at-creation: ₦115 debited once, entitlement created
        # with the record, access receipt returned.
        self.assertEqual(
            Wallet.objects.get(school=self.school).balance_kobo, 50000 - 11500,
        )
        student = Student.objects.get(
            school=self.school, admission_number='SUA/JSS/2026/009001',
        )
        entitlement = StudentEntitlement.objects.get(student=student)
        self.assertEqual(entitlement.amount_kobo, 11500)
        self.assertIsNotNone(entitlement.wallet_transaction)
        access = allowed.data['access']
        self.assertEqual(access['amountKobo'], 11500)
        self.assertEqual(access['walletBalanceKobo'], 50000 - 11500)
        self.assertTrue(access['periodEnd'])
        # Second create for another student keeps charging exactly once each.
        payload2 = dict(payload, admissionNumber='SUA/JSS/2026/009002')
        allowed2 = self.client.post('/api/v1/students/', payload2, format='json')
        self.assertEqual(allowed2.status_code, 201, allowed2.content)
        self.assertEqual(
            Wallet.objects.get(school=self.school).balance_kobo, 50000 - 23000,
        )

    def test_import_commit_blocked_until_wallet_funded(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        from billing.models import Wallet
        from records.models import Student
        Wallet.objects.filter(school=self.school).update(balance_kobo=0)
        content = (
            'first_name,last_name,admission_number,class,guardian_phone\n'
            'Nia,Okoro,ADM-003,JSS 1,08012345678\n'
        )

        def _file():
            return SimpleUploadedFile('s.csv', content.encode(), content_type='text/csv')

        blocked = self.client.post(
            '/api/v1/students/import/', {'file': _file()}, format='multipart',
        )
        self.assertEqual(blocked.status_code, 402, blocked.content)
        self.assertIn('wallet', blocked.data['detail'].lower())
        self.assertFalse(
            Student.objects.filter(school=self.school, admission_number='ADM-003').exists(),
        )
        # The analysis preview stays readable so staff can fix the file first.
        preview = self.client.post(
            '/api/v1/students/import/analyse/', {'file': _file()}, format='multipart',
        )
        self.assertEqual(preview.status_code, 200, preview.content)

    def test_record_fee_payment_blocked_until_wallet_funded(self):
        from billing.models import Wallet
        from records.models import Invoice, Payment
        Wallet.objects.filter(school=self.school).update(balance_kobo=0)
        student = self.make_student(admission_number='F1')
        invoice = self.make_invoice(student=student, total='50000')
        blocked = self.client.post(
            '/api/v1/payments/',
            {'invoiceId': str(invoice.id), 'amount': '10000', 'method': 'cash'},
            format='json',
        )
        self.assertEqual(blocked.status_code, 402, blocked.content)
        self.assertIn('wallet', blocked.data['detail'].lower())
        self.assertFalse(Payment.objects.filter(invoice=invoice).exists())
        services.credit_wallet(
            self.school, 20000, category=WalletTransaction.Category.DEPOSIT,
        )
        allowed = self.client.post(
            '/api/v1/payments/',
            {'invoiceId': str(invoice.id), 'amount': '10000', 'method': 'cash'},
            format='json',
        )
        self.assertEqual(allowed.status_code, 201, allowed.content)

    def test_verify_fee_payment_blocked_until_wallet_funded(self):
        from billing.models import Wallet
        from records.models import Payment
        Wallet.objects.filter(school=self.school).update(balance_kobo=0)
        student = self.make_student(admission_number='F2')
        invoice = self.make_invoice(student=student, total='50000')
        payment = Payment.objects.create(
            school=self.school, invoice=invoice, amount=10000,
            method=Payment.Method.BANK_TRANSFER, status=Payment.Status.PENDING,
            reference='FEE-001',
        )
        blocked = self.client.post(f'/api/v1/payments/{payment.id}/verify/')
        self.assertEqual(blocked.status_code, 402, blocked.content)
        payment.refresh_from_db()
        self.assertEqual(payment.status, Payment.Status.PENDING)

    def _import_csv(self, rows):
        from django.core.files.uploadedfile import SimpleUploadedFile
        content = (
            'first_name,last_name,admission_number,class,guardian_phone\n' + rows
        )
        return SimpleUploadedFile('s.csv', content.encode(), content_type='text/csv')

    def test_import_preview_shows_exact_cost(self):
        preview = self.client.post(
            '/api/v1/students/import/analyse/',
            {'file': self._import_csv(
                'Nia,Okoro,IMP-001,JSS 1,08012345678\n'
                'Mia,Okoro,IMP-002,JSS 1,08012345678\n'
            )},
            format='multipart',
        )
        self.assertEqual(preview.status_code, 200, preview.content)
        billing_quote = preview.data['billing']
        self.assertEqual(billing_quote['newCount'], 2)
        self.assertEqual(billing_quote['priceKobo'], 11500)
        self.assertEqual(billing_quote['totalCostKobo'], 23000)

    def test_import_commit_charges_once_each_atomically(self):
        from billing.models import Wallet
        from records.models import Student
        preview = self.client.post(
            '/api/v1/students/import/analyse/',
            {'file': self._import_csv(
                'Nia,Okoro,IMP-001,JSS 1,08012345678\n'
                'Mia,Okoro,IMP-002,JSS 1,08012345678\n'
            )},
            format='multipart',
        )
        committed = self.client.post(
            '/api/v1/students/import/',
            {'file': self._import_csv(
                'Nia,Okoro,IMP-001,JSS 1,08012345678\n'
                'Mia,Okoro,IMP-002,JSS 1,08012345678\n'
            )},
            format='multipart',
        )
        self.assertEqual(committed.status_code, 200, committed.content)
        self.assertEqual(committed.data['imported'], 2)
        self.assertEqual(committed.data['billing']['chargedKobo'], 23000)
        self.assertEqual(
            Wallet.objects.get(school=self.school).balance_kobo, 50000 - 23000,
        )
        for number in ('IMP-001', 'IMP-002'):
            student = Student.objects.get(
                school=self.school, admission_number=number,
            )
            entitlement = StudentEntitlement.objects.get(student=student)
            self.assertEqual(entitlement.amount_kobo, 11500)
            self.assertIsNotNone(entitlement.wallet_transaction)

    def test_import_commit_with_shortfall_imports_nothing(self):
        from billing.models import Wallet
        from records.models import Student
        Wallet.objects.filter(school=self.school).update(balance_kobo=10000)
        content = self._import_csv(
            'Nia,Okoro,IMP-001,JSS 1,08012345678\n'
            'Mia,Okoro,IMP-002,JSS 1,08012345678\n'
        )
        preview = self.client.post(
            '/api/v1/students/import/analyse/', {'file': content}, format='multipart',
        )
        self.assertEqual(preview.data['billing']['shortfallKobo'], 23000 - 10000)
        committed = self.client.post(
            '/api/v1/students/import/',
            {'file': self._import_csv(
                'Nia,Okoro,IMP-001,JSS 1,08012345678\n'
                'Mia,Okoro,IMP-002,JSS 1,08012345678\n'
            )},
            format='multipart',
        )
        self.assertEqual(committed.status_code, 402, committed.content)
        self.assertFalse(
            Student.objects.filter(school=self.school).exists(),
        )
        self.assertEqual(
            Wallet.objects.get(school=self.school).balance_kobo, 10000,
        )
        self.assertFalse(
            StudentEntitlement.objects.filter(school=self.school).exists(),
        )

    def test_complimentary_grant_gives_access_without_charging(self):
        from billing.models import Wallet
        platform = User.objects.create_user(
            email='platform@example.com', password='Strong-Pass-1!',
            first_name='Platform', last_name='Manager',
            role=User.Role.PLATFORM_MANAGER, school=None,
            is_active=True, is_verified=True,
        )
        self.client.force_authenticate(platform)
        student = self.make_student(admission_number='C1')
        granted = self.client.post(
            '/api/v1/billing/platform/complimentary/',
            {
                'schoolId': str(self.school.pk),
                'studentId': str(student.public_id),
                'reason': 'Flood relief, September intake',
            },
            format='json',
        )
        self.assertEqual(granted.status_code, 201, granted.content)
        entitlement = StudentEntitlement.objects.get(student=student)
        self.assertEqual(entitlement.amount_kobo, 0)
        self.assertTrue(entitlement.is_complimentary)
        self.assertEqual(entitlement.comp_reason, 'Flood relief, September intake')
        # Wallet untouched, no ledger row invented.
        self.assertEqual(
            Wallet.objects.get(school=self.school).balance_kobo, 50000,
        )
        self.assertFalse(
            WalletTransaction.objects.filter(student=student).exists(),
        )
        self.assertTrue(services.student_has_access(student))
        # Repeating is a no-op, and reason stays required.
        again = self.client.post(
            '/api/v1/billing/platform/complimentary/',
            {
                'schoolId': str(self.school.pk),
                'studentId': str(student.public_id),
                'reason': 'Flood relief, September intake',
            },
            format='json',
        )
        self.assertEqual(again.status_code, 200, again.content)
        self.assertFalse(again.data['created'])
        noreason = self.client.post(
            '/api/v1/billing/platform/complimentary/',
            {'schoolId': str(self.school.pk), 'studentId': str(student.public_id)},
            format='json',
        )
        self.assertEqual(noreason.status_code, 400, noreason.content)

    def test_school_admin_cannot_grant_complimentary(self):
        student = self.make_student(admission_number='C2')
        denied = self.client.post(
            '/api/v1/billing/platform/complimentary/',
            {
                'schoolId': str(self.school.pk),
                'studentId': str(student.public_id),
                'reason': 'Trying it on',
            },
            format='json',
        )
        self.assertEqual(denied.status_code, 403, denied.content)
        self.assertFalse(StudentEntitlement.objects.filter(student=student).exists())

    def test_grace_period_keeps_access(self):
        from records.services import results as results_service
        today = timezone.localdate()
        student = self.make_student(admission_number='B1')
        StudentEntitlement.objects.create(
            student=student, school=self.school,
            period_start=today - timedelta(days=32),
            period_end=today - timedelta(days=1),
            amount_kobo=11500,
        )
        response = self.client.get(f'/api/v1/students/{student.public_id}/')
        self.assertEqual(response.status_code, 200)


class EntitlementModelTests(TestCase):
    def test_school_admin_role_value_exists(self):
        self.assertTrue(User.Role.SCHOOL_ADMIN)
        self.assertTrue(hasattr(School, 'wallet'))


class ConcurrentActivationTests(TransactionTestCase):
    """Two simultaneous activations of one student charge exactly once.

    TransactionTestCase (no wrapping atomic) so both threads genuinely race
    on Postgres row locks; the loser reuses the winner's entitlement.
    """

    def setUp(self):
        from records.models import AcademicSession
        self.school = School.objects.create(
            name='Race Academy', slug='race-academy', address='1 Race Road',
            state='Lagos', lga='Ikeja', phone='+2348000000099',
            email='race@example.com', is_active=True,
        )
        self.admin = User.objects.create_user(
            email='race-admin@example.com', password='Strong-Pass-1!',
            first_name='Race', last_name='Admin',
            role=User.Role.SCHOOL_ADMIN, school=self.school, is_active=True,
        )
        self.session = AcademicSession.objects.create(
            school=self.school, name='2026/2027', start_year=2026, end_year=2027,
            is_current=True,
        )
        services.credit_wallet(
            self.school, 50000, category=WalletTransaction.Category.DEPOSIT,
        )
        self.student = Student.objects.create(
            school=self.school, admission_number='RACE-001',
            first_name='Race', last_name='Case', gender='male',
            class_name='JSS 1',
        )

    @skipUnlessDBFeature('has_select_for_update')
    def test_concurrent_activations_charge_once(self):
        import threading
        from billing import services as billing_services
        from billing.models import Wallet as WalletModel
        school_id = self.school.id
        student_id = self.student.id
        admin_id = self.admin.id
        barrier = threading.Barrier(2)
        outcomes = []

        def _activate():
            from accounts.models import User as UserModel
            from billing.models import Wallet as WalletModel
            from records.models import Student as StudentModel
            from schools.models import School as SchoolModel
            barrier.wait(timeout=30)
            school = SchoolModel.objects.get(pk=school_id)
            student = StudentModel.objects.get(pk=student_id)
            admin = UserModel.objects.get(pk=admin_id)
            entitlement, created = billing_services.activate_student(
                school, student, actor=admin,
            )
            outcomes.append(created)
            return created

        threads = [threading.Thread(target=_activate) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=60)
        self.assertEqual(sorted(outcomes), [False, True])
        self.assertEqual(
            StudentEntitlement.objects.filter(student_id=student_id).count(), 1,
        )
        self.assertEqual(
            WalletModel.objects.get(school_id=school_id).balance_kobo,
            50000 - 11500,
        )
        self.assertEqual(
            WalletTransaction.objects.filter(
                school_id=school_id,
                category=WalletTransaction.Category.STUDENT_ACTIVATION,
            ).count(),
            1,
        )
