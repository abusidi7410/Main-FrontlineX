"""Phase 1 security tests.

Covers the vulnerabilities closed in Phase 1:

* student create — role check, tenant isolation, spoofed school/class rejection
* student PATCH  — role check, cross-school rejection, school-reassignment
* attendance      — roster follows `Enrollment`, not `Student.class_name`
* transfer        — cross-school source and destination rejected

Each test calls the API directly. Nothing here relies on a hidden button, a
route guard or any client-side check.
"""
from __future__ import annotations

from decimal import Decimal

from django.urls import reverse

from accounts.models import User
from records.models import (
    AcademicSession,
    AttendanceRecord,
    Enrollment,
    Invoice,
    Level,
    SchoolClass,
    Section,
    Student,
)
from schools.models import School, SchoolSubscription, SubscriptionPlan

from .base import SchoolTestCase

STUDENT_PAYLOAD = {
    'firstName': 'Ada',
    'lastName': 'Nwosu',
    'gender': 'female',
    'admissionNumber': 'SUA/JSS/2026/009001',
    'className': 'JSS 1',
    'arm': 'A',
    'guardianName': 'Mrs Nwosu',
    'guardianPhone': '+2348000001234',
    'dateOfBirth': '2014-05-02',
}


class SecurityTestBase(SchoolTestCase):
    """Two schools with a full academic structure, plus users for every role."""

    def setUp(self):
        super().setUp()
        self.other_session = AcademicSession.objects.get(school=self.other_school)
        self.other_level = Level.objects.create(
            school=self.other_school, code=Level.JUNIOR_SECONDARY,
            name='Junior Secondary', sort_order=30,
        )
        self.other_jss1 = SchoolClass.objects.create(
            school=self.other_school, level=self.other_level, name='JSS 1',
        )
        self.other_section = Section.objects.create(
            school=self.other_school, class_obj=self.other_jss1, name='Z',
        )

        self.student = Student.objects.create(
            school=self.school, admission_number='SUA/JSS/2026/000100',
            first_name='Amina', last_name='Bello', gender='female',
            class_name='JSS 1', arm='A', status=Student.Status.ACTIVE,
        )
        self.other_student = Student.objects.create(
            school=self.other_school, admission_number='RVC/JSS/2026/000100',
            first_name='Chidi', last_name='Nwachukwu', gender='male',
            class_name='JSS 1', status=Student.Status.ACTIVE,
        )
        self.section_a = Section.objects.create(
            school=self.school, class_obj=self.jss1, name='A',
        )
        Enrollment.objects.create(
            school=self.school, student=self.student, academic_session=self.session,
            class_obj=self.jss1, section=self.section_a,
            status=Enrollment.Status.ACTIVE,
        )

    def roster(self, **params):
        return self.client.get(self.url('/attendance/roster/'), params)


# ── 1. Student create authorization ─────────────────────────────────────────

class StudentCreateAuthorizationTests(SecurityTestBase):
    def test_unauthenticated_request_is_rejected(self):
        self.client.force_authenticate(user=None)
        resp = self.client.post(self.url('/students/'), STUDENT_PAYLOAD, format='json')
        self.assertEqual(resp.status_code, 401)
        self.assertFalse(Student.objects.filter(first_name='Ada').exists())

    def test_teacher_cannot_create_a_student(self):
        self.auth(self.teacher)
        resp = self.client.post(self.url('/students/'), STUDENT_PAYLOAD, format='json')
        self.assertEqual(resp.status_code, 403)
        self.assertFalse(Student.objects.filter(first_name='Ada').exists())

    def test_accountant_cannot_create_a_student(self):
        self.auth(self.accountant)
        resp = self.client.post(self.url('/students/'), STUDENT_PAYLOAD, format='json')
        self.assertEqual(resp.status_code, 403)
        self.assertFalse(Student.objects.filter(first_name='Ada').exists())

    def test_secretary_and_principal_can_create_a_student(self):
        for user in (self.secretary, self.principal):
            with self.subTest(role=user.role):
                self.auth(user)
                payload = dict(STUDENT_PAYLOAD, admissionNumber=f'X-{user.role}')
                resp = self.client.post(self.url('/students/'), payload, format='json')
                self.assertEqual(resp.status_code, 201, resp.content)
        self.assertEqual(Student.objects.filter(school=self.school).count(), 3)


# ── 2. Student create tenant isolation ──────────────────────────────────────

