"""Paid-service usage control: SMS, OTP, AI allowances and reminders.

Pins the spec's chain end to end: Event -> Business Rule -> Authorization ->
Usage Check -> Execute -> Record Usage. The interesting cases are the failure
modes: an exhausted allowance must not spend provider money, an SMS failure
must not roll back a verified payment, a reminder must never double-send, and
nothing may leak across school boundaries.
"""
from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from unittest import mock

from django.core.management import call_command
from django.test import override_settings
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from accounts.models import OTPCode, User
from records.models import (
    AcademicSession,
    Invoice,
    Payment,
    ReminderLog,
    Student,
    UsageRecord,
)
from records.services import events as event_service
from records.services.sms import SMSResult
from records.services.usage import AllowanceExhausted, usage_service
from schools.models import SubscriptionPlan

from .base import SchoolTestCase


class FakeSMSProvider:
    """Deterministic provider stand-in: records calls, obeys a flag."""

    def __init__(self, succeed: bool = True):
        self.succeed = succeed
        self.calls: list[dict] = []

    def send(self, to, message, sender_id=None):
        self.calls.append({'to': to, 'message': message})
        if self.succeed:
            return SMSResult(
                succeeded=True, provider_reference=f'msg-{len(self.calls)}',
                cost=200,
            )
        return SMSResult(succeeded=False, error='provider down')


def fake_provider(succeed: bool = True):
    return mock.patch(
        'records.services.sms.get_sms_provider',
        return_value=FakeSMSProvider(succeed),
    )


class PaymentTriggeredSMSTests(SchoolTestCase):
    """Event -> rule -> authorization -> usage check -> execute -> record."""

    def setUp(self):
        super().setUp()
        self.student = self.make_student(admission_number='SUA/T/SMS1')
        self.parent.linked_students.add(self.student)
        User.objects.filter(pk=self.parent.pk).update(phone='+2348000000022')
        self.invoice = self.make_invoice(student=self.student, total='50000')
        self.payment = Payment.objects.create(
            school=self.school, invoice=self.invoice, amount=20000,
            method=Payment.Method.CASH, status=Payment.Status.VERIFIED,
            reference='PAY-SMS-1',
        )

    def test_verified_payment_sends_sms_and_records_usage(self):
        provider = FakeSMSProvider()
        with mock.patch(
            'records.services.sms.get_sms_provider', return_value=provider,
        ):
            event_service.payment_verified(self.payment)

        self.assertEqual(len(provider.calls), 1)
        record = UsageRecord.objects.get(
            payment=self.payment,
            resource_type=UsageRecord.ResourceType.SMS,
            action_type=UsageRecord.ActionType.PAYMENT_NOTIFICATION,
        )
        self.assertEqual(record.status, UsageRecord.Status.SUCCEEDED)
        self.assertEqual(record.school, self.school)
        self.assertEqual(record.provider_reference, 'msg-1')
        self.assertEqual(record.actual_cost, 200)
        self.assertEqual(record.student, self.student)
        self.assertEqual(record.invoice, self.invoice)

    def test_sms_failure_never_fails_the_payment(self):
        with fake_provider(succeed=False):
            # Must not raise: the payment stays verified regardless.
            event_service.payment_verified(self.payment)

        self.payment.refresh_from_db()
        self.invoice.refresh_from_db()
        self.assertEqual(self.payment.status, Payment.Status.VERIFIED)
        self.assertEqual(self.invoice.paid, 0)  # untouched by the SMS attempt
        record = UsageRecord.objects.get(
            payment=self.payment,
            resource_type=UsageRecord.ResourceType.SMS,
        )
        self.assertEqual(record.status, UsageRecord.Status.FAILED)

    def test_re_running_the_event_does_not_double_send(self):
        with fake_provider() as provider_factory:
            event_service.payment_verified(self.payment)
            event_service.payment_verified(self.payment)

        provider = provider_factory.return_value
        self.assertEqual(len(provider.calls), 1)

    def test_exhausted_allowance_blocks_sms_but_not_the_event(self):
        plan = self.school.subscription.plan
        plan.monthly_sms_allowance = 0
        plan.save(update_fields=['monthly_sms_allowance'])

        provider = FakeSMSProvider()
        with mock.patch(
            'records.services.sms.get_sms_provider', return_value=provider,
        ):
            event_service.payment_verified(self.payment)  # must not raise

        self.assertEqual(provider.calls, [])
        record = UsageRecord.objects.get(
            payment=self.payment,
            resource_type=UsageRecord.ResourceType.SMS,
        )
        self.assertEqual(record.status, UsageRecord.Status.EXHAUSTED)

    def test_allowance_counts_only_this_school(self):
        # Exhaust this school's plan; the rival school sits on its own plan
        # and its allowance must be untouched.
        plan = self.school.subscription.plan
        plan.monthly_sms_allowance = 0
        plan.save(update_fields=['monthly_sms_allowance'])
        rival_plan = SubscriptionPlan.objects.create(
            name='rival', min_students=1, max_students=5000,
            monthly_price=100, monthly_sms_allowance=50,
        )
        self.other_school.subscription.plan = rival_plan
        self.other_school.subscription.save(update_fields=['plan'])

        with fake_provider():
            event_service.payment_verified(self.payment)

        self.assertFalse(
            UsageRecord.objects.filter(school=self.other_school).exists(),
        )
        self.assertTrue(
            usage_service.check_allowance(self.other_school, 'sms', 1),
        )

    def test_sms_failure_is_recorded_with_the_school(self):
        with fake_provider(succeed=False):
            event_service.payment_verified(self.payment)

        record = UsageRecord.objects.get(
            school=self.school, resource_type=UsageRecord.ResourceType.SMS,
        )
        self.assertEqual(record.status, UsageRecord.Status.FAILED)
        # The provider class is still named, so the ledger says who failed.
        self.assertEqual(record.provider, 'FakeSMSProvider')


