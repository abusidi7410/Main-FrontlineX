"""Profit/cost reporting: subscription revenue vs SMS/OTP/AI variable cost.

The report is the platform's answer to "what did this school actually cost
us, and what did it pay?". Costs come from the usage ledger (never estimated
in the view), revenue from the plan, and the two endpoints must never leak
across school or role boundaries.
"""
from __future__ import annotations

from decimal import Decimal

from rest_framework.test import APIClient

from records.models import UsageRecord
from records.services import reporting as reporting_service
from schools.models import School, SchoolSubscription, SubscriptionPlan

from .base import SchoolTestCase


def _record(school, *, resource='sms', status='succeeded', quantity=1,
            actual=0, estimated=0, credits=0, **when):
    return UsageRecord.objects.create(
        school=school,
        resource_type=resource,
        action_type='payment_notification',
        quantity=quantity,
        credits_used=credits,
        actual_cost=actual,
        estimated_cost=estimated,
        status=status,
    )


class ReportingServiceTests(SchoolTestCase):
    """Pure aggregation logic, no HTTP."""

    def test_month_window_is_half_open(self):
        start, end = reporting_service.month_window(2026, 10)
        self.assertEqual(start.day, 1)
        self.assertEqual(end.month, 11)
        self.assertEqual(end.day, 1)

    def test_month_window_december_rolls_to_next_year(self):
        start, end = reporting_service.month_window(2026, 12)
        self.assertEqual(start.month, 12)
        self.assertEqual(end.year, 2027)
        self.assertEqual(end.month, 1)

    def test_parse_month_param_defaults_to_current(self):
        year, month = reporting_service.parse_month_param('')
        self.assertEqual((year, month), reporting_service.current_month_key())

    def test_parse_month_param_rejects_garbage(self):
        for bad in ('junk', '2026-13', '2026-00', '13-2026', '2026'):
            with self.assertRaises(ValueError, msg=bad):
                reporting_service.parse_month_param(bad)

    def test_usage_costs_aggregates_per_resource_and_status(self):
        _record(self.school, resource='sms', status='succeeded',
                actual=200, quantity=2)
        _record(self.school, resource='sms', status='failed',
                estimated=200)
        _record(self.school, resource='ai', status='succeeded',
                credits=3, actual=150)

        start, end = reporting_service.month_window(2026, 10)
        costs = reporting_service.usage_costs_for([self.school.id], start, end)
        sms = costs[self.school.id]['sms']
        ai = costs[self.school.id]['ai']

        self.assertEqual(sms['attempted'], 3)
        self.assertEqual(sms['succeeded'], 2)
        self.assertEqual(sms['failed'], 1)
        self.assertEqual(sms['costKobo'], 400)
        self.assertEqual(ai['credits'], 3)
        self.assertEqual(ai['costKobo'], 150)

    def test_cost_falls_back_to_estimate_when_provider_reported_nothing(self):
        # Console provider writes actual=0; the plan's estimate is the cost.
        _record(self.school, resource='sms', status='succeeded',
                estimated=200, actual=0)
        start, end = reporting_service.month_window(2026, 10)
        costs = reporting_service.usage_costs_for([self.school.id], start, end)
        self.assertEqual(costs[self.school.id]['sms']['costKobo'], 200)

    def test_school_report_computes_margin_from_ledger_and_plan(self):
        # Plan costs: sms=200 kobo, otp=100, ai=50 (from base fixture).
        # actual_cost is the record's total cost, not per-unit.
        _record(self.school, resource='sms', status='succeeded', actual=600,
                quantity=3)          # 3 SMS at 200 kobo = 600 kobo
        _record(self.school, resource='ai', status='succeeded', actual=250,
                credits=5)           # 5 credits at 50 kobo = 250 kobo

        start, end = reporting_service.month_window(2026, 10)
        report = reporting_service.school_report(self.school, start, end)

        self.assertEqual(report['revenueNaira'], Decimal('100'))
        self.assertEqual(report['costNaira'], Decimal('8.50'))  # 850 kobo
        self.assertEqual(report['grossMarginNaira'], Decimal('91.50'))
        # 91.50/100 = 91.5%
        self.assertAlmostEqual(report['grossMarginPercent'], 91.5, places=1)

    def test_school_report_zero_usage_has_full_margin(self):
        start, end = reporting_service.month_window(2026, 10)
        report = reporting_service.school_report(self.school, start, end)
        self.assertEqual(report['costNaira'], Decimal('0.00'))
        self.assertEqual(report['grossMarginNaira'], Decimal('100'))
        self.assertAlmostEqual(report['grossMarginPercent'], 100.0, places=1)

    def test_school_report_remaining_allowance_counts_all_attempts(self):
        # A blocked (exhausted) send must still consume budget.
        _record(self.school, resource='sms', status='exhausted', quantity=1)
        start, end = reporting_service.month_window(2026, 10)
        report = reporting_service.school_report(self.school, start, end)
        sms = report['usage']['sms']
        self.assertEqual(sms['allowance'], 1000)
        self.assertEqual(sms['blocked'], 1)
        self.assertEqual(sms['remaining'], 999)

    def test_platform_report_totals_every_school(self):
        _record(self.school, resource='sms', status='succeeded', actual=200)
        _record(self.other_school, resource='ai', status='succeeded',
                actual=50, credits=1)

        start, end = reporting_service.month_window(2026, 10)
        report = reporting_service.platform_profit_report(start, end)

        names = {row['schoolName'] for row in report['schools']}
        self.assertIn('Success Academy', names)
        self.assertIn('Rival College', names)
        # Both schools share the same 100-naira plan; cost 250 kobo total.
        self.assertEqual(report['totals']['schools'], 2)
        self.assertEqual(report['totals']['activeSubscriptions'], 2)
        self.assertEqual(report['totals']['revenueNaira'], Decimal('200'))
        self.assertEqual(report['totals']['costNaira'], Decimal('2.50'))

    def test_platform_report_includes_schools_with_cost_but_no_subscription(self):
        orphan = School.objects.create(
            name='Orphan Academy', slug='orphan-academy', code='ORP',
            address='Nowhere', state='Kano', lga='Kano',
            phone='', email='orphan@example.com', is_active=True,
            current_session='2026/2027',
        )
        _record(orphan, resource='sms', status='succeeded', actual=200)

        start, end = reporting_service.month_window(2026, 10)
        report = reporting_service.platform_profit_report(start, end)
        row = next(
            r for r in report['schools'] if r['schoolName'] == 'Orphan Academy'
        )
        self.assertIsNone(row['subscriptionStatus'])
        self.assertEqual(row['revenueNaira'], Decimal('0'))
        self.assertEqual(row['costNaira'], Decimal('2.00'))
        self.assertLess(row['grossMarginNaira'], 0)


