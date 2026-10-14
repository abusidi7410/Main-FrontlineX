from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

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


class PlatformSchoolListTests(TestCase):
    """The schools list stays bounded and cheap as the tenant count grows."""

    def setUp(self):
        self.platform = User.objects.create_user(
            email='platform@example.com', password='Strong-Pass-1!',
            first_name='Platform', last_name='Manager',
            role=User.Role.PLATFORM_MANAGER, is_active=True,
        )
        plan = SubscriptionPlan.objects.create(
            name='t100', min_students=1, max_students=100, monthly_price=100.00,
        )
        for index in range(3):
            school = School.objects.create(
                name=f'List Academy {index}', slug=f'list-academy-{index}',
                address='1 List Way', state='Kano', lga='Kano Municipal',
                phone=f'+234800000010{index}', email=f'list{index}@example.com',
                is_active=True,
            )
            SchoolSubscription.objects.create(
                school=school, plan=plan, status=SchoolSubscription.Status.ACTIVE,
            )
            Student.objects.create(
                school=school, admission_number=f'LST-{index:03d}',
                first_name='Ada', last_name='Test', gender='female',
                class_name='SS1', status=Student.Status.ACTIVE,
            )
        self.client = APIClient()
        self.client.force_authenticate(self.platform)

    def test_list_is_paginated_with_prefetched_counts(self):
        with self.assertNumQueries(1):
            response = self.client.get('/api/v1/platform/schools/')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['count'], 3)
        self.assertEqual(len(response.data['results']), 3)
        row = response.data['results'][0]
        self.assertEqual(row['students'], 1)
        self.assertEqual(row['status'], 'active')

    def test_list_second_page_and_search(self):
        second = self.client.get(
            '/api/v1/platform/schools/', {'page': 2, 'pageSize': 2},
        )
        self.assertEqual(second.data['count'], 3)
        self.assertEqual(len(second.data['results']), 1)
        searched = self.client.get(
            '/api/v1/platform/schools/', {'search': 'List Academy 1'},
        )
        self.assertEqual(searched.data['count'], 1)


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