class SMSAllowanceEnforcementTests(SchoolTestCase):
    def test_send_sms_raises_when_allowance_is_exhausted(self):
        plan = self.school.subscription.plan
        plan.monthly_sms_allowance = 0
        plan.save(update_fields=['monthly_sms_allowance'])

        with fake_provider() as provider_factory:
            with self.assertRaises(AllowanceExhausted):
                usage_service.send_sms(
                    school=self.school, to='+2348000000033',
                    message='hello', action_type='payment_notification',
                )
            self.assertEqual(provider_factory.return_value.calls, [])

        record = UsageRecord.objects.get(
            school=self.school, resource_type=UsageRecord.ResourceType.SMS,
        )
        self.assertEqual(record.status, UsageRecord.Status.EXHAUSTED)

    def test_send_sms_succeeds_within_allowance_and_is_ledgered(self):
        with fake_provider():
            usage_service.send_sms(
                school=self.school, to='+2348000000033',
                message='hello', action_type='payment_notification',
            )

        record = UsageRecord.objects.get(
            school=self.school, resource_type=UsageRecord.ResourceType.SMS,
        )
        self.assertEqual(record.status, UsageRecord.Status.SUCCEEDED)
        self.assertEqual(record.estimated_cost, 200)  # plan.sms_cost_per_unit

    def test_monthly_usage_aggregates_only_the_current_period(self):
        with fake_provider():
            usage_service.send_sms(
                school=self.school, to='+2341', message='a',
                action_type='payment_notification',
            )
            usage_service.send_sms(
                school=self.school, to='+2342', message='b',
                action_type='payment_notification',
            )
        self.assertEqual(
            usage_service._get_monthly_usage(self.school, 'sms'), 2,
        )


