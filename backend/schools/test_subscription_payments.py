import hashlib
import hmac
import json
from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from accounts.models import User
from schools.models import School, SchoolSubscription, SubscriptionPayment, SubscriptionPlan


class SubscriptionPaymentFlowTests(TestCase):
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
        self.client = APIClient()
        self.client.force_authenticate(self.admin)

    @override_settings(PAYSTACK_CALLBACK_URL='https://schools.example/subscription')
    @patch(
        'schools.subscription_views.paystack.initialize_transaction',
        return_value={
            'access_code': 'access-code',
            'authorization_url': 'https://checkout.paystack.com/access-code',
            'reference': 'gateway-reference',
        },
    )
    def test_checkout_uses_backend_plan_amount_and_callback_url(self, initialize):
        response = self.client.post(
            '/api/v1/schools/subscriptions/checkout/',
            {'planId': 't100'},
            format='json',
        )

        self.assertEqual(response.status_code, 200, response.content)
        initialize.assert_called_once()
        self.assertEqual(initialize.call_args.kwargs['amount_kobo'], 800000)
        self.assertEqual(
            initialize.call_args.kwargs['callback_url'],
            'https://schools.example/subscription',
        )
        self.assertEqual(response.data['authorizationUrl'], 'https://checkout.paystack.com/access-code')
        payment = SubscriptionPayment.objects.get(reference=response.data['reference'])
        self.assertEqual(payment.paystack_reference, 'gateway-reference')
        self.assertEqual(payment.amount_kobo, 800000)

    @patch(
        'schools.subscription_views.paystack.verify_transaction',
        side_effect=lambda reference: {
            'status': 'success',
            'reference': reference,
            'amount': 800000,
            'currency': 'NGN',
            'channel': 'card',
        },
    )
    def test_callback_verifies_payment_and_activates_subscription(self, verify):
        payment = self._pending_payment()

        response = self.client.get(
            f'/api/v1/schools/subscriptions/verify/{payment.reference}/',
        )

        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.data['status'], 'success')
        verify.assert_called_once_with(payment.reference)
        payment.refresh_from_db()
        self.assertEqual(payment.status, SubscriptionPayment.Status.SUCCESS)
        self.assertEqual(payment.channel, 'card')
        self.assertEqual(
            SchoolSubscription.objects.get(school=self.school).status,
            SchoolSubscription.Status.ACTIVE,
        )

    @override_settings(PAYSTACK_SECRET_KEY='test-secret')
    @patch(
        'schools.subscription_views.paystack.verify_transaction',
        side_effect=lambda reference: {
            'status': 'success',
            'reference': reference,
            'amount': 800000,
            'currency': 'NGN',
            'channel': 'card',
        },
    )
    def test_signed_webhook_reverifies_with_paystack_before_activation(self, verify):
        payment = self._pending_payment()
        body = json.dumps({
            'event': 'charge.success',
            'data': {
                'status': 'success',
                'reference': payment.reference,
                'amount': 800000,
                'currency': 'NGN',
            },
        })
        signature = hmac.new(
            b'test-secret', body.encode('utf-8'), hashlib.sha512,
        ).hexdigest()

        response = APIClient().post(
            '/api/v1/schools/subscriptions/webhook/',
            body,
            content_type='application/json',
            HTTP_X_PAYSTACK_SIGNATURE=signature,
        )

        self.assertEqual(response.status_code, 200, response.content)
        verify.assert_called_once_with(payment.reference)
        payment.refresh_from_db()
        self.assertEqual(payment.status, SubscriptionPayment.Status.SUCCESS)

    def test_repeated_payment_confirmation_does_not_extend_subscription_twice(self):
        payment = self._pending_payment()
        with patch(
            'schools.subscription_views.paystack.verify_transaction',
            side_effect=lambda reference: {
                'status': 'success',
                'reference': reference,
                'amount': 800000,
                'currency': 'NGN',
            },
        ):
            first = self.client.get(
                f'/api/v1/schools/subscriptions/verify/{payment.reference}/',
            )
            expiry = SchoolSubscription.objects.get(school=self.school).expires_at
            second = self.client.get(
                f'/api/v1/schools/subscriptions/verify/{payment.reference}/',
            )

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(
            SchoolSubscription.objects.get(school=self.school).expires_at,
            expiry,
        )

    def _pending_payment(self):
        return SubscriptionPayment.objects.create(
            school=self.school,
            plan=self.plan,
            reference='SUB-PAYMENT-FLOW-01',
            amount_kobo=800000,
        )
