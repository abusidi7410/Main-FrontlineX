"""Regression tests for the authorisation defects found in the 2026-09-30 audit.

Each test here corresponds to a bug that was live in production and is now
fixed. They are deliberately written as *denial* tests, because the existing
`test_security.py` suite only asserted the happy path and therefore shipped
every one of these holes:

- a `student` or `parent` login could create and delete staff records
  (records/views.py StaffListView / StaffDetailView carried only
  `IsAuthenticated, HasSchool`, with no role or permission guard at all)
- a `parent` login could rewrite the school's classes and subjects
  (AcademicsView.patch had no guard)
- an anonymous caller could create, rewrite and DELETE subscription plans
  (SubscriptionPlanViewSet was `AllowAny` on a full ModelViewSet)
- `SchoolRegistrationSerializer` referenced `User.Role.ADMIN`, which does not
  exist, so successful self-registration raised AttributeError -> HTTP 500
- `UserManager.create_superuser` demanded a 'superadmin' role that the model
  does not accept, so the only bootstrap path for the first platform user
  raised ValueError
"""

from django.core.management import call_command
from django.test import TestCase
from io import StringIO
from rest_framework.test import APIClient

from accounts.models import User
from records.models import StaffMember
from schools.models import School, SubscriptionPlan


def make_school(slug='sec-academy'):
    return School.objects.create(
        name='Security Academy', slug=slug, address='a', state='Kano',
        lga='Kano', phone='0800', email=f'{slug}@e.com',
    )


class StaffWriteIsCapabilityGuarded(TestCase):
    """Staff mutations must require `staff.write`, not merely a login."""

    def setUp(self):
        self.client = APIClient()
        self.school = make_school('staff-cap')
        self.member = StaffMember.objects.create(school=self.school, full_name='Victim')

    def _login(self, role):
        user = User.objects.create_user(
            email=f'{role}@staff-cap.com', password='Str0ng!Passw0rd',
            role=role, school=self.school,
        )
        self.client.force_authenticate(user=user)
        return user

    def test_student_cannot_create_staff(self):
        self._login('student')
        r = self.client.post('/api/v1/staff/', {
            'fullName': 'Injected', 'email': 'i@x.com', 'phone': '08011111111',
        }, format='json')
        self.assertEqual(r.status_code, 403)
        self.assertEqual(StaffMember.objects.filter(full_name='Injected').count(), 0)

    def test_parent_cannot_create_staff(self):
        self._login('parent')
        r = self.client.post('/api/v1/staff/', {
            'fullName': 'Injected', 'email': 'i@x.com', 'phone': '08011111111',
        }, format='json')
        self.assertEqual(r.status_code, 403)
        self.assertEqual(StaffMember.objects.filter(full_name='Injected').count(), 0)

    def test_student_cannot_delete_staff(self):
        self._login('student')
        r = self.client.delete(f'/api/v1/staff/{self.member.id}/')
        self.assertEqual(r.status_code, 403)
        self.assertTrue(StaffMember.objects.filter(id=self.member.id).exists())

    def test_teacher_cannot_delete_staff(self):
        self._login('teacher')
        r = self.client.delete(f'/api/v1/staff/{self.member.id}/')
        self.assertEqual(r.status_code, 403)
        self.assertTrue(StaffMember.objects.filter(id=self.member.id).exists())

    def test_school_admin_can_still_create_and_delete_staff(self):
        """The fix must not lock out the roles that legitimately own staff."""
        self._login('school_admin')
        created = self.client.post('/api/v1/staff/', {
            'fullName': 'Legit New Teacher', 'email': 'new@x.com', 'phone': '08022222222',
        }, format='json')
        self.assertEqual(created.status_code, 201)
        removed = self.client.delete(f'/api/v1/staff/{self.member.id}/')
        self.assertEqual(removed.status_code, 204)
        self.assertFalse(StaffMember.objects.filter(id=self.member.id).exists())

    def test_principal_can_still_write_staff(self):
        self._login('principal')
        r = self.client.post('/api/v1/staff/', {
            'fullName': 'HOD', 'email': 'hod@x.com', 'phone': '08033333333',
        }, format='json')
        self.assertEqual(r.status_code, 201)

    def test_student_can_still_read_staff(self):
        """Reading staff is not a write capability and must keep working."""
        self._login('student')
        r = self.client.get('/api/v1/staff/')
        self.assertEqual(r.status_code, 200)


class AcademicsWriteIsCapabilityGuarded(TestCase):
    """Class/subject configuration is a write capability, not a login side-effect."""

    def setUp(self):
        self.client = APIClient()
        self.school = make_school('acad-cap')

    def _login(self, role):
        user = User.objects.create_user(
            email=f'{role}@acad-cap.com', password='Str0ng!Passw0rd',
            role=role, school=self.school,
        )
        self.client.force_authenticate(user=user)
        return user

    def test_student_cannot_patch_academics(self):
        self._login('student')
        r = self.client.patch(
            '/api/v1/academics/',
            {'classes': ['Hacked'], 'currentSession': '2099/2100'},
            format='json',
        )
        self.assertEqual(r.status_code, 403)
        self.school.refresh_from_db()
        self.assertNotIn('Hacked', self.school.classes or [])

    def test_parent_cannot_patch_academics(self):
        self._login('parent')
        r = self.client.patch('/api/v1/academics/', {'session': '2099/2100'}, format='json')
        self.assertEqual(r.status_code, 403)

    def test_school_admin_can_still_patch_academics(self):
        self._login('school_admin')
        r = self.client.patch(
            '/api/v1/academics/',
            {'session': '2026/2027', 'term': 'First Term'},
            format='json',
        )
        self.assertEqual(r.status_code, 200, r.data)
        self.school.refresh_from_db()
        self.assertEqual(self.school.current_session, '2026/2027')

    def test_student_can_still_read_academics(self):
        self._login('student')
        r = self.client.get('/api/v1/academics/')
        self.assertEqual(r.status_code, 200)