class PlatformManagerHardeningTests(TestCase):
    """Platform managers stay global-only: never attached to a school,
    never promotable from the school-user screens."""

    def setUp(self):
        self.platform = User.objects.create_user(
            email='platform@example.com', password='Strong-Pass-1!',
            first_name='Platform', last_name='Manager',
            role=User.Role.PLATFORM_MANAGER, is_active=True,
        )
        self.school = School.objects.create(
            name='Sunrise Academy', slug='sunrise-academy', address='1 Sunrise Way',
            state='Kano', lga='Kano Municipal', phone='+2348000000011',
            email='sunrise@example.com', is_active=True,
        )
        self.admin = User.objects.create_user(
            email='admin@sunrise.example', password='Strong-Pass-1!',
            first_name='Sunrise', last_name='Admin',
            role=User.Role.SCHOOL_ADMIN, school=self.school, is_active=True,
        )
        self.client = APIClient()
        self.client.force_authenticate(self.platform)

    def test_cannot_create_schooled_platform_manager(self):
        resp = self.client.post(
            f'/api/v1/platform/schools/{self.school.id}/users/',
            {'email': 'evil@example.com', 'name': 'Evil PM', 'role': 'platform_manager'},
            format='json',
        )
        self.assertEqual(resp.status_code, 400, resp.content)
        self.assertFalse(User.objects.filter(email='evil@example.com').exists())

    def test_cannot_promote_school_user_to_platform_manager(self):
        resp = self.client.patch(
            f'/api/v1/platform/users/{self.admin.id}/',
            {'role': 'platform_manager'}, format='json',
        )
        self.assertEqual(resp.status_code, 400, resp.content)
        self.admin.refresh_from_db()
        self.assertEqual(self.admin.role, User.Role.SCHOOL_ADMIN)

    def test_schooled_platform_manager_role_is_not_superadmin(self):
        schooled = User.objects.create_user(
            email='schooled@example.com', password='Strong-Pass-1!',
            first_name='Schooled', last_name='PM',
            role=User.Role.PLATFORM_MANAGER, school=self.school, is_active=True,
        )
        other = APIClient()
        other.force_authenticate(schooled)
        resp = other.get('/api/v1/platform/overview/')
        self.assertEqual(resp.status_code, 403)


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
        from billing import services as wallet_services
        from billing.models import WalletTransaction
        wallet_services.credit_wallet(
            self.active_school, 250000,
            category=WalletTransaction.Category.DEPOSIT,
            description='Overview wallet deposit',
        )
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
        self.assertNotIn('mrr', payload)
        self.assertNotIn('mrrTrend', payload)
        self.assertEqual(payload['activeLogins24h'], 1)
        self.assertEqual(payload['failedPayments'], 1)
        self.assertEqual(payload['upcomingRenewals'], 2)
        self.assertEqual(payload['schoolsByStatus']['active'], 1)
        self.assertEqual(payload['schoolsByStatus']['trial'], 1)
        self.assertEqual(payload['schoolsByStatus']['suspended'], 1)
        self.assertEqual(payload['schoolsByStatus']['pending_payment'], 1)
        self.assertEqual(len(payload['atRiskSchools']), 2)
        at_risk_by_name = {row['name']: row for row in payload['atRiskSchools']}
        self.assertEqual(at_risk_by_name['Overview Pending']['failedPayments'], 1)
        self.assertNotIn('mrr', at_risk_by_name['Overview Pending'])

    def test_overview_is_cached_for_the_requested_range(self):
        first = self.client.get('/api/v1/platform/overview/?range=7d')
        second = self.client.get('/api/v1/platform/overview/?range=7d')
        self.assertEqual(first.status_code, 200)
        self.assertEqual(first.json(), second.json())
        self.assertEqual(cache.get('platform:overview:7:all'), second.json())


