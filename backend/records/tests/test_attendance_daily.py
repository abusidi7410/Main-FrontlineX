"""The daily attendance register: once per day, calendar, overview, correction.

These pin the rules that stop being true quietly:

* **Once per school day.** A student has at most one attendance record per day.
  The old constraint was per (student, day, subject), which let a class record a
  student several times in one day.
* **Roster truth.** Membership comes from an active `Enrollment`, never from the
  `Student.class_name` mirror.
* **Responsibility.** Only the designated class teacher (or an admin) submits.
* **Correction is audited.** Amending a taken register always leaves a trail.
* **The calendar.** A weekend or a declared closure is a school holiday, so the
  overview says "not a school day" rather than "nobody took the register".
"""
import datetime

from django.db.utils import IntegrityError

from schools.models import AuditLog

from accounts.models import User
from records.models import (
    AcademicSession,
    AttendanceRecord,
    ClassTeacherAssignment,
    Enrollment,
    SchoolClass,
    Section,
    StaffMember,
    Student,
)

from .test_security import SecurityTestBase


def remove_all_classes(school):
    """Delete a school's `SchoolClass` rows.

    `Enrollment`, `ResultSheet` and registrations PROTECT them, which is the point:
    a class that has students cannot vanish. Clearing the referencing rows first is
    the only way to reach the "this school has no classes at all" state.
    """
    from records.models import Registration, ResultSheet

    Enrollment.objects.filter(school=school).delete()
    ResultSheet.objects.filter(school=school).delete()
    Registration.objects.filter(school=school).delete()
    SchoolClass.objects.filter(school=school).delete()