class UsageReportEndpointTests(SchoolTestCase):
    """GET /api/v1/usage/report/ — the school's own P&L."""

    def test_admin_can_read_the_report(self):
        self.auth(self.admin)
        response = self.client.get(self.url('/usage/report/'))
        self.assertEqual(response.status_code, 200)
        self.assertIn('usage', response.data)
        self.assertIn('grossMarginNaira', response.data)
        self.assertIn('plan', response.data)

    def test_accountant_and_principal_can_read(self):
        for user in (self.accountant, self.principal):
            self.auth(user)
            response = self.client.get(self.url('/usage/report/'))
            self.assertEqual(response.status_code, 200, user.role)

    def test_teacher_and_parent_are_denied(self):
        for user in (self.teacher, self.parent, self.student_user):
            self.auth(user)
            response = self.client.get(self.url('/usage/report/'))
            self.assertEqual(response.status_code, 403, user.role)

    def test_report_is_scoped_to_the_callers_school(self):
        _record(self.other_school, resource='sms', status='succeeded',
                actual=200, quantity=50)

        self.auth(self.admin)
        response = self.client.get(self.url('/usage/report/'))
        self.assertEqual(response.data['usage']['sms']['succeeded'], 0)

        self.auth(self.other_admin)
        response = self.client.get(self.url('/usage/report/'))
        self.assertEqual(response.data['usage']['sms']['succeeded'], 50)

    def test_invalid_month_is_rejected(self):
        self.auth(self.admin)
        response = self.client.get(self.url('/usage/report/?month=junk'))
        self.assertEqual(response.status_code, 400)
        # The project's exception handler wraps field errors.
        self.assertIn('month', str(response.data))

    def test_month_param_filters_to_that_month(self):
        # Last month: one succeeded SMS at 200 kobo.
        last_month = reporting_service.current_month_key()
        if last_month[1] == 1:
            year, month = last_month[0] - 1, 12
        else:
            year, month = last_month[0], last_month[1] - 1
        record = _record(self.school, resource='sms', status='succeeded',
                         actual=200)
        UsageRecord.objects.filter(pk=record.pk).update(
            created_at=reporting_service.month_window(year, month)[0]
        )

        self.auth(self.admin)
        response = self.client.get(
            self.url(f'/usage/report/?month={year:04d}-{month:02d}'),
        )
        self.assertEqual(response.data['usage']['sms']['succeeded'], 1)


class PlatformProfitEndpointTests(SchoolTestCase):
    """GET /api/v1/platform/profit/ — every school as a P&L row."""

    def _platform_client(self):
        from accounts.models import User
        manager = User.objects.create_user(
            email='manager@platform.example', password='Strong-Pass-1!',
            first_name='Platform', last_name='Manager',
            role=User.Role.PLATFORM_MANAGER, school=None, is_active=True,
        )
        client = APIClient()
        client.force_authenticate(manager)
        return client

    def test_platform_manager_sees_all_schools(self):
        _record(self.school, resource='sms', status='succeeded', actual=200)

        client = self._platform_client()
        response = client.get('/api/v1/platform/profit/')
        self.assertEqual(response.status_code, 200)
        names = {row['schoolName'] for row in response.data['schools']}
        self.assertIn('Success Academy', names)
        self.assertIn('Rival College', names)
        self.assertGreaterEqual(response.data['totals']['schools'], 2)

    def test_school_admin_cannot_read_platform_profit(self):
        self.auth(self.admin)
        response = self.client.get('/api/v1/platform/profit/')
        self.assertEqual(response.status_code, 403)

    def test_revenue_and_cost_totals_are_consistent(self):
        _record(self.school, resource='sms', status='succeeded', actual=200)
        _record(self.school, resource='otp', status='succeeded', actual=100)

        client = self._platform_client()
        response = client.get('/api/v1/platform/profit/')
        totals = response.data['totals']

        self.assertEqual(totals['revenueNaira'], 200)   # two 100-naira plans
        self.assertEqual(totals['costNaira'], 3.0)
        self.assertEqual(totals['grossMarginNaira'], 197.0)