class StudentCreateTenantIsolationTests(SecurityTestBase):
    def test_client_cannot_force_creation_into_another_school(self):
        self.auth(self.admin)
        before = Student.objects.filter(school=self.other_school).count()
        payload = dict(STUDENT_PAYLOAD, schoolId=str(self.other_school.id))
        resp = self.client.post(self.url('/students/'), payload, format='json')
        self.assertIn(resp.status_code, (400, 403), resp.content)
        # No new student may land in the other tenant, and none in this one
        # either: the request is rejected outright, not silently redirected.
        self.assertEqual(Student.objects.filter(school=self.other_school).count(), before)
        self.assertFalse(Student.objects.filter(first_name='Ada').exists())

    def test_school_id_field_is_rejected_even_for_the_caller_own_school(self):
        self.auth(self.admin)
        payload = dict(STUDENT_PAYLOAD, schoolId=str(self.school.id))
        resp = self.client.post(self.url('/students/'), payload, format='json')
        self.assertEqual(resp.status_code, 400)
        self.assertIn('schoolId', resp.json().get('fieldErrors', resp.json()))
        self.assertFalse(Student.objects.filter(first_name='Ada').exists())

    def test_school_admin_cannot_read_another_schools_students(self):
        self.auth(self.admin)
        resp = self.client.get(self.url('/students/'))
        self.assertEqual(resp.status_code, 200)
        admission_numbers = {row['admissionNumber'] for row in resp.json()['results']}
        self.assertNotIn(self.other_student.admission_number, admission_numbers)


# ── 3. Student PATCH authorization ──────────────────────────────────────────