class BalanceReminderTests(SchoolTestCase):
    """Automatic reminders from the academic calendar."""

    def setUp(self):
        super().setUp()
        self.session.term_end_date = (
            timezone.localdate() + timedelta(days=7)
        )
        self.session.save(update_fields=['term_end_date'])
        self.student = self.make_student(admission_number='SUA/T/REM1')
        self.student.guardian_phone = '+2348000000044'
        self.student.save(update_fields=['guardian_phone'])
        self.invoice = self.make_invoice(
            student=self.student, total='50000', term='First Term',
        )
        self.invoice.paid = Decimal('20000')
        self.invoice.save(update_fields=['paid'])

    def run_sweep(self, **kwargs):
        with fake_provider() as provider_factory:
            call_command('sweep_balance_reminders', **kwargs)
            return provider_factory.return_value

    def test_outstanding_balance_triggers_a_reminder(self):
        provider = self.run_sweep()

        self.assertEqual(len(provider.calls), 1)
        # outstanding = total - verified payments; none are verified here,
        # so the full 50,000 is owed.
        self.assertIn('50,000.00', provider.calls[0]['message'])
        record = UsageRecord.objects.get(
            school=self.school,
            resource_type=UsageRecord.ResourceType.SMS,
            action_type=UsageRecord.ActionType.BALANCE_REMINDER,
        )
        self.assertEqual(record.status, UsageRecord.Status.SUCCEEDED)
        self.assertEqual(record.invoice, self.invoice)
        log = ReminderLog.objects.get(student=self.student)
        self.assertEqual(log.status, 'sent')

    def test_no_reminder_when_balance_is_zero(self):
        # `outstanding` counts verified payments only, so a fully verified
        # payment is what closes the balance.
        Payment.objects.create(
            school=self.school, invoice=self.invoice,
            amount=self.invoice.total, method=Payment.Method.CASH,
            status=Payment.Status.VERIFIED, reference='PAY-FULL',
        )

        provider = self.run_sweep()

        self.assertEqual(provider.calls, [])
        self.assertFalse(ReminderLog.objects.exists())
        self.assertFalse(
            UsageRecord.objects.filter(
                action_type=UsageRecord.ActionType.BALANCE_REMINDER,
            ).exists(),
        )

    def test_second_run_is_a_no_op(self):
        self.run_sweep()
        provider = self.run_sweep()

        self.assertEqual(provider.calls, [])
        self.assertEqual(
            ReminderLog.objects.filter(student=self.student).count(), 1,
        )

    def test_no_reminder_without_a_guardian_phone(self):
        self.student.guardian_phone = ''
        self.student.save(update_fields=['guardian_phone'])

        provider = self.run_sweep()

        self.assertEqual(provider.calls, [])

    def test_no_reminder_for_a_withdrawn_student(self):
        self.student.status = Student.Status.WITHDRAWN
        self.student.save(update_fields=['status'])

        provider = self.run_sweep()

        self.assertEqual(provider.calls, [])

    def test_no_reminder_when_the_term_does_not_end_today_plus_days(self):
        self.session.term_end_date = timezone.localdate() + timedelta(days=30)
        self.session.save(update_fields=['term_end_date'])

        provider = self.run_sweep()

        self.assertEqual(provider.calls, [])

    def test_exhausted_allowance_blocks_the_reminder_only(self):
        plan = self.school.subscription.plan
        plan.monthly_sms_allowance = 0
        plan.save(update_fields=['monthly_sms_allowance'])

        provider = self.run_sweep()

        self.assertEqual(provider.calls, [])
        # The sweep still claims the slot, so a top-up does not burst-send.
        log = ReminderLog.objects.get(student=self.student)
        self.assertEqual(log.status, 'blocked_exhausted')
        record = UsageRecord.objects.get(
            resource_type=UsageRecord.ResourceType.SMS,
            action_type=UsageRecord.ActionType.BALANCE_REMINDER,
        )
        self.assertEqual(record.status, UsageRecord.Status.EXHAUSTED)

    def test_reminders_do_not_cross_schools(self):
        rival_session = AcademicSession.objects.get(school=self.other_school)
        rival_session.term_end_date = (
            timezone.localdate() + timedelta(days=7)
        )
        rival_session.save(update_fields=['term_end_date'])
        rival_student = Student.objects.create(
            school=self.other_school, admission_number='RVC/T/REM1',
            first_name='Rival', last_name='Kid', gender='male',
            class_name='JSS 1', status=Student.Status.ACTIVE,
            guardian_phone='+2348000000055',
        )
        other_session = AcademicSession.objects.get(school=self.other_school)
        Invoice.objects.create(
            school=self.other_school, student=rival_student,
            academic_session=other_session, term='First Term',
            total=Decimal('50000'), paid=Decimal('0'),
            items=[{'label': 'Tuition', 'amount': '50000'}],
        )

        provider = self.run_sweep()

        # Both schools get their own reminder; no record crosses over.
        self.assertEqual(len(provider.calls), 2)
        self.assertEqual(
            UsageRecord.objects.filter(
                resource_type=UsageRecord.ResourceType.SMS,
                action_type=UsageRecord.ActionType.BALANCE_REMINDER,
            ).count(), 2,
        )
        self.assertFalse(
            UsageRecord.objects.filter(
                action_type=UsageRecord.ActionType.BALANCE_REMINDER,
                school=self.school, student=rival_student,
            ).exists(),
        )