@override_settings(
    CACHES={
        'default': {
            'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
            'LOCATION': 'platform-wallet-metrics-tests',
        },
    },
)
class PlatformWalletMetricsTests(TestCase):
    """The overview money figures reconcile with the wallet ledger.

    Deposits count only successful deposit credits; charges bucket by
    category; pending/failed rows never move a total. Refunds and
    reversals have their own series so deposits and charges are never
    added together.
    """

    def setUp(self):
        cache.clear()
        self.now = timezone.now()
        self.platform = User.objects.create_user(
            email='wallet-platform@example.com', password='Strong-Pass-1!',
            first_name='Wallet', last_name='Manager',
            role=User.Role.PLATFORM_MANAGER, is_active=True,
        )
        self.school = School.objects.create(
            name='Wallet Academy', slug='wallet-academy', address='1 Wallet Way',
            state='Kano', lga='Kano Municipal', phone='+2348000000111',
            email='wallet@example.com', is_active=True,
        )
        self.other_school = School.objects.create(
            name='Wallet College', slug='wallet-college', address='2 Wallet Way',
            state='Lagos', lga='Ikeja', phone='+2348000000112',
            email='college@example.com', is_active=True,
        )
        for school in (self.school, self.other_school):
            Student.objects.create(
                school=school, admission_number=f'W-{school.slug}',
                first_name='Ada', last_name='Test', gender='female',
                class_name='SS1', status=Student.Status.ACTIVE,
            )
        User.objects.create_user(
            email='wallet-admin@example.com', password='Strong-Pass-1!',
            first_name='Wallet', last_name='Admin',
            role=User.Role.SCHOOL_ADMIN, school=self.school, is_active=True,
        )
        from billing import services as wallet_services
        from billing.models import WalletTransaction
        self._wallet = wallet_services
        self._Txn = WalletTransaction
        self.client = APIClient()
        self.client.force_authenticate(self.platform)

    def tearDown(self):
        cache.clear()

    def _overview(self):
        response = self.client.get('/api/v1/platform/overview/?range=30d')
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()

    def _move_to_month(self, txn, months_ago):
        target = self.now - timedelta(days=32 * months_ago + 1)
        self._Txn.objects.filter(pk=txn.pk).update(created_at=target)

    def test_deposits_total_counts_successful_deposits_only(self):
        _, ok_txn = self._wallet.credit_wallet(
            self.school, 250000,
            category=self._Txn.Category.DEPOSIT, description='Good deposit',
        )
        pending = self._Txn.objects.create(
            school=self.school, reference='W-PENDING-1',
            direction=self._Txn.Direction.CREDIT, amount_kobo=999900,
            category=self._Txn.Category.DEPOSIT,
            status=self._Txn.Status.PENDING, description='In flight',
        )
        failed = self._Txn.objects.create(
            school=self.school, reference='W-FAILED-1',
            direction=self._Txn.Direction.CREDIT, amount_kobo=888800,
            category=self._Txn.Category.DEPOSIT,
            status=self._Txn.Status.FAILED, description='Declined',
        )
        payload = self._overview()
        self.assertEqual(payload['walletDepositsTotal'], 2500.0)
        self.assertEqual(sum(payload['walletDepositsTrend']), 2500.0)
        self.assertEqual(len(payload['walletDepositsTrend']), 6)
        # An older successful deposit lands in its own month bucket, not
        # today's, and still counts toward the total.
        _, old_txn = self._wallet.credit_wallet(
            self.other_school, 100000,
            category=self._Txn.Category.DEPOSIT, description='Old deposit',
        )
        self._move_to_month(old_txn, 2)
        cache.clear()
        payload = self._overview()
        self.assertEqual(payload['walletDepositsTotal'], 3500.0)
        self.assertEqual(payload['walletDepositsTrend'][-1], 2500.0)
        self.assertEqual(payload['walletDepositsTrend'][-3], 1000.0)
        pending.delete()
        failed.delete()
        ok_txn.delete()

    def test_charges_bucket_by_category_and_refunds_stay_separate(self):
        self._wallet.credit_wallet(
            self.school, 500000,
            category=self._Txn.Category.DEPOSIT, description='Funding',
        )
        self._wallet.debit_wallet(
            self.school, 11500,
            category=self._Txn.Category.STUDENT_ACTIVATION,
            description='Activation', what='student access',
        )
        self._wallet.debit_wallet(
            self.school, 57500,
            category=self._Txn.Category.STUDENT_RENEWAL,
            description='Renewal', what='student access',
        )
        self._wallet.debit_wallet(
            self.school, 2000,
            category=self._Txn.Category.SMS_ALERT,
            description='SME alert', what='SME alert',
        )
        self._wallet.credit_wallet(
            self.school, 11500,
            category=self._Txn.Category.REFUND, description='Goodwill refund',
        )
        payload = self._overview()
        # Activation + renewal are one expenditure series; deposits are
        # money in and are never added to charges.
        self.assertEqual(payload['activationChargesTotal'], 690.0)
        self.assertEqual(payload['smsChargesTotal'], 20.0)
        self.assertEqual(payload['refundsTotal'], 115.0)
        self.assertEqual(payload['walletDepositsTotal'], 5000.0)
        self.assertEqual(len(payload['activationChargesTrend']), 6)
        self.assertEqual(len(payload['smsChargesTrend']), 6)
        self.assertEqual(len(payload['refundsTrend']), 6)

    def test_user_and_student_counts_come_from_the_right_tables(self):
        payload = self._overview()
        self.assertEqual(payload['totalUsers'], 1)
        self.assertEqual(payload['totalStudents'], 2)

    def test_empty_platform_reports_zeros_not_nulls(self):
        School.objects.all().delete()
        cache.clear()
        payload = self._overview()
        self.assertEqual(payload['totalUsers'], 0)
        self.assertEqual(payload['totalStudents'], 0)
        self.assertEqual(payload['walletDepositsTotal'], 0)
        self.assertEqual(payload['activationChargesTotal'], 0)
        self.assertEqual(payload['smsChargesTotal'], 0)
        self.assertEqual(payload['refundsTotal'], 0)
        self.assertEqual(payload['walletDepositsTrend'], [0, 0, 0, 0, 0, 0])
        self.assertEqual(payload['schoolsByStatus']['active'], 0)

    def test_school_user_cannot_see_platform_money(self):
        admin = User.objects.get(email='wallet-admin@example.com')
        other = APIClient()
        other.force_authenticate(admin)
        response = other.get('/api/v1/platform/overview/?range=30d')
        self.assertEqual(response.status_code, 403)


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

    def test_public_registration_starts_with_empty_wallet(self):
        response = self.client.post(
            '/api/v1/schools/register/', self._payload(), format='json',
        )

        self.assertEqual(response.status_code, 201, response.content)
        body = response.json()
        school = School.objects.get(id=body['schoolId'])
        admin = User.objects.get(email='new-admin@example.com')
        # No subscription rows: the school starts with a ₦0 wallet instead.
        self.assertFalse(SchoolSubscription.objects.filter(school=school).exists())
        from billing.models import Wallet
        wallet = Wallet.objects.get(school=school)
        self.assertEqual(wallet.balance_kobo, 0)
        self.assertTrue(school.is_active)
        self.assertTrue(admin.is_active)
        self.assertTrue(admin.is_verified)
        self.assertFalse(body['trial'])
        self.assertFalse(body['requiresPayment'])
        login_response = self.client.post(
            '/api/v1/auth/login/',
            {'identifier': admin.email, 'password': 'Strong-Pass-1!'},
            format='json',
        )
        self.assertEqual(login_response.status_code, 200, login_response.content)

    def test_registration_records_declared_student_count(self):
        payload = self._payload()
        payload['school']['expectedStudents'] = 250
        response = self.client.post(
            '/api/v1/schools/register/', payload, format='json',
        )
        self.assertEqual(response.status_code, 201, response.content)
        school = School.objects.get(id=response.json()['schoolId'])
        self.assertEqual(school.expected_students, 250)
        self.assertEqual(response.json()['expectedStudents'], 250)

    def test_registration_rejects_bad_student_count(self):
        payload = self._payload()
        payload['school']['expectedStudents'] = 0
        response = self.client.post(
            '/api/v1/schools/register/', payload, format='json',
        )
        self.assertEqual(response.status_code, 400, response.content)
        self.assertFalse(School.objects.filter(email='new-academy@example.com').exists())

    def test_public_registration_rejection_explains_itself(self):
        payload = self._payload()
        payload['school']['type'] = 'Primary only'
        response = self.client.post(
            '/api/v1/schools/register/', payload, format='json',
        )

        self.assertEqual(response.status_code, 400, response.content)
        body = response.json()
        self.assertTrue(body['detail'])
        self.assertIn('school', body['errors'])
        self.assertFalse(School.objects.filter(email='new-academy@example.com').exists())

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
        self.assertFalse(
            SchoolSubscription.objects.filter(school=school).exists(),
        )


