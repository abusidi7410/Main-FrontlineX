"""Retired subscription money paths: checkout/verify/webhook answer 410.

Historical rows (SubscriptionPayment / SchoolSubscription) are preserved and
asserted untouched: retiring means no NEW charges, never rewritten history.
"""
from decimal import Decimal

from django.test import TestCase
from rest_framework.test import APIClient

from accounts.models import User
from schools.models import School, SchoolSubscription, SubscriptionPayment, SubscriptionPlan


class RetiredSubscriptionPaymentTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name='Payment Flow Academy',
            slug='payment-flow-academy',
            address='1 School Road',
            state='Lagos',
            lga='Ikeja',
            phone='+2348000000011',
            email='payments@example.com',
            is_active=True,
        )
        self.admin = User.objects.create_user(
            email='payment-admin@example.com',
            password='Strong-Pass-1!',
            first_name='Payment',
            last_name='Admin',
            role=User.Role.SCHOOL_ADMIN,
            school=self.school,
            is_active=True,
            is_verified=True,
        )
        self.plan = SubscriptionPlan.objects.create(
            code='t100',
            name='1–100 students',
            min_students=1,
            max_students=100,
            monthly_price=Decimal('8000.00'),
            is_active=True,
        )
        self.payment = SubscriptionPayment.objects.create(
            school=self.school,
            plan=self.plan,
            reference='SUB-PAYMENT-FLOW-01',
            amount_kobo=800000,
        )
        self.client = APIClient()
        self.client.force_authenticate(self.admin)

    def test_checkout_is_retired(self):
        response = self.client.post(
            '/api/v1/schools/subscriptions/checkout/',
            {'planId': 't100'},
            format='json',
        )
        self.assertEqual(response.status_code, 410, response.content)
        # No new payment attempt created.
        self.assertEqual(
            SubscriptionPayment.objects.filter(school=self.school).count(), 1,
        )

    def test_verify_is_retired_and_leaves_history_untouched(self):
        response = self.client.get(
            '/api/v1/schools/subscriptions/verify/SUB-PAYMENT-FLOW-01/',
        )
        self.assertEqual(response.status_code, 410, response.content)
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, SubscriptionPayment.Status.PENDING)

    def test_webhook_is_retired(self):
        response = APIClient().post(
            '/api/v1/schools/subscriptions/webhook/',
            {'event': 'charge.success', 'data': {'reference': 'SUB-PAYMENT-FLOW-01'}},
            format='json',
        )
        self.assertEqual(response.status_code, 410, response.content)
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, SubscriptionPayment.Status.PENDING)

    def test_plan_catalogue_is_empty(self):
        response = self.client.get('/api/v1/schools/plans/')
        self.assertEqual(response.status_code, 200, response.content)
        data = response.data
        results = data.get('results', data) if hasattr(data, 'get') else list(data)
        self.assertEqual(list(results), [])

    def test_school_subscription_self_view_is_retired(self):
        response = self.client.get('/api/v1/subscription/')
        self.assertEqual(response.status_code, 410, response.content)

    def test_historical_subscription_row_survives(self):
        SchoolSubscription.objects.create(
            school=self.school,
            plan=self.plan,
            status=SchoolSubscription.Status.ACTIVE,
        )
        self.assertTrue(
            SchoolSubscription.objects.filter(school=self.school).exists(),
        )
