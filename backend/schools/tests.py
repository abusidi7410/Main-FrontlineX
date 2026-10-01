from datetime import timedelta
from decimal import Decimal

from django.core.cache import cache
from django.db import connection
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from rest_framework.test import APIClient

from accounts.models import User
from records.models import Invoice, Payment, Student
from schools.models import AuditLog, School, SchoolSubscription

from .models import SubscriptionPlan


class PlatformSchoolDeleteTests(TestCase):
    def setUp(self):
        self.platform = User.objects.create_user(
            email='platform@example.com',
            password='Strong-Pass-1!',
            first_name='Platform',
            last_name='Manager',
            role=User.Role.PLATFORM_MANAGER,
            is_active=True,
        )
        self.school = School.objects.create(
            name='Sunrise Academy', slug='sunrise-academy', address='1 Sunrise Way',
            state='Kano', lga='Kano Municipal', phone='+2348000000011',
            email='sunrise@example.com', is_active=True,
        )
        self.plan = SubscriptionPlan.objects.create(
            name='t100', min_students=1, max_students=100, monthly_price=100.00,
        )
        SchoolSubscription.objects.create(
            school=self.school, plan=self.plan, status=SchoolSubscription.Status.ACTIVE,
        )
        self.admin = User.objects.create_user(
            email='admin@sunrise.example', password='Strong-Pass-1!',
            first_name='Sunrise', last_name='Admin',
            role=User.Role.SCHOOL_ADMIN, school=self.school, is_active=True,
        )
        Student.objects.create(
            school=self.school, admission_number='SRN-001',
            first_name='Amina', last_name='Bello', gender='female',
            class_name='SS1', status=Student.Status.ACTIVE,
        )
        self.client = APIClient()

    def _auth_as_platform(self):
        self.client.force_authenticate(self.platform)

    def _delete_url(self, school_id):
        return f'/api/v1/platform/schools/{school_id}/'

    def test_platform_manager_can_delete_school_with_confirmation(self):
        self._auth_as_platform()
        resp = self.client.delete(
            self._delete_url(self.school.id), {'confirm': 'Sunrise Academy'}, format='json',
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertFalse(School.objects.filter(id=self.school.id).exists())
        self.assertFalse(
            User.objects.filter(school_id=self.school.id).exists(),
            'School users must be cascade-deleted.',
        )
        self.assertFalse(
            Student.objects.filter(school_id=self.school.id).exists(),
            'School records must be cascade-deleted.',
        )
        self.assertTrue(
            AuditLog.objects.filter(action='school.deleted', target='Sunrise Academy').exists(),
            'Deletion must be left in the global audit trail.',
        )

    def test_wrong_confirmation_is_rejected(self):
        self._auth_as_platform()
        resp = self.client.delete(
            self._delete_url(self.school.id), {'confirm': 'Wrong Name'}, format='json',
        )
        self.assertEqual(resp.status_code, 400)
        self.assertTrue(School.objects.filter(id=self.school.id).exists())

    def test_missing_confirmation_is_rejected(self):
        self._auth_as_platform()
        resp = self.client.delete(self._delete_url(self.school.id))
        self.assertEqual(resp.status_code, 400)
        self.assertTrue(School.objects.filter(id=self.school.id).exists())

    def test_unknown_school_returns_404(self):
        self._auth_as_platform()
        resp = self.client.delete(
            self._delete_url('999999999'), {'confirm': 'Anything'}, format='json',
        )
        self.assertEqual(resp.status_code, 404)

    def test_non_platform_roles_are_forbidden(self):
        admin_client = APIClient()
        admin_client.force_authenticate(self.admin)
        resp = admin_client.delete(
            self._delete_url(self.school.id), {'confirm': 'Sunrise Academy'}, format='json',
        )
        self.assertEqual(resp.status_code, 403)
        self.assertTrue(School.objects.filter(id=self.school.id).exists())

    def test_unauthenticated_request_is_rejected(self):
        resp = self.client.delete(
            self._delete_url(self.school.id), {'confirm': 'Sunrise Academy'}, format='json',
        )
        self.assertEqual(resp.status_code, 401)
        self.assertTrue(School.objects.filter(id=self.school.id).exists())

    def test_deletion_is_permanent_and_counts_all_schools(self):
        School.objects.create(
            name='Other School', slug='other-school', address='9 Other Road',
            state='Lagos', lga='Ikeja', phone='+2348000000012',
            email='other@example.com', is_active=True,
        )
        self._auth_as_platform()
        resp = self.client.delete(
            self._delete_url(self.school.id), {'confirm': 'Sunrise Academy'}, format='json',
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()['remaining'], 1)


@override_settings(
    CACHES={
        'default': {
            'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
            'LOCATION': 'platform-overview-tests',
        },
    },
)
class PlatformOverviewTests(TestCase):
    def setUp(self):
        cache.clear()
        self.now = timezone.now()
        self.platform = User.objects.create_user(
            email='overview-platform@example.com',
            password='Strong-Pass-1!',
            first_name='Overview',
            last_name='Manager',
            role=User.Role.PLATFORM_MANAGER,
            is_active=True,
        )
        self.plan = SubscriptionPlan.objects.create(
            name='growth', min_students=1, max_students=500, monthly_price=Decimal('2500.00'),
        )
        self.active_school = self._school('Overview Active', 'active', 'active')
        self.trial_school = self._school('Overview Trial', 'trial', None)
        self.suspended_school = self._school('Overview Suspended', 'suspended', 'suspended')
        self.pending_school = self._school('Overview Pending', 'pending', 'expired')
        self.active_student = Student.objects.create(
            school=self.active_school,
            admission_number='OV-001',
            first_name='Amina',
            last_name='Bello',
            gender=Student.Gender.FEMALE,
            class_name='SS1',
            status=Student.Status.ACTIVE,
        )
        self.pending_student = Student.objects.create(
            school=self.pending_school,
            admission_number='OV-002',
            first_name='Chinedu',
            last_name='Okafor',
            gender=Student.Gender.MALE,
            class_name='SS1',
            status=Student.Status.ACTIVE,
        )
        self.active_admin = User.objects.create_user(
            email='overview-admin@example.com',
            password='Strong-Pass-1!',
            first_name='Active',
            last_name='Admin',
            role=User.Role.SCHOOL_ADMIN,
            school=self.active_school,
            is_active=True,
        )
        User.objects.filter(id=self.active_admin.id).update(last_login=self.now - timedelta(hours=2))
        invoice = Invoice.objects.create(
            school=self.active_school,
            student=self.active_student,
            term='First Term',
            total=Decimal('5000.00'),
        )
        payment = Payment.objects.create(
            school=self.active_school,
            invoice=invoice,
            amount=Decimal('5000.00'),
            method=Payment.Method.ONLINE,
            status=Payment.Status.VERIFIED,
            reference='OV-PAY-001',
        )
        Payment.objects.filter(id=payment.id).update(created_at=self.now - timedelta(days=2))
        failed_invoice = Invoice.objects.create(
            school=self.pending_school,
            student=self.pending_student,
            term='First Term',
            total=Decimal('1000.00'),
        )
        failed_payment = Payment.objects.create(
            school=self.pending_school,
            invoice=failed_invoice,
            amount=Decimal('1000.00'),
            method=Payment.Method.CARD,
            status=Payment.Status.FAILED,
            reference='OV-PAY-002',
        )
        Payment.objects.filter(id=failed_payment.id).update(created_at=self.now - timedelta(days=3))
        self.client = APIClient()
        self.client.force_authenticate(self.platform)

    def tearDown(self):
        cache.clear()

    def _school(self, name, slug, subscription_status):
        school = School.objects.create(
            name=name,
            slug=slug,
            address=f'{slug} road',
            state='Lagos',
            lga='Ikeja',
            phone=f'+234800000{len(slug):04d}',
            email=f'{slug}@example.com',
            is_active=slug == 'active',
        )
        if subscription_status is not None:
            SchoolSubscription.objects.create(
                school=school,
                plan=self.plan,
                status=subscription_status,
                expires_at=(
                    self.now - timedelta(days=1)
                    if subscription_status == SchoolSubscription.Status.EXPIRED
                    else self.now + timedelta(days=10)
                ),
            )
        return school

    def test_overview_uses_one_query_and_returns_operational_metrics(self):
        with CaptureQueriesContext(connection) as queries:
            response = self.client.get('/api/v1/platform/overview/?range=30d')

        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(len(queries), 1, [query['sql'] for query in queries])
        payload = response.json()
        self.assertEqual(payload['mrr'], 2500.0)
        self.assertEqual(payload['activeLogins24h'], 1)
        self.assertEqual(payload['failedPayments'], 1)
        self.assertEqual(payload['upcomingRenewals'], 2)
        self.assertEqual(payload['schoolsByStatus']['active'], 1)
        self.assertEqual(payload['schoolsByStatus']['trial'], 1)
        self.assertEqual(payload['schoolsByStatus']['suspended'], 1)
        self.assertEqual(payload['schoolsByStatus']['pending_payment'], 1)
        self.assertEqual(len(payload['mrrTrend']), 6)
        self.assertEqual(len(payload['atRiskSchools']), 2)
        at_risk_by_name = {row['name']: row for row in payload['atRiskSchools']}
        self.assertEqual(at_risk_by_name['Overview Pending']['failedPayments'], 1)

    def test_overview_is_cached_for_the_requested_range(self):
        first = self.client.get('/api/v1/platform/overview/?range=7d')
        second = self.client.get('/api/v1/platform/overview/?range=7d')
        self.assertEqual(first.status_code, 200)
        self.assertEqual(first.json(), second.json())
        self.assertEqual(cache.get('platform:overview:7:all'), second.json())


class PublicSchoolRegistrationPaymentTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.plan = SubscriptionPlan.objects.create(
            name='t100', min_students=1, max_students=100, monthly_price=100.00,
        )

    def _payload(self):
        return {
            'school': {
                'name': 'New Academy',
                'type': 'primary',
                'address': '1 New Road',
                'state': 'Lagos',
                'lga': 'Ikeja',
                'phone': '+2348000000100',
                'email': 'new-academy@example.com',
            },
            'admin': {
                'fullName': 'New Admin',
                'phone': '+2348000000101',
                'email': 'new-admin@example.com',
                'password': 'Strong-Pass-1!',
            },
            'tierId': 't100',
        }

    def test_public_registration_creates_inactive_pending_school_and_admin(self):
        response = self.client.post(
            '/api/v1/schools/register/', self._payload(), format='json',
        )

        self.assertEqual(response.status_code, 201, response.content)
        school = School.objects.get(id=response.json()['schoolId'])
        subscription = SchoolSubscription.objects.get(school=school)
        admin = User.objects.get(email='new-admin@example.com')
        self.assertFalse(school.is_active)
        self.assertEqual(subscription.status, SchoolSubscription.Status.PENDING)
        self.assertEqual(subscription.plan, self.plan)
        self.assertFalse(admin.is_active)
        self.assertFalse(admin.is_verified)
        login_response = self.client.post(
            '/api/v1/auth/login/',
            {'identifier': admin.email, 'password': 'Strong-Pass-1!'},
            format='json',
        )
        self.assertEqual(login_response.status_code, 401)

    def test_payment_verification_never_trusts_a_public_reference(self):
        response = self.client.post(
            '/api/v1/schools/register/', self._payload(), format='json',
        )
        reference = response.json()['paymentRef']

        valid_reference_response = self.client.get(
            f'/api/v1/schools/payments/{reference}/verify/',
        )
        fake_reference_response = self.client.get(
            '/api/v1/schools/payments/FN-not-a-real-payment/verify/',
        )

        self.assertEqual(valid_reference_response.json(), {'status': 'pending'})
        self.assertEqual(fake_reference_response.json(), {'status': 'pending'})
        school = School.objects.get(id=response.json()['schoolId'])
        self.assertFalse(school.is_active)
        self.assertEqual(
            school.subscription.status,
            SchoolSubscription.Status.PENDING,
        )