class OTPControlTests(SchoolTestCase):
    def setUp(self):
        super().setUp()
        self.user = self.parent
        User.objects.filter(pk=self.user.pk).update(phone='+2348000000066')

    def test_otp_is_recorded_per_school(self):
        with fake_provider():
            usage_service.send_otp(
                self.user, self.school, purpose='phone_verification',
            )

        record = UsageRecord.objects.get(
            school=self.school, resource_type=UsageRecord.ResourceType.OTP,
        )
        self.assertEqual(record.status, UsageRecord.Status.SUCCEEDED)
        self.assertEqual(record.user, self.user)
        self.assertEqual(record.estimated_cost, 100)

    def test_resend_cooldown_is_enforced(self):
        with fake_provider():
            usage_service.send_otp(
                self.user, self.school, purpose='phone_verification',
            )
            with self.assertRaises(ValidationError):
                usage_service.send_otp(
                    self.user, self.school, purpose='phone_verification',
                )

    def test_otp_window_limit_is_enforced(self):
        with mock.patch.object(usage_service, 'OTP_RESEND_COOLDOWN_SECONDS', 0):
            with fake_provider():
                for _ in range(usage_service.OTP_MAX_PER_WINDOW):
                    usage_service.send_otp(
                        self.user, self.school, purpose='phone_verification',
                    )
                with self.assertRaises(ValidationError):
                    usage_service.send_otp(
                        self.user, self.school, purpose='phone_verification',
                    )

    def test_otp_allowance_exhaustion_is_enforced(self):
        plan = self.school.subscription.plan
        plan.monthly_otp_allowance = 0
        plan.save(update_fields=['monthly_otp_allowance'])

        with fake_provider() as provider_factory:
            with self.assertRaises(AllowanceExhausted):
                usage_service.send_otp(
                    self.user, self.school, purpose='phone_verification',
                )
            self.assertEqual(provider_factory.return_value.calls, [])
        self.assertFalse(
            UsageRecord.objects.filter(
                resource_type=UsageRecord.ResourceType.OTP,
            ).exists(),
        )

    def test_otp_codes_do_not_cross_users_or_schools(self):
        with fake_provider():
            otp = usage_service.send_otp(
                self.user, self.school, purpose='phone_verification',
            )
        self.assertEqual(OTPCode.objects.get(pk=otp.pk).school, self.school)
        # A different user in a different school cannot verify it.
        with self.assertRaises(ValidationError):
            usage_service.verify_otp(
                self.other_admin, self.other_school,
                code='000000', purpose='phone_verification',
            )


