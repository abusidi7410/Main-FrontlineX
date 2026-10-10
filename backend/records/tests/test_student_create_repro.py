"""Reproduce the 'add student fails' report against the real create endpoint.

Run with:  manage.py test records.tests.test_student_create_repro
Prints the actual status code and body so the failure mode is visible.
"""
from rest_framework.test import APIClient

from accounts.models import User
from records.models import AcademicSession, SchoolClass, Student
from schools.models import School

from .test_security import SecurityTestBase


class StudentCreateReproTests(SecurityTestBase):
    def _post(self, payload, user=None):
        client = APIClient()
        client.force_authenticate(user or self.admin)
        return client.post('/api/v1/students/', payload, format='json')

    def assertFieldError(self, response, field, fragment):
        """Assert a 400 carrying a readable message for `field`.

        These assertions are the point of the module: the bug being guarded
        against was a validation failure that reached the user as either a bare
        500 or a generic "we couldn't save this" toast, so the wording matters
        as much as the status code.
        """
        self.assertEqual(response.status_code, 400, response.content)
        message = response.json()['fieldErrors'][field]
        self.assertIn(fragment, message)

    def test_admin_create_exactly_as_the_ui_sends_it(self):
        payload = {
            'firstName': 'Ada',
            'lastName': 'Nwosu',
            'admissionNumber': 'SUA/JSS/2026/000777',
            'gender': 'female',
            'dateOfBirth': '2014-05-02',
            'className': 'JSS 1',
            'arm': 'A',
            'guardianName': 'Mrs N',
            'guardianPhone': '+234800',
        }
        r = self._post(payload)
        self.assertEqual(r.status_code, 201, r.content)

    def test_duplicate_admission_number(self):
        payload = {
            'firstName': 'Ada',
            'lastName': 'Nwosu',
            'admissionNumber': self.student.admission_number,
            'gender': 'female',
            'className': 'JSS 1',
            'arm': 'A',
            'guardianName': 'Mrs N',
            'guardianPhone': '+234800',
        }
        r = self._post(payload)
        # A duplicate must be a readable 400, not the 500 this originally threw.
        self.assertFieldError(r, 'admissionNumber', 'already used by another student')
        self.assertEqual(Student.objects.filter(first_name='Ada').count(), 0)

    def test_teacher_create(self):
        payload = {
            'firstName': 'Grace',
            'lastName': 'Hopper',
            'admissionNumber': 'SUA/JSS/2026/000888',
            'gender': 'female',
            'className': 'JSS 1',
            'arm': 'A',
            'guardianName': 'Mr H',
            'guardianPhone': '+234800',
        }
        r = self._post(payload, self.teacher)
        self.assertEqual(r.status_code, 403)
        self.assertEqual(Student.objects.filter(first_name='Grace').count(), 0)

    def test_create_with_body_carrying_school_field(self):
        payload = {
            'firstName': 'Alan',
            'lastName': 'Turing',
            'admissionNumber': 'SUA/JSS/2026/000999',
            'gender': 'male',
            'className': 'JSS 1',
            'arm': 'A',
            'guardianName': 'Mr T',
            'guardianPhone': '+234800',
            'schoolId': str(self.other_school.id),
        }
        r = self._post(payload)
        self.assertFieldError(r, 'schoolId', 'taken from your account')
        self.assertEqual(Student.objects.filter(first_name='Alan').count(), 0)

    def test_create_with_school_key(self):
        payload = {
            'firstName': 'Kay',
            'lastName': 'Ten',
            'admissionNumber': 'SUA/JSS/2026/001000',
            'gender': 'male',
            'className': 'JSS 1',
            'arm': 'A',
            'guardianName': 'Mr K',
            'guardianPhone': '+234800',
            'school': str(self.school.id),
        }
        r = self._post(payload)
        self.assertFieldError(r, 'school', 'taken from your account')
        self.assertEqual(Student.objects.filter(first_name='Kay').count(), 0)

    def test_create_missing_optional_but_required_by_serializer_fields(self):
        """The serializer marks guardian fields required; the form may not send them."""
        payload = {
            'firstName': 'Noor',
            'lastName': 'Bello',
            'admissionNumber': 'SUA/JSS/2026/001111',
            'gender': 'female',
            'className': 'JSS 1',
        }
        r = self._post(payload)
        # Named field errors, so the UI can point at the offending inputs.
        errors = r.json()['fieldErrors']
        self.assertEqual(r.status_code, 400)
        self.assertIn('guardianName', errors)
        self.assertIn('guardianPhone', errors)

    def test_server_generates_the_number_when_omitted(self):
        """The default path: no admissionNumber in the body, server mints one."""
        payload = {
            'firstName': 'Generated',
            'lastName': 'Student',
            'gender': 'male',
            'dateOfBirth': '2013-01-01',
            'className': 'JSS 1',
            'arm': 'A',
            'guardianName': 'Mr G',
            'guardianPhone': '+2348001112222',
        }
        r = self._post(payload)
        self.assertEqual(r.status_code, 201, r.content)
        number = r.json()['admissionNumber']
        self.assertRegex(number, r'^SUA/JSS/\d{4}/\d{6}$')

    def test_generated_numbers_are_sequential(self):
        base = {
            'gender': 'male', 'className': 'JSS 1', 'arm': 'A',
            'guardianName': 'Mr S', 'guardianPhone': '+2348001112222',
            'dateOfBirth': '2013-01-01',
        }
        first = self._post({**base, 'firstName': 'S', 'lastName': 'One'})
        second = self._post({**base, 'firstName': 'S', 'lastName': 'Two'})
        self.assertEqual(first.status_code, 201, first.content)
        self.assertEqual(second.status_code, 201, second.content)
        n1, n2 = first.json()['admissionNumber'], second.json()['admissionNumber']
        self.assertNotEqual(n1, n2)
        self.assertEqual(int(n2.rsplit('/', 1)[1]), int(n1.rsplit('/', 1)[1]) + 1)

    def test_generated_number_is_marked_system_generated(self):
        payload = {
            'firstName': 'Prov', 'lastName': 'Enance', 'gender': 'male',
            'className': 'JSS 1', 'arm': 'A', 'guardianName': 'Mr P',
            'guardianPhone': '+2348001112222', 'dateOfBirth': '2013-01-01',
        }
        r = self._post(payload)
        self.assertEqual(r.status_code, 201, r.content)
        student = Student.objects.get(public_id=r.json()['id'])
        self.assertEqual(
            student.admission_number_source, Student.AdmissionNumberSource.SYSTEM_GENERATED,
        )

    def test_supplied_number_is_kept(self):
        payload = {
            'firstName': 'Custom', 'lastName': 'Number', 'gender': 'female',
            'admissionNumber': 'LEGACY/2019/07', 'className': 'JSS 1',
            'arm': 'A', 'guardianName': 'Ms C', 'guardianPhone': '+2348001112222',
            'dateOfBirth': '2013-01-01',
        }
        r = self._post(payload)
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(r.json()['admissionNumber'], 'LEGACY/2019/07')

    def test_generation_still_works_when_school_already_has_a_code(self):
        """A confirmed code is the source of truth and is never recalculated."""
        self.assertEqual(self.school.code, 'SUA')
        r = self._post({
            'firstName': 'Coded', 'lastName': 'Twice', 'gender': 'male',
            'className': 'JSS 1', 'arm': 'A', 'guardianName': 'Mr C',
            'guardianPhone': '+2348001112222', 'dateOfBirth': '2013-01-01',
        })
        self.assertEqual(r.status_code, 201, r.content)
        self.assertTrue(r.json()['admissionNumber'].startswith('SUA/'))

    def test_school_code_is_derived_when_not_already_set(self):
        """A school with no stored code gets one derived from its name, once."""

        # A school that never confirmed a code, as on a fresh registration.
        uncoded = School.objects.create(
            name='Hope Academy', slug='hope-academy', code='',
            address='3 Hope Way', state='Kano', lga='Kano Municipal',
            is_active=True, current_session='2026/2027',
        )
        boss = User.objects.create_user(
            email='boss@hope.example', password='Strong-Pass-1!',
            role=User.Role.SCHOOL_ADMIN, school=uncoded, is_active=True,
        )
        AcademicSession.objects.create(
            school=uncoded, name='2026/2027', start_year=2026, end_year=2027,
            is_current=True,
        )
        SchoolClass.objects.create(
            school=uncoded, level=self.jss_level, name='JSS 1',
        )
        client = APIClient()
        client.force_authenticate(boss)
        r = client.post('/api/v1/students/', {
            'firstName': 'Coded', 'lastName': 'School', 'gender': 'male',
            'className': 'JSS 1', 'arm': 'A', 'guardianName': 'Mr H',
            'guardianPhone': '+2348001112222', 'dateOfBirth': '2013-01-01',
        }, format='json')
        self.assertEqual(r.status_code, 201, r.content)
        uncoded.refresh_from_db()
        self.assertEqual(uncoded.code, 'HA')
        self.assertTrue(r.json()['admissionNumber'].startswith('HA/'))

    def test_generated_number_uses_the_admission_year_not_today(self):
        """The year segment comes from the current session's start year."""
        self.session.start_year = 2019
        self.session.save(update_fields=['start_year'])
        payload = {
            'firstName': 'Year', 'lastName': 'Test', 'gender': 'male',
            'className': 'JSS 1', 'arm': 'A', 'guardianName': 'Mr Y',
            'guardianPhone': '+2348001112222', 'dateOfBirth': '2013-01-01',
        }
        r = self._post(payload)
        self.assertEqual(r.status_code, 201, r.content)
        self.assertIn('/2019/', r.json()['admissionNumber'])
        student = Student.objects.get(public_id=r.json()['id'])
        self.assertEqual(student.admission_year, 2019)

    def test_generation_is_scoped_per_school(self):
        """Two schools issuing numbers independently never collide."""
        base = {
            'gender': 'male', 'className': 'JSS 1', 'arm': 'A',
            'guardianName': 'Mr X', 'guardianPhone': '+2348001112222',
            'dateOfBirth': '2013-01-01',
        }
        mine = self._post({**base, 'firstName': 'Mine', 'lastName': 'One'})
        self.assertEqual(mine.status_code, 201, mine.content)
        client = APIClient()
        client.force_authenticate(self.other_admin)
        theirs = client.post(
            '/api/v1/students/', {**base, 'firstName': 'Theirs', 'lastName': 'One'},
            format='json',
        )
        self.assertEqual(theirs.status_code, 201, theirs.content)
        self.assertNotEqual(mine.json()['admissionNumber'], theirs.json()['admissionNumber'])

    def test_create_with_empty_class_name(self):
        payload = {
            'firstName': 'Empty',
            'lastName': 'Class',
            'admissionNumber': 'SUA/JSS/2026/001222',
            'gender': 'male',
            'className': '',
            'arm': '',
            'guardianName': 'x',
            'guardianPhone': 'y',
        }
        r = self._post(payload)
