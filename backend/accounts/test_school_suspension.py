"""Suspension belongs to a school, so it must close the door on every account in it.

The suspended state is produced through the platform manager's real endpoint
(`PATCH /platform/schools/<id>/status/`) rather than by flipping model flags by
hand, so a change to how that endpoint stores a suspension fails these tests
instead of quietly reopening a hole.
"""
from django.test import TestCase
from rest_framework.test import APIClient

from accounts.models import User
from schools.models import School, SchoolSubscription, SubscriptionPlan
from schools.status import (
    SUSPENDED_CODE,
    SUSPENDED_DETAIL,
    is_suspended_school,
    school_status,
)


class SuspendedSchoolAuthTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name='Sunrise Academy', slug='sunrise-academy', address='1 Sunrise Way',
            state='Kano', lga='Kano Municipal', phone='+2348000000011',
            email='sunrise@example.com', is_active=True,
        )
        self.plan = SubscriptionPlan.objects.create(
            name='t100', min_students=1, max_students=100, monthly_price=100.00,
        )
        self.subscription = SchoolSubscription.objects.create(
            school=self.school, plan=self.plan, status=SchoolSubscription.Status.ACTIVE,
        )
        self.admin = User.objects.create_user(
            email='admin@sunrise.example', password='Strong-Pass-1!',
            first_name='Sunrise', last_name='Admin',
            role=User.Role.SCHOOL_ADMIN, school=self.school, is_active=True,
        )
        self.teacher = User.objects.create_user(
            email='teacher@sunrise.example', password='Strong-Pass-1!',
            first_name='Ada', last_name='Bello',
            role=User.Role.TEACHER, school=self.school, is_active=True,
        )
        self.platform = User.objects.create_user(
            email='platform@example.com', password='Strong-Pass-1!',
            first_name='Platform', last_name='Manager',
            role=User.Role.PLATFORM_MANAGER, is_active=True,
        )

    # ── helpers ─────────────────────────────────────────────────────────────

    def _login(self, identifier='admin@sunrise.example'):
        return APIClient().post(
            '/api/v1/auth/login/',
            {'identifier': identifier, 'password': 'Strong-Pass-1!'},
            format='json',
        )

    def _set_school_status(self, value):
        """Drive the platform endpoint exactly as the platform manager does."""
        platform = APIClient()
        platform.force_authenticate(self.platform)
        response = platform.patch(
            f'/api/v1/platform/schools/{self.school.id}/status/',
            {'status': value}, format='json',
        )
        self.assertEqual(response.status_code, 200, response.content)

    def _bearer_client(self):
        from rest_framework_simplejwt.tokens import RefreshToken

        client = APIClient()
        token = str(RefreshToken.for_user(self.admin).access_token)
        client.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')
        return client

    # ── sign in ─────────────────────────────────────────────────────────────

    def test_a_suspended_school_cannot_sign_in(self):
        self._set_school_status('suspended')
        self.assertTrue(is_suspended_school(self.school.id))

        for identifier in ('admin@sunrise.example', 'teacher@sunrise.example'):
            with self.subTest(identifier=identifier):
                response = self._login(identifier)
                self.assertEqual(response.status_code, 403, response.content)
                self.assertEqual(response.json()['detail'], SUSPENDED_DETAIL)
                self.assertNotIn('token', response.json())

    def test_sign_in_works_again_once_the_school_is_reinstated(self):
        self._set_school_status('suspended')
        self.assertEqual(self._login().status_code, 403)

        self._set_school_status('active')
        self.assertFalse(is_suspended_school(self.school.id))
        self.assertEqual(self._login().status_code, 200)

    def test_a_school_that_has_not_been_activated_yet_can_still_sign_in(self):
        # `is_active=False` with a pending subscription is ordinary onboarding,
        # not a suspension: a newly registered school's staff must be able to
        # get in to set it up.
        self.school.is_active = False
        self.school.save(update_fields=['is_active'])
        self.subscription.status = SchoolSubscription.Status.PENDING
        self.subscription.save(update_fields=['status'])

        self.assertEqual(school_status(self.school, self.subscription), 'pending_payment')
        self.assertFalse(is_suspended_school(self.school.id))
        self.assertEqual(self._login().status_code, 200)

    def test_platform_staff_sign_in_while_a_school_is_suspended(self):
        # Platform managers hold no school, so they are never caught by a
        # suspension — otherwise nobody could lift it.
        self._set_school_status('suspended')
        self.assertEqual(self._login('platform@example.com').status_code, 200)

    # ── already-issued credentials ──────────────────────────────────────────

    def test_a_token_issued_before_the_suspension_stops_working(self):
        client = self._bearer_client()
        self.assertEqual(client.get('/api/v1/auth/me/').status_code, 200)

        self._set_school_status('suspended')

        response = client.get('/api/v1/auth/me/')
        self.assertEqual(response.status_code, 401, response.content)
        self.assertEqual(response.json()['detail'], SUSPENDED_DETAIL)
        # The client needs to tell this apart from an expired token, or an
        # ordinary session expiry starts reading as "your school is suspended".
        self.assertEqual(response.json()['code'], SUSPENDED_CODE)

    def test_a_live_session_can_refresh_only_until_the_school_is_suspended(self):
        client = APIClient()
        login = client.post(
            '/api/v1/auth/login/',
            {'identifier': 'admin@sunrise.example', 'password': 'Strong-Pass-1!'},
            format='json',
        )
        self.assertEqual(login.status_code, 200, login.content)
        self.assertTrue(client.cookies.get('refresh_token'), 'login did not set the cookie')

        self.assertEqual(client.post('/api/v1/auth/token/refresh/').status_code, 200)

        self._set_school_status('suspended')

        response = client.post('/api/v1/auth/token/refresh/')
        self.assertEqual(response.status_code, 401, response.content)
        self.assertEqual(response.json()['detail'], SUSPENDED_DETAIL)