class SchoolLocationRegistrationTests(TestCase):
    """The school's GPS location is captured at registration and editable later."""

    def setUp(self):
        self.client = APIClient()
        SubscriptionPlan.objects.create(
            name='t100', min_students=1, max_students=100, monthly_price=100.00,
        )

    def _payload(self, **school_overrides):
        school = {
            'name': 'Located Academy',
            'type': 'primary',
            'address': '1 Located Road',
            'state': 'Lagos',
            'lga': 'Ikeja',
            'phone': '+2348000000200',
            'email': 'located@example.com',
        }
        school.update(school_overrides)
        return {
            'school': school,
            'admin': {
                'fullName': 'Located Admin',
                'phone': '+2348000000201',
                'email': 'located-admin@example.com',
                'password': 'Strong-Pass-1!',
            },
            'tierId': 't100',
        }

    def test_registration_stores_coordinates_and_timezone(self):
        response = self.client.post(
            '/api/v1/schools/register/',
            self._payload(latitude=6.5244, longitude=3.3792, gpsAccuracy=12.5),
            format='json',
        )
        self.assertEqual(response.status_code, 201, response.content)
        school = School.objects.get(id=response.json()['schoolId'])
        self.assertAlmostEqual(float(school.latitude), 6.5244, places=4)
        self.assertAlmostEqual(float(school.longitude), 3.3792, places=4)
        self.assertEqual(school.gps_accuracy, 12.5)
        self.assertEqual(school.timezone, 'Africa/Lagos')
        self.assertIsNotNone(school.location_set_at)

    def test_registration_can_omit_location(self):
        response = self.client.post(
            '/api/v1/schools/register/', self._payload(), format='json',
        )
        self.assertEqual(response.status_code, 201, response.content)
        school = School.objects.get(id=response.json()['schoolId'])
        self.assertIsNone(school.latitude)
        self.assertIsNone(school.longitude)
        self.assertIsNone(school.location_set_at)

    def test_registration_rejects_a_lone_coordinate(self):
        response = self.client.post(
            '/api/v1/schools/register/',
            self._payload(latitude=6.5244),
            format='json',
        )
        self.assertEqual(response.status_code, 400, response.content)

    def test_profile_patch_updates_location_and_confirms_it(self):
        response = self.client.post(
            '/api/v1/schools/register/', self._payload(), format='json',
        )
        school = School.objects.get(id=response.json()['schoolId'])
        admin = User.objects.get(email='located-admin@example.com')
        self.client.force_authenticate(admin)

        patch = self.client.patch(
            '/api/v1/schools/profile/',
            {'latitude': 6.5, 'longitude': 3.4, 'attendance_radius': 250},
            format='json',
        )
        self.assertEqual(patch.status_code, 200, patch.content)
        school.refresh_from_db()
        self.assertAlmostEqual(float(school.latitude), 6.5, places=4)
        self.assertEqual(school.attendance_radius, 250)
        self.assertIsNotNone(school.location_set_at)
        self.assertIsNotNone(school.location_confirmed_at)
        # The session shape the Settings screen merges back in.
        self.assertEqual(patch.json()['latitude'], 6.5)
        self.assertEqual(patch.json()['attendanceRadius'], 250)

    def test_reverse_geocode_is_proxied_and_validated(self):
        school = School.objects.create(
            name='Geo School', slug='geo-school', address='1 Geo Way',
            state='Lagos', lga='Ikeja', phone='+2348000000300',
            email='geo@example.com', is_active=True,
        )
        admin = User.objects.create_user(
            email='geo-admin@example.com', password='Strong-Pass-1!',
            first_name='Geo', last_name='Admin',
            role=User.Role.SCHOOL_ADMIN, school=school, is_active=True,
        )
        self.client.force_authenticate(admin)

        bad = self.client.get('/api/v1/schools/reverse-geocode/?lat=abc&lng=3.4')
        self.assertEqual(bad.status_code, 400, bad.content)

        with patch('schools.views.reverse_geocode') as geocoder:
            geocoder.return_value = {
                'label': '1 Geo Way, Ikeja, Lagos',
                'address': {'road': '1 Geo Way'},
                'latitude': 6.5,
                'longitude': 3.4,
            }
            ok = self.client.get('/api/v1/schools/reverse-geocode/?lat=6.5&lng=3.4')
        self.assertEqual(ok.status_code, 200, ok.content)
        self.assertEqual(ok.json()['location']['label'], '1 Geo Way, Ikeja, Lagos')
        geocoder.assert_called_once()

    def test_anonymous_cannot_reverse_geocode(self):
        response = self.client.get('/api/v1/schools/reverse-geocode/?lat=6.5&lng=3.4')
        self.assertIn(response.status_code, (401, 403))