class AIAllowanceTests(SchoolTestCase):
    def ask(self, tool='noop', **arguments):
        return self.client.post(
            self.url('/assistant/query/'),
            {'tool': tool, 'arguments': arguments},
            format='json',
        )

    def test_ai_usage_is_ledgered_with_credits(self):
        self.auth(self.admin)
        with mock.patch(
            'records.services.ai_tools.call_tool',
            return_value={'ok': True},
        ):
            response = self.ask('students.list')

        self.assertEqual(response.status_code, 200)
        record = UsageRecord.objects.get(
            school=self.school, resource_type=UsageRecord.ResourceType.AI,
        )
        self.assertEqual(record.status, UsageRecord.Status.SUCCEEDED)
        self.assertEqual(record.credits_used, 1)
        self.assertEqual(record.user, self.admin)

    def test_exhausted_credits_reject_before_any_tool_runs(self):
        plan = self.school.subscription.plan
        plan.monthly_ai_allowance = 0
        plan.save(update_fields=['monthly_ai_allowance'])
        self.auth(self.admin)

        with mock.patch(
            'records.services.ai_tools.call_tool',
        ) as tool:
            response = self.ask('students.list')

        self.assertEqual(response.status_code, 400)
        tool.assert_not_called()
        self.assertFalse(
            UsageRecord.objects.filter(
                resource_type=UsageRecord.ResourceType.AI,
            ).exists(),
        )

    def test_check_ai_allowance_reports_the_cost_of_each_operation(self):
        self.assertEqual(
            usage_service.check_ai_allowance(self.school, 'simple_request'), 1,
        )
        self.assertEqual(
            usage_service.check_ai_allowance(self.school, 'normal_analysis'), 3,
        )
        self.assertEqual(
            usage_service.check_ai_allowance(self.school, 'report_analysis'), 5,
        )
        self.assertEqual(
            usage_service.check_ai_allowance(self.school, 'large_analysis'), 10,
        )

    def test_large_operation_is_rejected_when_only_small_credits_remain(self):
        plan = self.school.subscription.plan
        plan.monthly_ai_allowance = 4
        plan.save(update_fields=['monthly_ai_allowance'])

        usage_service.check_ai_allowance(self.school, 'normal_analysis')  # ok
        with self.assertRaises(ValidationError):
            usage_service.check_ai_allowance(self.school, 'large_analysis')

    def test_parent_cannot_reach_another_students_data(self):
        self.auth(self.parent)
        # A parent holds only ai.parent: a roster search is refused outright,
        # and the refusal happens before any credits are spent.
        response = self.ask('search_students', query='Amina')

        self.assertEqual(response.status_code, 403)
        self.assertFalse(
            UsageRecord.objects.filter(
                resource_type=UsageRecord.ResourceType.AI,
                status=UsageRecord.Status.SUCCEEDED,
            ).exists(),
        )

    def test_parent_cannot_read_another_familys_child(self):
        # A child the parent is not linked to.
        child = self.make_student(admission_number='SUA/T/CHILD1')
        other = Student.objects.create(
            school=self.school, admission_number='SUA/T/OTHER1',
            first_name='Other', last_name='Child', gender='female',
            class_name='JSS 1', status=Student.Status.ACTIVE,
        )
        self.parent.linked_students.add(child)
        self.auth(self.parent)
        response = self.ask(
            'get_my_child_attendance', student_id=str(other.id),
        )
        self.assertEqual(response.status_code, 403)

    def test_school_b_is_not_blocked_by_school_as_exhaustion(self):
        plan = self.school.subscription.plan
        plan.monthly_ai_allowance = 0
        plan.save(update_fields=['monthly_ai_allowance'])
        rival_plan = SubscriptionPlan.objects.create(
            name='rival-ai', min_students=1, max_students=5000,
            monthly_price=100, monthly_ai_allowance=100,
        )
        self.other_school.subscription.plan = rival_plan
        self.other_school.subscription.save(update_fields=['plan'])

        self.assertTrue(
            usage_service.check_allowance(self.other_school, 'ai', 1),
        )


class UsageLedgerAccuracyTests(SchoolTestCase):
    def test_costs_and_references_are_stored_not_dropped(self):
        usage_service.record_usage(
            school=self.school, resource_type='sms',
            action_type='payment_notification',
            provider='TermiiSMSProvider', provider_reference='abc-123',
            estimated_cost=200, actual_cost=180, status='succeeded',
        )
        record = UsageRecord.objects.get(school=self.school)
        self.assertEqual(record.provider, 'TermiiSMSProvider')
        self.assertEqual(record.provider_reference, 'abc-123')
        self.assertEqual(record.estimated_cost, 200)
        self.assertEqual(record.actual_cost, 180)

    def test_per_school_cost_isolates_the_two_ledgers(self):
        usage_service.record_usage(
            school=self.school, resource_type='sms',
            action_type='payment_notification', actual_cost=200,
        )
        usage_service.record_usage(
            school=self.other_school, resource_type='sms',
            action_type='payment_notification', actual_cost=50,
        )
        mine = UsageRecord.objects.filter(school=self.school)
        theirs = UsageRecord.objects.filter(school=self.other_school)
        self.assertEqual(
            sum(r.actual_cost for r in mine), 200,
        )
        self.assertEqual(
            sum(r.actual_cost for r in theirs), 50,
        )