class StudentPatchAuthorizationTests(SecurityTestBase):
    def test_teacher_cannot_modify_a_student(self):
        self.auth(self.teacher)
        resp = self.client.patch(
            self.url(f'/students/{self.student.id}/'), {'firstName': 'Hacked'}, format='json',
        )
        self.assertEqual(resp.status_code, 403)
        self.student.refresh_from_db()
        self.assertEqual(self.student.first_name, 'Amina')

    def test_accountant_cannot_modify_a_student(self):
        self.auth(self.accountant)
        resp = self.client.patch(
            self.url(f'/students/{self.student.id}/'), {'firstName': 'Hacked'}, format='json',
        )
        self.assertEqual(resp.status_code, 403)
        self.student.refresh_from_db()
        self.assertEqual(self.student.first_name, 'Amina')

    def test_authorized_role_can_still_modify_a_student(self):
        self.auth(self.admin)
        resp = self.client.patch(
            self.url(f'/students/{self.student.id}/'), {'guardianPhone': '+234999'}, format='json',
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        self.student.refresh_from_db()
        self.assertEqual(self.student.guardian_phone, '+234999')

    def test_parent_and_student_roles_cannot_modify_a_student(self):
        for user in (self.parent, self.student_user):
            with self.subTest(role=user.role):
                self.auth(user)
                resp = self.client.patch(
                    self.url(f'/students/{self.student.id}/'),
                    {'firstName': 'Hacked'}, format='json',
                )
                self.assertIn(resp.status_code, (403, 404))
        self.student.refresh_from_db()
        self.assertEqual(self.student.first_name, 'Amina')


# ── 4. Student PATCH cross-school isolation ─────────────────────────────────

class StudentPatchCrossSchoolTests(SecurityTestBase):
    def test_school_a_user_cannot_patch_a_school_b_student(self):
        self.auth(self.admin)
        resp = self.client.patch(
            self.url(f'/students/{self.other_student.id}/'),
            {'firstName': 'Hacked'}, format='json',
        )
        self.assertEqual(resp.status_code, 404)
        self.other_student.refresh_from_db()
        self.assertEqual(self.other_student.first_name, 'Chidi')

    def test_school_a_user_cannot_patch_a_school_b_student_by_uuid(self):
        self.auth(self.principal)
        resp = self.client.patch(
            self.url(f'/students/{self.other_student.id}/'),
            {'status': 'suspended'}, format='json',
        )
        self.assertEqual(resp.status_code, 404)
        self.other_student.refresh_from_db()
        self.assertEqual(self.other_student.status, Student.Status.ACTIVE)

    def test_school_b_admin_cannot_patch_a_school_a_student(self):
        self.auth(self.other_admin)
        resp = self.client.patch(
            self.url(f'/students/{self.student.id}/'), {'firstName': 'Hacked'}, format='json',
        )
        self.assertEqual(resp.status_code, 404)
        self.student.refresh_from_db()
        self.assertEqual(self.student.first_name, 'Amina')

    def test_cross_school_read_is_also_blocked(self):
        self.auth(self.admin)
        resp = self.client.get(self.url(f'/students/{self.other_student.id}/'))
        self.assertEqual(resp.status_code, 404)


# ── 5. Student school reassignment ──────────────────────────────────────────

class StudentSchoolReassignmentTests(SecurityTestBase):
    def test_patch_cannot_move_a_student_to_another_school(self):
        self.auth(self.admin)
        resp = self.client.patch(
            self.url(f'/students/{self.student.id}/'),
            {'schoolId': str(self.other_school.id)}, format='json',
        )
        self.assertIn(resp.status_code, (400, 403), resp.content)
        self.student.refresh_from_db()
        self.assertEqual(self.student.school_id, self.school.id)

    def test_patch_cannot_move_a_student_by_another_school_class(self):
        """A crafted `className` pointing at another school's class must not stick."""
        self.auth(self.admin)
        resp = self.client.patch(
            self.url(f'/students/{self.student.id}/'),
            {'className': self.other_jss1.name}, format='json',
        )
        # `className` is a free-text mirror, so the value is accepted as text but
        # must never change the owning school or the active enrollment.
        self.assertIn(resp.status_code, (200, 400), resp.content)
        self.student.refresh_from_db()
        self.assertEqual(self.student.school_id, self.school.id)
        self.assertFalse(Enrollment.objects.filter(
            student=self.student, class_obj=self.other_jss1,
        ).exists())


# ── 6. Attendance roster uses Enrollment ────────────────────────────────────

class AttendanceRosterEnrollmentTests(SecurityTestBase):
    def test_roster_follows_the_enrollment_not_a_stale_class_name(self):
        """The student says 'JSS 1' but is enrolled in JSS 2 - JSS 1 must be empty."""
        enrollment = Enrollment.objects.get(student=self.student, status=Enrollment.Status.ACTIVE)
        enrollment.class_obj = self.jss2
        enrollment.save(update_fields=['class_obj'])
        # The denormalised mirror still (incorrectly) says JSS 1.
        self.student.refresh_from_db()
        self.assertEqual(self.student.class_name, 'JSS 1')

        self.auth(self.teacher)
        wrong = self.roster(className='JSS 1').json()['students']
        right = self.roster(className='JSS 2').json()['students']
        self.assertNotIn('Amina', {row['firstName'] for row in wrong})
        self.assertIn('Amina', {row['firstName'] for row in right})
        self.assertEqual(right[0]['className'], 'JSS 2')

    def test_student_without_an_active_enrollment_is_absent(self):
        self.auth(self.teacher)
        self.assertIn('Amina', {r['firstName'] for r in self.roster(className='JSS 1').json()['students']})
        Enrollment.objects.filter(student=self.student).update(status=Enrollment.Status.SUSPENDED)
        self.assertNotIn(
            'Amina', {r['firstName'] for r in self.roster(className='JSS 1').json()['students']},
        )

    def test_roster_reports_the_enrolled_section_not_the_mirror(self):
        self.auth(self.teacher)
        row = self.roster(className='JSS 1').json()['students'][0]
        self.assertEqual(row['arm'], 'A')

    def test_attendance_submit_only_accepts_enrolled_students(self):
        self.auth(self.teacher)
        resp = self.client.post(
            self.url('/attendance/'),
            {
                'className': 'JSS 1',
                'date': '2026-09-20',
                'records': [{'studentId': str(self.other_student.id), 'status': 'present'}],
            },
            format='json',
        )
        self.assertEqual(resp.status_code, 201, resp.content)
        self.assertEqual(resp.json()['saved'], 0)
        self.assertFalse(AttendanceRecord.objects.filter(
            student=self.other_student,
        ).exists())


# ── 7. Attendance cross-school isolation ────────────────────────────────────

class AttendanceIsolationTests(SecurityTestBase):
    def test_roster_never_returns_another_schools_students(self):
        self.auth(self.teacher)
        rows = self.roster(className='JSS 1').json()['students']
        self.assertNotIn('Chidi', {row['firstName'] for row in rows})

    def test_a_class_belonging_to_another_school_is_not_found(self):
        """Both schools have a class called 'JSS 1'; the filter stays school-scoped."""
        self.assertTrue(SchoolClass.objects.filter(
            school=self.other_school, name='JSS 1',
        ).exists())
        self.auth(self.teacher)
        rows = self.roster(className='JSS 1').json()['students']
        self.assertEqual([row['firstName'] for row in rows], ['Amina'])

    def test_another_schools_student_cannot_be_marked_present(self):
        self.auth(self.teacher)
        self.client.post(
            self.url('/attendance/'),
            {
                'className': 'JSS 1',
                'date': '2026-09-21',
                'records': [{'studentId': str(self.other_student.id), 'status': 'present'}],
            },
            format='json',
        )
        self.assertEqual(
            AttendanceRecord.objects.filter(school=self.school).count(), 0,
        )


# ── 8 & 9. Transfer cross-school source / destination ───────────────────────

class TransferSecurityTests(SecurityTestBase):
    def test_cannot_transfer_another_schools_student(self):
        self.auth(self.admin)
        resp = self.client.post(
            self.url(f'/students/{self.other_student.id}/transfer/'),
            {'toSchoolId': str(self.other_school.id)}, format='json',
        )
        self.assertEqual(resp.status_code, 404)
        self.other_student.refresh_from_db()
        self.assertEqual(self.other_student.status, Student.Status.ACTIVE)

    def test_cannot_move_a_student_into_another_schools_class(self):
        self.auth(self.admin)
        resp = self.client.post(
            self.url(f'/students/{self.student.id}/transfer/'),
            {'toClassId': str(self.other_jss1.pk)}, format='json',
        )
        self.assertEqual(resp.status_code, 404)
        self.assertFalse(Enrollment.objects.filter(
            student=self.student, class_obj=self.other_jss1,
        ).exists())

    def test_cannot_move_a_student_into_another_schools_section(self):
        self.auth(self.admin)
        resp = self.client.post(
            self.url(f'/students/{self.student.id}/transfer/'),
            {'toClassId': str(self.jss1.pk), 'toSectionId': str(self.other_section.pk)},
            format='json',
        )
        self.assertEqual(resp.status_code, 404)
        enrollment = Enrollment.objects.get(student=self.student, status=Enrollment.Status.ACTIVE)
        self.assertNotEqual(enrollment.section_id, self.other_section.pk)

    def test_cannot_move_a_student_into_another_schools_session(self):
        self.auth(self.admin)
        resp = self.client.post(
            self.url(f'/students/{self.student.id}/transfer/'),
            {'toClassId': str(self.jss1.pk), 'sessionId': str(self.other_session.pk)},
            format='json',
        )
        self.assertEqual(resp.status_code, 404)

    def test_teacher_cannot_transfer_a_student(self):
        self.auth(self.teacher)
        resp = self.client.post(
            self.url(f'/students/{self.student.id}/transfer/'),
            {'toClassId': str(self.jss2.pk)}, format='json',
        )
        self.assertEqual(resp.status_code, 403)


# ── 10. Valid same-school transfers still work ──────────────────────────────

class TransferHappyPathTests(SecurityTestBase):
    def test_school_to_school_transfer_still_works(self):
        self.auth(self.admin)
        resp = self.client.post(
            self.url(f'/students/{self.student.id}/transfer/'),
            {'toSchoolId': str(self.other_school.id)}, format='json',
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        self.student.refresh_from_db()
        self.assertEqual(self.student.status, Student.Status.TRANSFERRED)
        self.assertEqual(self.student.transferred_to_id, self.other_school.id)

    def test_cannot_transfer_to_own_school(self):
        self.auth(self.admin)
        resp = self.client.post(
            self.url(f'/students/{self.student.id}/transfer/'),
            {'toSchoolId': str(self.school.id)}, format='json',
        )
        self.assertEqual(resp.status_code, 400)

    def test_cannot_transfer_to_an_inactive_school(self):
        inactive = School.objects.create(
            name='Closed School', slug='closed-school', code='CLS',
            address='x', state='Kano', lga='Kano', phone='1',
            email='closed@example.com', is_active=False,
        )
        self.auth(self.admin)
        resp = self.client.post(
            self.url(f'/students/{self.student.id}/transfer/'),
            {'toSchoolId': str(inactive.id)}, format='json',
        )
        self.assertEqual(resp.status_code, 404)

    def test_missing_destination_is_a_validation_error(self):
        self.auth(self.admin)
        resp = self.client.post(
            self.url(f'/students/{self.student.id}/transfer/'), {}, format='json',
        )
        self.assertEqual(resp.status_code, 400)

    def test_valid_within_school_class_transfer_still_works(self):
        self.auth(self.admin)
        resp = self.client.post(
            self.url(f'/students/{self.student.id}/transfer/'),
            {'toClassId': str(self.jss2.pk)}, format='json',
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        enrollment = Enrollment.objects.get(
            student=self.student, status=Enrollment.Status.ACTIVE,
        )
        self.assertEqual(enrollment.class_obj_id, self.jss2.pk)
        # The denormalised mirror follows the enrollment.
        self.student.refresh_from_db()
        self.assertEqual(self.student.class_name, 'JSS 2')

    def test_valid_within_school_section_transfer_still_works(self):
        section_b = Section.objects.create(
            school=self.school, class_obj=self.jss1, name='B',
        )
        self.auth(self.admin)
        resp = self.client.post(
            self.url(f'/students/{self.student.id}/transfer/'),
            {'toSectionId': str(section_b.pk)}, format='json',
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        enrollment = Enrollment.objects.get(
            student=self.student, status=Enrollment.Status.ACTIVE,
        )
        self.assertEqual(enrollment.section_id, section_b.pk)
        self.student.refresh_from_db()
        self.assertEqual(self.student.arm, 'B')
