from io import BytesIO
from unittest.mock import patch

from django.test import TestCase
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image

from rest_framework.test import APIClient

from records.models import StaffMember, Student
from schools.models import School
from .models import User
from .services import profile_photos


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

    def test_login_accepts_email_case_insensitively(self):
        response = APIClient().post(
            '/api/v1/auth/login/',
            {'identifier': '  ADMIN@ALPHA.EXAMPLE ', 'password': 'Strong-Pass-1!'},
            format='json',
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()['user']['id'], str(self.admin.id))

    def test_login_accepts_phone_in_local_and_international_formats(self):
        user = User.objects.create_user(
            email='teacher@alpha.example',
            phone='+2348012345678',
            password='Strong-Pass-1!',
            first_name='Phone',
            last_name='Login',
            role=User.Role.TEACHER,
            school=self.school_a,
            is_active=True,
        )
        for phone in ('08012345678', '2348012345678', '+2348012345678'):
            with self.subTest(phone=phone):
                response = APIClient().post(
                    '/api/v1/auth/login/',
                    {'identifier': phone, 'password': 'Strong-Pass-1!'},
                    format='json',
                )
                self.assertEqual(response.status_code, 200, response.content)
                self.assertEqual(response.json()['user']['id'], str(user.id))

    def test_login_reports_staff_id_for_staff_linked_users_only(self):
        staff = StaffMember.objects.create(
            school=self.school_a,
            full_name='Class Teacher',
            email='classteacher@alpha.example',
            phone='+2348099999999',
            role='teacher',
        )
        teacher = User.objects.create_user(
            email='classteacher@alpha.example',
            password='Strong-Pass-1!',
            first_name='Class',
            last_name='Teacher',
            role=User.Role.TEACHER,
            school=self.school_a,
            is_active=True,
            staff_profile=staff,
        )
        teacher_login = APIClient().post(
            '/api/v1/auth/login/',
            {'identifier': 'classteacher@alpha.example', 'password': 'Strong-Pass-1!'},
            format='json',
        )
        self.assertEqual(teacher_login.status_code, 200, teacher_login.content)
        self.assertEqual(teacher_login.json()['user']['staffId'], str(staff.public_id))

        admin_login = APIClient().post(
            '/api/v1/auth/login/',
            {'identifier': 'admin@alpha.example', 'password': 'Strong-Pass-1!'},
            format='json',
        )
        self.assertEqual(admin_login.status_code, 200, admin_login.content)
        self.assertIsNone(admin_login.json()['user']['staffId'])

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
                'studentId': str(student.public_id),
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
                'studentId': str(student.public_id),
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


class ProfilePhotoAPITests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name='Photo Academy', slug='photo-academy', address='1 Photo St',
            state='Kano', lga='Fagge', phone='+2348000000003',
            email='photo@example.com', is_active=True,
        )
        self.user = User.objects.create_user(
            email='photo-user@example.com',
            password='Strong-Pass-1!',
            first_name='Photo',
            last_name='User',
            role=User.Role.TEACHER,
            school=self.school,
            is_active=True,
        )
        self.client = APIClient()
        self.client.force_authenticate(self.user)
        self.url = '/api/v1/auth/profile/photo/'

    def _image(self, name='profile.png'):
        output = BytesIO()
        Image.new('RGB', (2, 2), color='navy').save(output, format='PNG')
        return SimpleUploadedFile(name, output.getvalue(), content_type='image/png')

    @patch('accounts.services.profile_photos.avatar_url', return_value='https://res.cloudinary.com/demo/image/upload/profile.png')
    @patch('accounts.services.profile_photos.upload_profile_photo', return_value='frontlinex/profile-photos/user-1-new')
    def test_upload_saves_cloudinary_identifier_and_returns_url(self, upload, avatar_url):
        response = self.client.post(
            self.url,
            {'photo': self._image()},
            format='multipart',
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(
            response.data['avatarUrl'],
            'https://res.cloudinary.com/demo/image/upload/profile.png',
        )
        self.user.refresh_from_db()
        self.assertEqual(
            self.user.profile_photo_public_id,
            'frontlinex/profile-photos/user-1-new',
        )
        upload.assert_called_once()
        avatar_url.assert_called_once_with(self.user.profile_photo_public_id)

    def test_upload_rejects_non_image_files(self):
        response = self.client.post(
            self.url,
            {'photo': SimpleUploadedFile('not-image.txt', b'not an image', content_type='text/plain')},
            format='multipart',
        )
        self.assertEqual(response.status_code, 400)
        self.user.refresh_from_db()
        self.assertEqual(self.user.profile_photo_public_id, '')

    @patch('accounts.services.profile_photos.delete_profile_photo')
    @patch('accounts.services.profile_photos.avatar_url', return_value=None)
    def test_remove_clears_photo_reference_and_deletes_cloud_asset(self, avatar_url, delete_photo):
        self.user.profile_photo_public_id = 'frontlinex/profile-photos/old-photo'
        self.user.save(update_fields=['profile_photo_public_id'])
        response = self.client.delete(self.url)
        self.assertEqual(response.status_code, 200, response.content)
        self.assertIsNone(response.data['avatarUrl'])
        self.user.refresh_from_db()
        self.assertEqual(self.user.profile_photo_public_id, '')
        delete_photo.assert_called_once_with('frontlinex/profile-photos/old-photo')

    @patch(
        'accounts.services.profile_photos.upload_profile_photo',
        side_effect=profile_photos.StorageNotConfigured('Profile photo storage is not configured.'),
    )
    def test_upload_reports_missing_cloudinary_configuration(self, upload):
        response = self.client.post(
            self.url,
            {'photo': self._image()},
            format='multipart',
        )
        self.assertEqual(response.status_code, 503)
        self.assertIn('not configured', response.data['detail'])