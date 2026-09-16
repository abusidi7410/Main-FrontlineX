from django.test import TestCase

from rest_framework.test import APIClient

from records.models import StaffMember, Student
from schools.models import School
from .models import User


class AccountManagementAPITests(TestCase):
    def setUp(self):
        self.school_a = School.objects.create(
            name='Alpha Academy', slug='alpha-academy', address='1 Alpha St',
            state='Kano', lga='Fagge', phone='+2348000000001', email='alpha@example.com',
            is_active=True,
        )
        self.school_b = School.objects.create(
            name='Beta College', slug='beta-college', address='1 Beta St',
            state='Lagos', lga='Ikeja', phone='+2348000000002', email='beta@example.com',
            is_active=True,
        )
        self.admin = User.objects.create_user(
            email='admin@alpha.example',
            password='Strong-Pass-1!',
            first_name='Alpha',
            last_name='Admin',
            role=User.Role.SCHOOL_ADMIN,
            school=self.school_a,
            is_active=True,
        )
        self.client = APIClient()

    def _auth(self, user):
        self.client.force_authenticate(user)

    def _list_url(self, **query):
        params = '&'.join(f'{k}={v}' for k, v in query.items())
        return f'/api/v1/accounts/users/?{params}' if params else '/api/v1/accounts/users/'

    # ── create ────────────────────────────────────────────────────────────

    def test_admin_can_create_teacher_with_auto_password(self):
        self._auth(self.admin)
        resp = self.client.post(
            '/api/v1/accounts/users/',
            {
                'fullName': 'Maimuna Sani',
                'email': 'maimuna@alpha.example',
                'phone': '+2348011111111',
                'role': 'teacher',
            },
            format='json',
        )
        self.assertEqual(resp.status_code, 201, resp.content)
        body = resp.json()
        self.assertEqual(body['role'], 'teacher')
        self.assertEqual(body['status'], 'active')
        self.assertTrue(body['mustChangePassword'])
        creds = body['defaultCredentials']
        self.assertEqual(creds['email'], 'maimuna@alpha.example')
        self.assertTrue(creds['password'])

        # The generated password actually logs the new user in.
        login = APIClient().post(
            '/api/v1/auth/login/',
            {'identifier': 'maimuna@alpha.example', 'password': creds['password']},
            format='json',
        )
        self.assertEqual(login.status_code, 200, login.content)
        self.assertEqual(login.json()['user']['role'], 'teacher')

    def test_create_with_explicit_password_does_not_force_change(self):
        self._auth(self.admin)
        resp = self.client.post(
            '/api/v1/accounts/users/',
            {
                'fullName': 'Amina Lawal',
                'email': 'amina@alpha.example',
                'role': 'secretary',
                'password': 'Chosen-Pass-2026!',
            },
            format='json',
        )
        body = resp.json()
        self.assertEqual(resp.status_code, 201)
        self.assertFalse(body['mustChangePassword'])
        self.assertNotIn('defaultCredentials', body)

    def test_duplicate_email_rejected(self):
        self._auth(self.admin)
        resp = self.client.post(
            '/api/v1/accounts/users/',
            {
                'fullName': 'Dup User',
                'email': 'admin@alpha.example',
                'role': 'teacher',
            },
            format='json',
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn('email', resp.json()['fieldErrors'])

    def test_student_account_requires_linked_student(self):
        self._auth(self.admin)
        resp = self.client.post(
            '/api/v1/accounts/users/',
            {
                'fullName': 'Student One',
                'email': 'student1@alpha.example',
                'role': 'student',
            },
            format='json',
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn('studentId', resp.json()['fieldErrors'])

    def test_student_account_links_to_school_student(self):
        student = Student.objects.create(
            school=self.school_a, admission_number='ALP-001',
            first_name='Maryam', last_name='Yusuf', gender='female',
            class_name='SS1', status=Student.Status.ACTIVE,
        )
        self._auth(self.admin)
        resp = self.client.post(
            '/api/v1/accounts/users/',
            {
                'fullName': 'Maryam Yusuf',
                'email': 'maryam@alpha.example',
                'role': 'student',
                'studentId': str(student.id),
            },
            format='json',
        )
        self.assertEqual(resp.status_code, 201, resp.content)
        self.assertEqual(resp.json()['student']['admissionNumber'], 'ALP-001')

    def test_cannot_link_student_from_another_school(self):
        student = Student.objects.create(
            school=self.school_b, admission_number='BET-001',
            first_name='Other', last_name='Student', gender='male',
            class_name='JSS1', status=Student.Status.ACTIVE,
        )
        self._auth(self.admin)
        resp = self.client.post(
            '/api/v1/accounts/users/',
            {
                'fullName': 'Nope Nope',
                'email': 'nope@alpha.example',
                'role': 'student',
                'studentId': str(student.id),
            },
            format='json',
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn('studentId', resp.json()['fieldErrors'])

    def test_student_account_can_link_by_admission_number(self):
        Student.objects.create(
            school=self.school_a, admission_number='ALP-042',
            first_name='Yetunde', last_name='Okafor', gender='female',
            class_name='JSS2', status=Student.Status.ACTIVE,
        )
        self._auth(self.admin)
        resp = self.client.post(
            '/api/v1/accounts/users/',
            {
                'fullName': 'Yetunde Okafor',
                'email': 'yetunde@alpha.example',
                'role': 'student',
                'admissionNumber': 'alp-042',
            },
            format='json',
        )
        self.assertEqual(resp.status_code, 201, resp.content)
        self.assertEqual(resp.json()['student']['admissionNumber'], 'ALP-042')

    def test_admission_number_from_another_school_rejected(self):
        Student.objects.create(
            school=self.school_b, admission_number='BET-042',
            first_name='Other', last_name='Student', gender='male',
            class_name='JSS1', status=Student.Status.ACTIVE,
        )
        self._auth(self.admin)
        resp = self.client.post(
            '/api/v1/accounts/users/',
            {
                'fullName': 'Ghost Student',
                'email': 'ghost@alpha.example',
                'role': 'student',
                'admissionNumber': 'BET-042',
            },
            format='json',
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn('admissionNumber', resp.json()['fieldErrors'])

    def test_secretary_cannot_create_teacher(self):
        secretary = User.objects.create_user(
            email='sec@alpha.example', password='Strong-Pass-1!',
            first_name='Sec', last_name='Retary', role=User.Role.SECRETARY,
            school=self.school_a, is_active=True,
        )
        self._auth(secretary)
        resp = self.client.post(
            '/api/v1/accounts/users/',
            {
                'fullName': 'Teacher X',
                'email': 'teacherx@alpha.example',
                'role': 'teacher',
            },
            format='json',
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn('role', resp.json()['fieldErrors'])

    def test_accountant_cannot_access_endpoint(self):
        accountant = User.objects.create_user(
            email='fin@alpha.example', password='Strong-Pass-1!',
            first_name='Fin', last_name='Ance', role=User.Role.ACCOUNTANT,
            school=self.school_a, is_active=True,
        )
        self._auth(accountant)
        resp = self.client.get('/api/v1/accounts/users/')
        self.assertEqual(resp.status_code, 403)

    # ── list / scope ──────────────────────────────────────────────────────

    def test_list_is_school_scoped_and_paginated(self):
        User.objects.create_user(
            email='t1@alpha.example', password='Strong-Pass-1!',
            first_name='T', last_name='One', role=User.Role.TEACHER,
            school=self.school_a, is_active=True,
        )
        User.objects.create_user(
            email='t2@beta.example', password='Strong-Pass-1!',
            first_name='T', last_name='Two', role=User.Role.TEACHER,
            school=self.school_b, is_active=True,
        )
        self._auth(self.admin)
        resp = self.client.get(self._list_url(role='teacher'))
        body = resp.json()
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(body['count'], 1)
        self.assertEqual(body['results'][0]['email'], 't1@alpha.example')

    def test_search_by_name_or_email(self):
        User.objects.create_user(
            email='findme@alpha.example', password='Strong-Pass-1!',
            first_name='Zainab', last_name='Kabir', role=User.Role.TEACHER,
            school=self.school_a, is_active=True,
        )
        self._auth(self.admin)
        body = self.client.get(self._list_url(search='zainab')).json()
        self.assertEqual(body['count'], 1)
        body = self.client.get(self._list_url(search='findme')).json()
        self.assertEqual(body['count'], 1)
        body = self.client.get(self._list_url(search='nomatch')).json()
        self.assertEqual(body['count'], 0)

    # ── update / status / password ────────────────────────────────────────

    def test_activate_deactivate_and_reset_password(self):
        teacher = User.objects.create_user(
            email='t3@alpha.example', password='Strong-Pass-1!',
            first_name='T', last_name='Three', role=User.Role.TEACHER,
            school=self.school_a, is_active=True,
        )
        self._auth(self.admin)

        deact = self.client.post(f'/api/v1/accounts/users/{teacher.id}/deactivate/')
        self.assertEqual(deact.status_code, 200)
        self.assertEqual(deact.json()['status'], 'inactive')

        act = self.client.post(f'/api/v1/accounts/users/{teacher.id}/activate/')
        self.assertEqual(act.json()['status'], 'active')

        reset = self.client.post(f'/api/v1/accounts/users/{teacher.id}/reset-password/')
        body = reset.json()
        new_password = body['defaultCredentials']['password']
        self.assertTrue(body['defaultCredentials']['mustChangePassword'])

        login = APIClient().post(
            '/api/v1/auth/login/',
            {'identifier': 't3@alpha.example', 'password': new_password},
            format='json',
        )
        self.assertEqual(login.status_code, 200)

    def test_last_active_admin_cannot_be_deactivated(self):
        self._auth(self.admin)
        resp = self.client.post(f'/api/v1/accounts/users/{self.admin.id}/deactivate/')
        self.assertEqual(resp.status_code, 400)

    def test_cannot_modify_other_school_account(self):
        other_admin = User.objects.create_user(
            email='admin@beta.example', password='Strong-Pass-1!',
            first_name='Beta', last_name='Admin', role=User.Role.SCHOOL_ADMIN,
            school=self.school_b, is_active=True,
        )
        self._auth(self.admin)
        resp = self.client.patch(
            f'/api/v1/accounts/users/{other_admin.id}/',
            {'fullName': 'Hacked Name'},
            format='json',
        )
        self.assertEqual(resp.status_code, 404)

    def test_audit_logged_on_create(self):
        self._auth(self.admin)
        self.client.post(
            '/api/v1/accounts/users/',
            {
                'fullName': 'Audit Test',
                'email': 'audit@alpha.example',
                'role': 'teacher',
            },
            format='json',
        )
        from schools.models import AuditLog
        self.assertTrue(
            AuditLog.objects.filter(action='account.created').exists(),
        )