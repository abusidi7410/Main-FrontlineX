from django.test import TestCase

from rest_framework.test import APIClient

from accounts.models import User
from records.models import Student
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