class SubscriptionPlansAreNotPubliclyWritable(TestCase):
    """Pricing is public to read and superadmin-only to change."""

    def setUp(self):
        self.client = APIClient()
        self.plan = SubscriptionPlan.objects.create(
            name='Real Plan', min_students=1, max_students=100, monthly_price='5000')
        make_school('plans-sec')

    def test_anonymous_cannot_create_plan(self):
        r = self.client.post('/api/v1/schools/plans/', {
            'name': 'HACKED', 'min_students': 1, 'max_students': 999999,
            'monthly_price': '1.00',
        }, format='json')
        self.assertEqual(r.status_code, 401)
        self.assertFalse(SubscriptionPlan.objects.filter(name='HACKED').exists())

    def test_anonymous_cannot_update_plan(self):
        r = self.client.patch(
            f'/api/v1/schools/plans/{self.plan.id}/',
            {'monthly_price': '1.00'}, format='json')
        self.assertIn(r.status_code, (401, 403))
        self.plan.refresh_from_db()
        self.assertNotEqual(str(self.plan.monthly_price), '1.00')

    def test_anonymous_cannot_delete_plan(self):
        r = self.client.delete(f'/api/v1/schools/plans/{self.plan.id}/')
        self.assertIn(r.status_code, (401, 403))
        self.assertTrue(SubscriptionPlan.objects.filter(id=self.plan.id).exists())

    def test_anonymous_can_still_list_and_retrieve_plans(self):
        """Onboarding reads pricing before anyone has logged in."""
        self.assertEqual(self.client.get('/api/v1/schools/plans/').status_code, 200)
        self.assertEqual(
            self.client.get(f'/api/v1/schools/plans/{self.plan.id}/').status_code, 200)

    def test_platform_manager_can_still_delete_plan(self):
        user = User.objects.create_user(
            email='pm@plans-sec.com', password='Str0ng!Passw0rd', role='platform_manager')
        self.client.force_authenticate(user=user)
        r = self.client.delete(f'/api/v1/schools/plans/{self.plan.id}/')
        self.assertEqual(r.status_code, 204)
        self.assertFalse(SubscriptionPlan.objects.filter(id=self.plan.id).exists())


class ValidRoleConstantsAreUsed(TestCase):
    """`User.Role.ADMIN` did not exist; it raised AttributeError -> HTTP 500."""

    def test_role_admin_is_not_referenced_anywhere(self):
        self.assertFalse(hasattr(User.Role, 'ADMIN'))

    def test_school_registration_creates_a_school_admin(self):
        """End-to-end: the public signup path must complete, not 500."""
        self.client = APIClient()
        response = self.client.post('/api/v1/auth/school/register/', {
            'school_name': 'Brand New School',
            'school_type': 'secondary',
            'school_address': '12 Main Street',
            'school_state': 'Kano',
            'school_lga': 'Kano',
            'school_phone': '08033333333',
            'school_email': 'brand@new.com',
            'admin_email': 'owner@new.com',
            'admin_password': 'Str0ng!Passw0rd',
            'admin_password_confirm': 'Str0ng!Passw0rd',
            'admin_first_name': 'Own',
            'admin_last_name': 'Er',
        }, format='json')
        self.assertNotEqual(response.status_code, 500, response.data)
        self.assertEqual(response.status_code, 201, response.data)
        owner = User.objects.get(email='owner@new.com')
        self.assertEqual(owner.role, User.Role.SCHOOL_ADMIN)
        self.assertIsNotNone(owner.school)
        self.assertFalse(owner.is_active)
        self.assertFalse(owner.school.is_active)
        self.assertEqual(owner.school.subscription.status, 'pending')
        self.assertNotIn('access', response.data)
        self.assertNotIn('refresh_token', response.cookies)
        login_response = self.client.post('/api/v1/auth/login/', {
            'identifier': owner.email,
            'password': 'Str0ng!Passw0rd',
        }, format='json')
        self.assertEqual(login_response.status_code, 401)


class SuperuserBootstrapWorks(TestCase):
    """`create_superuser` demanded a role value the model rejects."""

    def test_create_superuser_assigns_platform_manager(self):
        user = User.objects.create_superuser(
            email='root@super.com', password='Str0ng!Passw0rd')
        self.assertEqual(user.role, User.Role.PLATFORM_MANAGER)
        self.assertTrue(user.is_superuser)
        self.assertTrue(user.is_staff)

    def test_create_superadmin_management_command_succeeds(self):
        """The command prompts on stdin, so drive it through patched input.

        Before the fix this raised ValueError from `create_superuser` because
        the command passes role='platform_manager' while the manager demanded
        'superadmin' - the only documented way to create the first platform
        user was broken.
        """
        import getpass
        from unittest import mock

        answers = iter(['boot2@super.com', 'Boot', 'Admin'])
        with mock.patch('builtins.input', lambda *a: next(answers)), \
                mock.patch.object(getpass, 'getpass', lambda *a: 'Str0ng!Passw0rd'):
            call_command('create_superadmin', stdout=StringIO())

        user = User.objects.get(email='boot2@super.com')
        self.assertEqual(user.role, User.Role.PLATFORM_MANAGER)
        self.assertTrue(user.is_superuser)