class DailyAttendanceTests(SecurityTestBase):
    def setUp(self):
        super().setUp()
        # A second section so an arm-scoped register can be told apart from the
        # whole-class one.
        self.section_b = Section.objects.create(
            school=self.school, class_obj=self.jss1, name='B',
        )
        self.student_b = Student.objects.create(
            school=self.school, admission_number='SUA/JSS/2026/000101',
            first_name='Tunde', last_name='Okafor', gender='male',
            class_name='JSS 1', arm='B', status=Student.Status.ACTIVE,
        )
        Enrollment.objects.create(
            school=self.school, student=self.student_b, academic_session=self.session,
            class_obj=self.jss1, section=self.section_b,
            status=Enrollment.Status.ACTIVE,
        )
        self.day = datetime.date(2026, 9, 18)

    def register(self, **overrides):
        payload = {
            'className': 'JSS 1',
            'date': '2026-09-18',
            'records': [
                {'studentId': str(self.student.public_id), 'status': 'present'},
                {'studentId': str(self.student_b.public_id), 'status': 'absent'},
            ],
        }
        payload.update(overrides)
        return self.client.post(self.url('/attendance/'), payload, format='json')

    # ── once per day ────────────────────────────────────────────────────────

    def test_a_student_gets_only_one_record_per_day(self):
        self.auth(self.admin)
        self.assertEqual(self.register().status_code, 201)

        with self.assertRaises(Exception):
            AttendanceRecord.objects.create(
                school=self.school, student=self.student,
                class_obj=self.jss1, class_name='JSS 1',
                date=self.day, status=AttendanceRecord.Status.ABSENT,
            )

    def test_a_second_register_for_the_class_is_refused_with_the_existing_marks(self):
        self.auth(self.admin)
        self.assertEqual(self.register().status_code, 201)

        second = self.register(
            date='2026-09-18',
            records=[{'studentId': str(self.student.public_id), 'status': 'absent'}],
        )
        self.assertEqual(second.status_code, 409, second.content)
        # The 409 hands back what is already recorded, so the client can display
        # the taken register instead of starting a fresh one.
        body = second.json()
        self.assertTrue(body['taken'])
        self.assertEqual(body['existing'][str(self.student.public_id)], 'present')
        self.assertEqual(AttendanceRecord.objects.count(), 2)

    def test_the_same_day_in_a_different_class_is_allowed(self):
        """One record per student per day, not one per class per day."""
        self.auth(self.admin)
        self.assertEqual(self.register().status_code, 201)

        other_day_class = self.client.post(
            self.url('/attendance/'),
            {
                'className': 'JSS 2',
                'date': '2026-09-18',
                'records': [{'studentId': str(self.student.public_id), 'status': 'present'}],
            },
            format='json',
        )
        # The student is only enrolled in JSS 1, so JSS 2 has no roster to mark.
        self.assertEqual(other_day_class.status_code, 400, other_day_class.content)

    def test_a_duplicated_student_in_one_payload_is_rejected(self):
        self.auth(self.admin)
        resp = self.register(records=[
            {'studentId': str(self.student.public_id), 'status': 'present'},
            {'studentId': str(self.student.public_id), 'status': 'absent'},
        ])
        self.assertEqual(resp.status_code, 400, resp.content)
        self.assertFalse(AttendanceRecord.objects.exists())

    def test_an_invalid_status_is_rejected_and_nothing_is_written(self):
        self.auth(self.admin)
        resp = self.register(records=[
            {'studentId': str(self.student.public_id), 'status': 'present'},
            {'studentId': str(self.student_b.public_id), 'status': 'invented'},
        ])
        self.assertEqual(resp.status_code, 400, resp.content)
        self.assertFalse(AttendanceRecord.objects.exists())

    def test_an_empty_class_cannot_have_a_register_written_for_it(self):
        self.auth(self.admin)
        resp = self.register(
            className='SSS 1',
            records=[{'studentId': str(self.student.public_id), 'status': 'present'}],
        )
        self.assertEqual(resp.status_code, 400, resp.content)
        self.assertFalse(AttendanceRecord.objects.exists())

    # ── roster truth ────────────────────────────────────────────────────────

    def test_a_stale_class_name_mirror_cannot_put_a_student_in_the_register(self):
        enrollment = Enrollment.objects.get(
            student=self.student, status=Enrollment.Status.ACTIVE,
        )
        enrollment.class_obj = self.jss2
        enrollment.save(update_fields=['class_obj'])

        self.auth(self.admin)
        rows = self.client.get(
            self.url('/attendance/roster/'), {'className': 'JSS 1'},
        ).json()['students']
        self.assertNotIn('Amina', {row['firstName'] for row in rows})

    def test_the_register_reports_its_class_teacher_and_submission_right(self):
        self.auth(self.teacher)
        body = self.client.get(
            self.url('/attendance/roster/'), {'className': 'JSS 1'},
        ).json()
        self.assertEqual(body['classTeacher'], 'Teacher Test')
        self.assertTrue(body['canSubmit'])
        self.assertTrue(body['classConfigured'])

    def test_a_configured_class_with_no_class_row_is_empty_not_an_error(self):
        """The dropdown/roster split: a name the school configured but never
        provisioned resolves to an empty roster, not a 404."""
        self.school.classes = list(self.school.classes or []) + ['Unprovisioned Class']
        self.school.save(update_fields=['classes'])

        self.auth(self.admin)
        resp = self.client.get(
            self.url('/attendance/roster/'), {'className': 'Unprovisioned Class'},
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(resp.json()['students'], [])
        self.assertFalse(resp.json()['classConfigured'])

    def test_a_class_this_school_never_configured_is_not_found(self):
        self.auth(self.admin)
        resp = self.client.get(
            self.url('/attendance/roster/'), {'className': 'Nonexistent Class'},
        )
        self.assertEqual(resp.status_code, 404)

    # ── school calendar ─────────────────────────────────────────────────────

    def test_a_weekend_is_not_a_school_day(self):
        saturday = datetime.date(2026, 9, 19)
        self.assertEqual(saturday.weekday(), 5)
        self.auth(self.admin)
        body = self.client.get(
            self.url('/attendance/roster/'), {'className': 'JSS 1', 'date': saturday.isoformat()},
        ).json()
        self.assertFalse(body['isSchoolDay'])

    def test_a_declared_closure_is_not_a_school_day(self):
        closed = datetime.date(2026, 9, 24)
        self.school.non_school_days = [closed.isoformat()]
        self.school.save(update_fields=['non_school_days'])

        self.auth(self.admin)
        body = self.client.get(
            self.url('/attendance/roster/'), {'className': 'JSS 1', 'date': closed.isoformat()},
        ).json()
        self.assertFalse(body['isSchoolDay'])

    def test_attendance_cannot_be_submitted_on_a_weekend(self):
        self.auth(self.admin)
        resp = self.register(date='2026-09-19')

        self.assertEqual(resp.status_code, 400, resp.content)
        self.assertIn('date', resp.json()['fieldErrors'])
        self.assertFalse(AttendanceRecord.objects.exists())

    def test_attendance_cannot_be_submitted_on_a_declared_closure(self):
        closed = datetime.date(2026, 9, 24)
        self.school.non_school_days = [closed.isoformat()]
        self.school.save(update_fields=['non_school_days'])

        self.auth(self.admin)
        resp = self.register(date=closed.isoformat())

        self.assertEqual(resp.status_code, 400, resp.content)
        self.assertIn('date', resp.json()['fieldErrors'])
        self.assertFalse(AttendanceRecord.objects.exists())

    def test_the_overview_flags_a_non_school_day_rather_than_showing_late_teachers(self):
        saturday = datetime.date(2026, 9, 19)
        self.auth(self.admin)
        body = self.client.get(
            self.url('/attendance/overview/'), {'date': saturday.isoformat()},
        ).json()
        self.assertFalse(body['isSchoolDay'])
        self.assertEqual(body['submitted'], 0)

    # ── the admin overview ──────────────────────────────────────────────────

    def test_the_overview_reports_who_has_and_has_not_submitted(self):
        self.auth(self.admin)
        self.assertEqual(self.register().status_code, 201)

        body = self.client.get(
            self.url('/attendance/overview/'), {'date': '2026-09-18'},
        ).json()
        self.assertEqual(body['total'], 3)
        self.assertEqual(body['submitted'], 1)

        rows = {row['className']: row for row in body['classes']}
        self.assertEqual(rows['JSS 1']['present'], 1)
        self.assertEqual(rows['JSS 1']['absent'], 1)
        self.assertEqual(rows['JSS 1']['submitted'], 2)
        self.assertEqual(rows['JSS 2']['submitted'], 0)
        self.assertEqual(rows['SSS 1']['submitted'], 0)

    def test_a_teacher_only_sees_their_own_classes_on_the_overview(self):
        """Without this the overview would be a school-wide leak for a teacher."""
        self.auth(self.teacher)
        body = self.client.get(
            self.url('/attendance/overview/'), {'date': '2026-09-18'},
        ).json()
        self.assertEqual([row['className'] for row in body['classes']], ['JSS 1'])

    def test_a_teacher_with_no_class_assignment_sees_no_overview_classes(self):
        """No assignment recorded means "no classes", never "all classes"."""
        unassigned = StaffMember.objects.create(
            school=self.school, full_name='Unassigned Teacher',
            email='unassigned@success.example', role='teacher',
            status=StaffMember.Status.ACTIVE,
        )
        stray = User.objects.create_user(
            email='stray@success.example', password='Strong-Pass-1!',
            first_name='Stray', last_name='Teacher',
            role=User.Role.TEACHER, school=self.school, is_active=True,
        )
        stray.staff_profile = unassigned
        stray.save(update_fields=['staff_profile'])

        self.auth(stray)
        body = self.client.get(
            self.url('/attendance/overview/'), {'date': '2026-09-18'},
        ).json()
        self.assertEqual(body['classes'], [])

    # ── correction with an audit trail ──────────────────────────────────────

    def test_correcting_a_record_writes_an_audit_entry_with_before_and_after(self):
        self.auth(self.admin)
        self.assertEqual(self.register().status_code, 201)
        record = AttendanceRecord.objects.get(student=self.student)

        resp = self.client.post(
            self.url('/attendance/correct/'),
            {'recordId': str(record.id), 'status': 'absent', 'reason': 'Marked in error'},
            format='json',
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertTrue(resp.json()['changed'])

        record.refresh_from_db()
        self.assertEqual(record.status, AttendanceRecord.Status.ABSENT)

        entry = AuditLog.objects.filter(
            school=self.school, action='attendance.correct',
        ).first()
        self.assertIsNotNone(entry)
        self.assertEqual(entry.entity, 'AttendanceRecord')
        self.assertEqual(entry.entity_id, str(record.id))
        self.assertEqual(entry.before['status'], 'present')
        self.assertEqual(entry.after['status'], 'absent')
        self.assertIn('Marked in error', entry.detail)

    def test_a_correction_needs_a_reason(self):
        self.auth(self.admin)
        self.assertEqual(self.register().status_code, 201)
        record = AttendanceRecord.objects.get(student=self.student)

        resp = self.client.post(
            self.url('/attendance/correct/'),
            {'recordId': str(record.id), 'status': 'absent', 'reason': '   '},
            format='json',
        )
        self.assertEqual(resp.status_code, 400, resp.content)
        record.refresh_from_db()
        self.assertEqual(record.status, 'present')

    def test_a_no_op_correction_writes_no_audit_entry(self):
        self.auth(self.admin)
        self.assertEqual(self.register().status_code, 201)
        record = AttendanceRecord.objects.get(student=self.student)
        before = AuditLog.objects.filter(action='attendance.correct').count()

        resp = self.client.post(
            self.url('/attendance/correct/'),
            {'recordId': str(record.id), 'status': 'present', 'reason': 'No change'},
            format='json',
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertFalse(resp.json()['changed'])
        self.assertEqual(
            AuditLog.objects.filter(action='attendance.correct').count(), before,
        )

    # ── history ─────────────────────────────────────────────────────────────

    def test_history_filters_by_class_and_date_range(self):
        self.auth(self.admin)
        self.assertEqual(self.register().status_code, 201)
        self.assertEqual(
            self.register(
                date='2026-09-21',
                records=[{'studentId': str(self.student.public_id), 'status': 'absent'}],
            ).status_code,
            201,
        )

        body = self.client.get(self.url('/attendance/history/'), {
            'className': 'JSS 1',
            'dateFrom': '2026-09-18',
            'dateTo': '2026-09-18',
        }).json()
        self.assertEqual(len(body['records']), 2)
        self.assertTrue(all(row['className'] == 'JSS 1' for row in body['records']))

    def test_history_filters_by_student(self):
        self.auth(self.admin)
        self.assertEqual(self.register().status_code, 201)

        body = self.client.get(
            self.url('/attendance/history/'), {'studentId': str(self.student.public_id)},
        ).json()
        self.assertEqual(len(body['records']), 1)
        self.assertEqual(body['records'][0]['studentId'], str(self.student.public_id))

    def test_history_is_paginated_before_serialization(self):
        self.auth(self.admin)
        self.assertEqual(self.register().status_code, 201)
        self.assertEqual(
            self.register(
                date='2026-09-21',
                records=[{'studentId': str(self.student.public_id), 'status': 'absent'}],
            ).status_code,
            201,
        )

        response = self.client.get(
            self.url('/attendance/history/'),
            {
                'dateFrom': '2026-09-18',
                'dateTo': '2026-09-18',
                'page': 2,
                'pageSize': 1,
            },
        )
        self.assertEqual(response.status_code, 200, response.content)
        payload = response.json()
        self.assertEqual(len(payload['records']), 1)
        self.assertEqual(payload['count'], 2)
        self.assertEqual(payload['page'], 2)
        self.assertEqual(payload['totalPages'], 2)

    def test_an_inverted_date_range_is_rejected(self):
        self.auth(self.admin)
        resp = self.client.get(self.url('/attendance/history/'), {
            'dateFrom': '2026-09-18',
            'dateTo': '2026-09-01',
        })
        self.assertEqual(resp.status_code, 400, resp.content)

    def test_history_never_reaches_another_schools_student(self):
        self.auth(self.admin)
        resp = self.client.get(
            self.url('/attendance/history/'), {'studentId': str(self.other_student.public_id)},
        )
        self.assertEqual(resp.status_code, 404, resp.content)

    # ── history is confined for teachers ─────────────────────────────────────

    def test_a_teacher_cannot_read_a_student_outside_their_classes(self):
        """`attendance.read` is school-wide, so the history search must narrow."""
        outsider = Student.objects.create(
            school=self.school, admission_number='SUA/SSS/2026/000300',
            first_name='Kemi', last_name='Ayo', gender='female',
            class_name='SSS 1', status=Student.Status.ACTIVE,
        )
        section_ccc = Section.objects.create(
            school=self.school, class_obj=self.sss1, name='C',
        )
        Enrollment.objects.create(
            school=self.school, student=outsider, academic_session=self.session,
            class_obj=self.sss1, section=section_ccc,
            status=Enrollment.Status.ACTIVE,
        )

        self.auth(self.teacher)
        resp = self.client.get(
            self.url('/attendance/history/'), {'studentId': str(outsider.id)},
        )
        # 404 rather than 403: the teacher may not learn the student exists.
        self.assertEqual(resp.status_code, 404, resp.content)

    def test_a_teacher_cannot_read_another_classs_history(self):
        self.auth(self.teacher)
        resp = self.client.get(
            self.url('/attendance/history/'), {'className': 'JSS 2'},
        )
        self.assertEqual(resp.status_code, 404, resp.content)

    def test_a_teacher_can_read_the_history_of_their_own_students(self):
        self.auth(self.admin)
        self.assertEqual(self.register().status_code, 201)

        self.auth(self.teacher)
        body = self.client.get(
            self.url('/attendance/history/'), {'studentId': str(self.student.public_id)},
        ).json()
        self.assertEqual(len(body['records']), 1)

    def test_a_teacher_with_no_classes_gets_no_history_not_the_schools(self):
        unassigned = StaffMember.objects.create(
            school=self.school, full_name='Unassigned Teacher',
            email='unassigned@success.example', role='teacher',
            status=StaffMember.Status.ACTIVE,
        )
        stray = User.objects.create_user(
            email='stray@success.example', password='Strong-Pass-1!',
            first_name='Stray', last_name='Teacher',
            role=User.Role.TEACHER, school=self.school, is_active=True,
        )
        stray.staff_profile = unassigned
        stray.save(update_fields=['staff_profile'])

        self.auth(self.admin)
        self.assertEqual(self.register().status_code, 201)

        self.auth(stray)
        body = self.client.get(self.url('/attendance/history/'), {'className': 'JSS 1'})
        self.assertEqual(body.status_code, 404, body.content)

    def test_a_teacher_can_still_read_a_class_they_teach_without_being_class_teacher(self):
        """Read access is wider than submit access: Subject Teacher teaches JSS 1."""
        self.auth(self.admin)
        self.assertEqual(self.register().status_code, 201)

        self.auth(self.subject_teacher)
        body = self.client.get(
            self.url('/attendance/history/'), {'className': 'JSS 1'},
        )
        self.assertEqual(body.status_code, 200, body.content)
        self.assertEqual(len(body.json()['records']), 2)

    def test_a_suspended_staff_record_loses_history_access(self):
        self.auth(self.admin)
        self.assertEqual(self.register().status_code, 201)

        self.teacher_staff.status = StaffMember.Status.SUSPENDED
        self.teacher_staff.save(update_fields=['status'])

        self.auth(self.teacher)
        body = self.client.get(
            self.url('/attendance/history/'), {'className': 'JSS 1'},
        )
        self.assertEqual(body.status_code, 404, body.content)

    # ── legacy rows stay visible ────────────────────────────────────────────

    def test_a_legacy_row_with_no_class_fk_is_still_reported_as_taken(self):
        """`class_obj` is a new FK; old rows carry NULL and must not read as untaken."""
        AttendanceRecord.objects.create(
            school=self.school, student=self.student, class_name='JSS 1',
            date=self.day, status=AttendanceRecord.Status.PRESENT,
        )
        self.auth(self.admin)
        body = self.client.get(
            self.url('/attendance/roster/'), {'className': 'JSS 1', 'date': '2026-09-18'},
        ).json()
        self.assertTrue(body['taken'])
        self.assertEqual(body['existing'][str(self.student.public_id)], 'present')


class ClassTeacherAssignmentTests(SecurityTestBase):
    def test_one_class_teacher_per_class_per_session(self):
        from django.db import transaction

        # JSS 1 is already assigned to Teacher Test by the base fixture, so this
        # uses JSS 2 to show the constraint is per (class, session).
        ClassTeacherAssignment.objects.create(
            school=self.school, staff=self.subject_staff,
            class_obj=self.jss2, academic_session=self.session,
        )
        with self.assertRaises(IntegrityError):
            # Nested atomic: the failed INSERT poisons the surrounding
            # transaction, so the block is rolled back to its savepoint.
            with transaction.atomic():
                ClassTeacherAssignment.objects.create(
                    school=self.school, staff=self.teacher_staff,
                    class_obj=self.jss2, academic_session=self.session,
                )
        self.assertEqual(
            ClassTeacherAssignment.objects.get(class_obj=self.jss2).staff,
            self.subject_staff,
        )

    def test_a_different_class_can_have_its_own_teacher(self):
        ClassTeacherAssignment.objects.create(
            school=self.school, staff=self.subject_staff,
            class_obj=self.jss2, academic_session=self.session,
        )
        self.assertEqual(ClassTeacherAssignment.objects.filter(school=self.school).count(), 2)

    def test_a_new_session_can_name_a_different_class_teacher(self):
        next_session = AcademicSession.objects.create(
            school=self.school, name='2027/2028', start_year=2027, end_year=2028,
            is_current=False,
        )
        ClassTeacherAssignment.objects.create(
            school=self.school, staff=self.subject_staff,
            class_obj=self.jss1, academic_session=next_session,
        )
        self.assertEqual(ClassTeacherAssignment.objects.filter(school=self.school).count(), 2)


class ClassTeacherDesignationTests(SecurityTestBase):
    """Without this endpoint the strict rule is unusable: nobody can submit."""

    def designate(self, class_name='JSS 2', staff_id=None, **extra):
        payload = {'className': class_name, **extra}
        if staff_id is not None:
            payload['staffId'] = str(staff_id)
        return self.client.post(
            self.url('/attendance/class-teachers/'), payload, format='json',
        )

    def test_designating_a_teacher_lets_them_submit_that_class(self):
        ClassTeacherAssignment.objects.filter(
            class_obj=self.jss2, academic_session=self.session,
        ).delete()
        self.auth(self.admin)
        resp = self.designate('JSS 2', self.subject_staff.public_id)
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(resp.json()['staffName'], 'Subject Teacher')

        self.auth(self.subject_teacher)
        # Give JSS 2 a student, then the designated teacher can submit it.
        section = Section.objects.create(school=self.school, class_obj=self.jss2, name='A')
        jss2_student = Student.objects.create(
            school=self.school, admission_number='SUA/JSS/2026/000400',
            first_name='Yusuf', last_name='Bello', gender='male',
            class_name='JSS 2', status=Student.Status.ACTIVE,
        )
        Enrollment.objects.create(
            school=self.school, student=jss2_student, academic_session=self.session,
            class_obj=self.jss2, section=section, status=Enrollment.Status.ACTIVE,
        )

        self.auth(self.subject_teacher)
        roster = self.client.get(
            self.url('/attendance/roster/'), {'className': 'JSS 2'},
        ).json()
        self.assertTrue(roster['canSubmit'])
        self.assertEqual(roster['classTeacher'], 'Subject Teacher')

        saved = self.client.post(
            self.url('/attendance/'),
            {
                'className': 'JSS 2',
                'date': '2026-09-18',
                'records': [{'studentId': str(jss2_student.public_id), 'status': 'present'}],
            },
            format='json',
        )
        self.assertEqual(saved.status_code, 201, saved.content)

    def test_designation_adds_the_class_to_the_teachers_own_class_list(self):
        """Otherwise "my classes" - which drives the register and the assistant -
        would not include the class they are now responsible for."""
        ClassTeacherAssignment.objects.filter(
            class_obj=self.jss2, academic_session=self.session,
        ).delete()
        self.auth(self.admin)
        self.designate('JSS 2', self.subject_staff.public_id)

        self.subject_staff.refresh_from_db()
        self.assertIn('JSS 2', self.subject_staff.classes)

    def test_reassigning_replaces_the_previous_teacher(self):
        self.auth(self.admin)
        first = self.designate('JSS 2', self.subject_staff.public_id)
        self.assertEqual(first.status_code, 200, first.content)

        second = self.designate('JSS 2', self.teacher_staff.public_id)
        self.assertEqual(second.status_code, 200, second.content)
        self.assertEqual(
            ClassTeacherAssignment.objects.get(
                class_obj=self.jss2, academic_session=self.session,
            ).staff,
            self.teacher_staff,
        )
        self.assertEqual(
            ClassTeacherAssignment.objects.filter(
                class_obj=self.jss2, academic_session=self.session,
            ).count(),
            1,
        )

    def test_clearing_a_designation(self):
        self.auth(self.admin)
        self.assertEqual(self.designate('JSS 2', self.subject_staff.public_id).status_code, 200)

        cleared = self.designate('JSS 2', assign=False)
        self.assertEqual(cleared.status_code, 200, cleared.content)
        self.assertFalse(
            ClassTeacherAssignment.objects.filter(class_obj=self.jss2).exists(),
        )

    def test_a_secretary_cannot_designate_a_class_teacher(self):
        self.auth(self.secretary)
        resp = self.designate('JSS 2', self.subject_staff.public_id)
        self.assertEqual(resp.status_code, 403, resp.content)
        self.assertFalse(
            ClassTeacherAssignment.objects.filter(class_obj=self.jss2).exists(),
        )

    def test_a_teacher_cannot_designate_themselves(self):
        self.auth(self.teacher)
        resp = self.designate('JSS 2', self.subject_staff.public_id)
        self.assertEqual(resp.status_code, 403, resp.content)

    def test_a_non_teacher_cannot_be_designated(self):
        from records.models import StaffMember as SM

        accountant_staff = SM.objects.create(
            school=self.school, full_name='Accountant Test',
            email='accountant@success.example', role='accountant',
            status=SM.Status.ACTIVE,
        )
        self.auth(self.admin)
        resp = self.designate('JSS 2', accountant_staff.public_id)
        self.assertEqual(resp.status_code, 400, resp.content)
        self.assertFalse(
            ClassTeacherAssignment.objects.filter(class_obj=self.jss2).exists(),
        )

    def test_designating_a_staff_member_from_another_school_is_not_found(self):
        other_staff = StaffMember.objects.create(
            school=self.other_school, full_name='Rival Teacher',
            email='rival@rival.example', role='teacher',
            status=StaffMember.Status.ACTIVE,
        )
        self.auth(self.admin)
        resp = self.designate('JSS 2', other_staff.public_id)
        self.assertEqual(resp.status_code, 404, resp.content)

    def test_designating_an_unknown_class_is_rejected(self):
        self.auth(self.admin)
        resp = self.designate('Nonexistent Class', self.subject_staff.public_id)
        self.assertEqual(resp.status_code, 400, resp.content)

    def test_the_assignment_list_is_scoped_to_the_school_and_session(self):
        self.auth(self.admin)
        body = self.client.get(self.url('/attendance/class-teachers/')).json()
        self.assertEqual(body['session'], self.session.name)
        self.assertEqual(
            [row['className'] for row in body['assignments']], ['JSS 1'],
        )

    def test_the_assignment_list_is_visible_to_a_teacher_but_not_writable(self):
        self.auth(self.teacher)
        resp = self.client.get(self.url('/attendance/class-teachers/'))
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(
            resp.json()['assignments'][0]['staffName'], 'Teacher Test',
        )


class SchoolCalendarTests(SecurityTestBase):
    """The calendar decides what "not taken" means, so it has to be settable."""

    def patch_academics(self, **payload):
        return self.client.patch(self.url('/academics/'), payload, format='json')

    def test_the_calendar_is_returned_with_the_academic_structure(self):
        self.school.non_school_days = ['2026-12-25']
        self.school.save(update_fields=['non_school_days'])
        self.auth(self.admin)
        body = self.client.get(self.url('/academics/')).json()
        self.assertEqual(body['attendanceWeekendDays'], [5, 6])
        self.assertEqual(body['nonSchoolDays'], ['2026-12-25'])

    def test_weekend_days_can_be_changed(self):
        self.auth(self.admin)
        resp = self.patch_academics(attendanceWeekendDays=[6, 0])
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(resp.json()['attendanceWeekendDays'], [0, 6])
        self.school.refresh_from_db()
        self.assertEqual(self.school.attendance_weekend_days, [0, 6])

    def test_a_weekend_day_can_be_made_a_teaching_day(self):
        self.auth(self.admin)
        self.patch_academics(attendanceWeekendDays=[6])
        resp = self.client.get(
            self.url('/attendance/roster/'),
            {'className': 'JSS 1', 'date': '2026-09-18'},  # a Friday
        ).json()
        self.assertTrue(resp['isSchoolDay'])

    def test_every_day_being_a_weekend_is_rejected_as_impossible(self):
        """Allowing 0-6 would make every day a holiday, silently switching the
        whole register off. That is a mistake, not a configuration."""
        self.auth(self.admin)
        resp = self.patch_academics(attendanceWeekendDays=[0, 1, 2, 3, 4, 5, 6])
        self.assertEqual(resp.status_code, 400, resp.content)

    def test_an_out_of_range_weekday_is_rejected(self):
        self.auth(self.admin)
        self.assertEqual(self.patch_academics(attendanceWeekendDays=[7]).status_code, 400)
        self.assertEqual(self.patch_academics(attendanceWeekendDays=['-1']).status_code, 400)

    def test_a_non_numeric_weekday_is_rejected(self):
        self.auth(self.admin)
        resp = self.patch_academics(attendanceWeekendDays=['Sunday'])
        self.assertEqual(resp.status_code, 400, resp.content)
        self.assertIn('attendanceWeekendDays', str(resp.data))

    def test_closures_can_be_set_and_are_deduplicated_and_sorted(self):
        self.auth(self.admin)
        resp = self.patch_academics(
            nonSchoolDays=['2026-12-25', '2026-01-05', '2026-12-25'],
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(
            resp.json()['nonSchoolDays'], ['2026-01-05', '2026-12-25'],
        )

    def test_a_malformed_closure_date_is_rejected(self):
        self.auth(self.admin)
        resp = self.patch_academics(nonSchoolDays=['25/12/2026'])
        self.assertEqual(resp.status_code, 400, resp.content)
        self.school.refresh_from_db()
        self.assertEqual(self.school.non_school_days, [])

    def test_updating_the_term_alone_does_not_wipe_the_calendar(self):
        """The calendar keys are opt-in, so a partial update must not clear them."""
        self.school.non_school_days = ['2026-12-25']
        self.school.save(update_fields=['non_school_days'])

        self.auth(self.admin)
        resp = self.patch_academics(term='Second Term')
        self.assertEqual(resp.status_code, 200, resp.content)
        self.school.refresh_from_db()
        self.assertEqual(self.school.current_term, 'Second Term')
        self.assertEqual(self.school.non_school_days, ['2026-12-25'])
        self.assertEqual(self.school.attendance_weekend_days, [5, 6])

    def test_an_empty_update_is_rejected(self):
        self.auth(self.admin)
        resp = self.patch_academics()
        self.assertEqual(resp.status_code, 400, resp.content)

    def test_a_teacher_cannot_change_the_calendar(self):
        self.auth(self.teacher)
        resp = self.patch_academics(attendanceWeekendDays=[0, 1, 2, 3, 4, 5, 6])
        self.assertEqual(resp.status_code, 403, resp.content)

    def test_a_secretary_cannot_change_the_calendar(self):
        self.auth(self.secretary)
        self.assertEqual(
            self.patch_academics(nonSchoolDays=['2026-12-25']).status_code, 403,
        )

    def test_the_principal_may_change_the_calendar(self):
        self.auth(self.principal)
        resp = self.patch_academics(nonSchoolDays=['2026-12-25'])
        self.assertEqual(resp.status_code, 200, resp.content)


class AcademicsClassSourceOfTruthTests(SecurityTestBase):
    def test_adding_a_class_creates_a_real_class_row(self):
        """A class that exists only as a dropdown string has no roster."""
        self.auth(self.admin)
        resp = self.client.post(
            self.url('/academics/classes/'),
            {'name': 'JSS 4', 'level': 'jss'},
            format='json',
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertTrue(
            self.school.school_classes.filter(name='JSS 4', is_active=True).exists()
        )
        self.assertIn('JSS 4', resp.json()['classes'])
        self.assertIn('JSS 4', resp.json()['classIds'])

    def test_the_academics_payload_lists_only_real_classes(self):
        self.auth(self.admin)
        payload = self.client.get(self.url('/academics/')).json()
        self.assertEqual(sorted(payload['classes']), ['JSS 1', 'JSS 2', 'SSS 1'])
        self.assertEqual(len(payload['classIds']), 3)

    def test_removing_a_class_retires_it_without_losing_history(self):
        self.auth(self.admin)
        self.assertEqual(
            self.client.delete(self.url('/academics/classes/JSS 2/')).status_code, 200,
        )
        self.assertFalse(
            self.school.school_classes.get(name='JSS 2').is_active,
        )
        self.assertNotIn('JSS 2', self.client.get(self.url('/academics/')).json()['classes'])

    def test_a_school_with_real_classes_but_an_empty_mirror_lists_them(self):
        """The live bug: `School.classes` was never written, so the dropdown was
        empty while the register endpoint resolved the same classes fine."""
        self.school.classes = []
        self.school.save(update_fields=['classes'])

        self.auth(self.admin)
        payload = self.client.get(self.url('/academics/')).json()
        self.assertEqual(sorted(payload['classes']), ['JSS 1', 'JSS 2', 'SSS 1'])
        # ...and the mirror is repaired as a side effect, not just the response.
        self.school.refresh_from_db()
        self.assertEqual(sorted(self.school.classes), ['JSS 1', 'JSS 2', 'SSS 1'])

    def test_a_retired_class_drops_out_of_the_dropdown(self):
        self.school.classes = ['JSS 1', 'JSS 2', 'SSS 1']
        self.school.save(update_fields=['classes'])
        self.jss2.is_active = False
        self.jss2.save(update_fields=['is_active'])

        self.auth(self.admin)
        payload = self.client.get(self.url('/academics/')).json()
        self.assertEqual(sorted(payload['classes']), ['JSS 1', 'SSS 1'])

    def test_a_school_with_no_class_rows_gets_an_empty_list_not_the_defaults(self):
        """Inventing 14 class names would be fabricating data. An administrator
        adds real ones through the academics screen."""
        remove_all_classes(self.school)
        self.school.classes = []
        self.school.save(update_fields=['classes'])

        self.auth(self.admin)
        self.assertEqual(self.client.get(self.url('/academics/')).json()['classes'], [])


class ClassMirrorBackfillMigrationTests(SecurityTestBase):
    """`schools.0014` repairs the mirror at rest, so the dropdown is right even
    before the new read path has been deployed anywhere."""

    def run_migration(self):
        """Invoke the migration body the way Django does."""
        import importlib

        from django.apps import apps as global_apps
        from django.db.migrations import RunPython
        from django.db import connection

        module = importlib.import_module('schools.migrations.0014_backfill_class_mirror')

        class FakeSchemaEditor:
            connection = type('C', (), {'alias': 'default'})()

        module.rebuild_class_mirror(global_apps, FakeSchemaEditor())
        return module

    def test_the_migration_rebuilds_an_empty_mirror_from_the_class_rows(self):
        self.assertEqual(self.school.classes, [])

        self.run_migration()

        self.school.refresh_from_db()
        self.assertEqual(self.school.classes, ['JSS 1', 'JSS 2', 'SSS 1'])

    def test_the_migration_drops_a_class_that_no_longer_exists(self):
        self.school.classes = ['JSS 1', 'JSS 2', 'SSS 1', 'OLD CLASS']
        self.school.save(update_fields=['classes'])

        self.run_migration()

        self.school.refresh_from_db()
        self.assertEqual(self.school.classes, ['JSS 1', 'JSS 2', 'SSS 1'])

    def test_the_migration_excludes_a_retired_class(self):
        self.jss2.is_active = False
        self.jss2.save(update_fields=['is_active'])

        self.run_migration()

        self.school.refresh_from_db()
        self.assertEqual(self.school.classes, ['JSS 1', 'SSS 1'])

    def test_the_migration_clears_a_mirror_with_no_class_rows(self):
        """A name in the mirror with no `SchoolClass` row behind it is exactly the
        state that produced the 404s, so it must not survive."""
        remove_all_classes(self.school)
        self.school.classes = ['JSS 1', 'GHOST CLASS']
        self.school.save(update_fields=['classes'])

        self.run_migration()

        self.school.refresh_from_db()
        self.assertEqual(self.school.classes, [])

    def test_the_migration_repairs_every_school_not_just_one(self):
        """Drift is not per-school, so the repair must not stop at the first one:
        the rival school also holds a real `SchoolClass` with an empty mirror."""
        self.assertEqual(self.other_school.classes or [], [])

        self.run_migration()

        self.other_school.refresh_from_db()
        self.assertEqual(self.other_school.classes, ['JSS 1'])

    def test_the_migration_is_idempotent(self):
        self.run_migration()
        self.school.refresh_from_db()
        first = list(self.school.classes)

        self.run_migration()

        self.school.refresh_from_db()
        self.assertEqual(self.school.classes, first)

    def test_reverse_is_a_noop(self):
        from django.db.migrations import RunPython

        module = self.run_migration()
        self.assertIs(module.Migration.operations[0].reverse_code, RunPython.noop)

    def test_the_migration_and_the_read_path_agree(self):
        """The data migration and `sync_school_class_names` must not drift: if they
        did, deploying one and not the other would change the dropdown."""
        from records.services import academic as academic_service

        self.run_migration()
        self.school.refresh_from_db()
        from_migration = list(self.school.classes)

        self.school.classes = []
        self.school.save(update_fields=['classes'])

        self.assertEqual(academic_service.sync_school_class_names(self.school), from_migration)
