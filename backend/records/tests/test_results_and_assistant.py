"""The results lifecycle and the assistant's authorisation boundary.

Two things are pinned here, because both are the kind of rule that silently
stops being true:

**Results (spec 51-55).** A sheet only ever moves one step forward, a LOCKED
sheet cannot be edited, and a correction has to be requested and authorised
before a published score changes. Anything less and a published result becomes
editable by anyone with a login.

**The assistant (spec 62-68).** The assistant inherits permissions; it never
gains any. These tests are mostly about refusals, because the interesting
failure mode is a role reading data it should not have.
"""
from decimal import Decimal

import datetime

from django.urls import reverse

from records.models import (
    AcademicSession,
    AttendanceRecord,
    ClassTeacherAssignment,
    Enrollment,
    FeeStructure,
    Invoice,
    Payment,
    ResultEntry,
    ResultSheet,
    SchoolClass,
    Section,
    Student,
    StaffMember,
    invoice_item_amount,
)
from records.services import results as results_service

from .test_security import SecurityTestBase


class ResultSheetLifecycleTests(SecurityTestBase):
    def setUp(self):
        super().setUp()
        self.sheet = results_service.create_sheet(
            school=self.school,
            academic_session=self.session,
            class_obj=self.jss1,
            subject='Mathematics',
            assessment='First Term Test',
        )

    def act(self, action, **payload):
        return self.client.post(
            self.url(f'/results/{self.sheet.id}/action/'),
            {'action': action, **payload},
            format='json',
        )

    def test_sheet_starts_as_draft_seeded_from_the_roster(self):
        self.assertEqual(self.sheet.status, ResultSheet.Status.DRAFT)
        self.assertEqual(self.sheet.entries.count(), 1)
        self.assertEqual(self.sheet.entries.first().student_id, self.student.id)

    def test_student_not_on_the_roster_cannot_be_scored(self):
        self.auth(self.teacher)
        resp = self.act('scores', scores={str(self.other_student.public_id): 40})
        self.assertEqual(resp.status_code, 400)
        self.assertIn('roster', str(resp.data))

    def test_score_above_the_assessment_maximum_is_rejected(self):
        self.auth(self.teacher)
        resp = self.act('scores', scores={str(self.student.public_id): 150})
        self.assertEqual(resp.status_code, 400)
        self.assertIn('maximum', str(resp.data))

    def test_score_is_graded_and_saved(self):
        self.auth(self.teacher)
        resp = self.act('scores', scores={str(self.student.public_id): 75})
        self.assertEqual(resp.status_code, 200)
        entry = self.sheet.entries.first()
        entry.refresh_from_db()
        self.assertEqual(entry.score, Decimal('75.00'))
        self.assertEqual(entry.grade, ResultEntry.Grade.A)

    def test_sheet_cannot_skip_approval(self):
        self.auth(self.admin)
        # DRAFT -> PUBLISHED is not a legal single step.
        resp = self.act('publish')
        self.assertEqual(resp.status_code, 400)
        self.sheet.refresh_from_db()
        self.assertEqual(self.sheet.status, ResultSheet.Status.DRAFT)

    def test_sheet_moves_forward_one_step_at_a_time(self):
        self.auth(self.admin)
        for action, expected in [
            ('submit', ResultSheet.Status.SUBMITTED),
            ('review', ResultSheet.Status.UNDER_REVIEW),
            ('approve', ResultSheet.Status.APPROVED),
            ('publish', ResultSheet.Status.PUBLISHED),
            ('lock', ResultSheet.Status.LOCKED),
        ]:
            self.assertEqual(self.act(action).status_code, 200, action)
            self.sheet.refresh_from_db()
            self.assertEqual(self.sheet.status, expected, action)
        self.assertTrue(self.sheet.is_locked)
        self.assertIsNotNone(self.sheet.locked_at)

    def test_locked_sheet_cannot_be_rescored(self):
        self.auth(self.admin)
        for action in ('submit', 'review', 'approve', 'publish', 'lock'):
            self.act(action)
        self.sheet.refresh_from_db()
        self.assertTrue(self.sheet.is_locked)
        self.auth(self.teacher)
        resp = self.act('scores', scores={str(self.student.public_id): 10})
        self.assertEqual(resp.status_code, 400)
        self.assertIn('locked', str(resp.data).lower())

    def test_locked_sheet_cannot_be_moved_further(self):
        self.auth(self.admin)
        for action in ('submit', 'review', 'approve', 'publish', 'lock'):
            self.act(action)
        self.assertEqual(self.act('lock').status_code, 400)

    def test_correction_needs_a_reason_and_then_authorisation(self):
        self.auth(self.admin)
        for action in ('submit', 'review', 'approve', 'publish', 'lock'):
            self.act(action)
        # A reason is mandatory: a bare "fix it" is not an audit trail.
        self.assertEqual(self.act('request-correction', reason='  ').status_code, 400)
        self.assertEqual(
            self.act('request-correction', reason='Mark was entered on the wrong row').status_code,
            200,
        )
        self.assertEqual(self.act('release-correction').status_code, 200)
        self.sheet.refresh_from_db()
        self.assertFalse(self.sheet.is_locked)
        self.assertEqual(self.sheet.status, ResultSheet.Status.DRAFT)
        self.assertEqual(self.sheet.correction_authorised_by_id, self.admin.id)

    def test_correction_cannot_be_released_without_a_request(self):
        self.auth(self.admin)
        for action in ('submit', 'review', 'approve', 'publish', 'lock'):
            self.act(action)
        self.assertEqual(self.act('release-correction').status_code, 400)

    def test_teacher_cannot_publish(self):
        self.auth(self.teacher)
        self.assertEqual(self.act('submit').status_code, 200)
        self.assertEqual(self.act('review').status_code, 403)

    def test_teacher_cannot_approve(self):
        self.auth(self.teacher)
        self.act('submit')
        self.assertEqual(self.act('approve').status_code, 403)

    def test_result_sheet_from_another_school_is_not_reachable(self):
        other_class = SchoolClass.objects.filter(school=self.other_school).first()
        other_sheet = results_service.create_sheet(
            school=self.other_school,
            academic_session=AcademicSession.objects.get(school=self.other_school),
            class_obj=other_class,
            subject='Mathematics',
            assessment='Exam',
        )
        self.auth(self.admin)
        resp = self.client.get(self.url(f'/results/{other_sheet.id}/'))
        self.assertEqual(resp.status_code, 404)

    def test_class_from_another_school_cannot_open_a_sheet(self):
        other_class = SchoolClass.objects.filter(school=self.other_school).first()
        self.auth(self.admin)
        resp = self.client.post(
            self.url('/results/create/'),
            {
                'classId': str(other_class.id),
                'subject': 'Mathematics',
                'assessment': 'Exam',
            },
            format='json',
        )
        self.assertEqual(resp.status_code, 404)
        self.assertEqual(ResultSheet.objects.filter(school=self.other_school).count(), 0)


class ResultSheetListTests(SecurityTestBase):
    def test_list_is_school_scoped_and_paginated(self):
        results_service.create_sheet(
            school=self.school, academic_session=self.session, class_obj=self.jss1,
            subject='Mathematics', assessment='Test',
        )
        other_class = SchoolClass.objects.filter(school=self.other_school).first()
        results_service.create_sheet(
            school=self.other_school,
            academic_session=AcademicSession.objects.get(school=self.other_school),
            class_obj=other_class, subject='Mathematics', assessment='Test',
        )
        self.auth(self.principal)
        resp = self.client.get(self.url('/results/'), {'page': 1, 'pageSize': 25})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data['count'], 1)
        self.assertEqual(resp.data['pageSize'], 25)
        self.assertTrue(all(row['className'] == 'JSS 1' for row in resp.data['results']))


class TermResultSheetTests(SecurityTestBase):
    def setUp(self):
        super().setUp()
        self.auth(self.teacher)
        self.create_response = self.client.post(
            self.url('/results/create/'),
            {
                'classId': str(self.jss1.id),
                'subject': 'Mathematics',
                'term': 'First Term',
            },
            format='json',
        )
        self.assertEqual(self.create_response.status_code, 201, self.create_response.data)
        self.sheet_id = str(self.create_response.data['id'])

    def action(self, action, **payload):
        return self.client.post(
            self.url(f'/results/{self.sheet_id}/action/'),
            {'action': action, **payload},
            format='json',
        )

    def test_term_sheet_is_created_with_component_rows(self):
        self.assertEqual(self.create_response.data['assessment'], 'Term Results')
        self.assertEqual(self.create_response.data['rows'][0]['studentId'], str(self.student.public_id))
        self.assertIsNone(self.create_response.data['rows'][0]['ca1'])

    def test_component_scores_are_saved_and_totaled(self):
        response = self.action(
            'scores',
            termScores={
                str(self.student.public_id): {
                    'ca1': 9,
                    'ca2': 8,
                    'assignment': 18,
                    'exam': 55,
                },
            },
        )
        self.assertEqual(response.status_code, 200, response.data)
        row = response.data['rows'][0]
        self.assertEqual(row['score'], 90.0)
        self.assertEqual(row['grade'], 'A')

    def test_component_scores_cannot_exceed_component_maximum(self):
        response = self.action(
            'scores',
            termScores={str(self.student.public_id): {'ca1': 11}},
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn('between 0 and 10', str(response.data))

    def test_term_sheet_cannot_be_submitted_until_every_component_is_recorded(self):
        response = self.action('submit')
        self.assertEqual(response.status_code, 400)
        self.assertIn('all four', str(response.data))

        save_response = self.action(
            'scores',
            termScores={
                str(self.student.public_id): {
                    'ca1': 10,
                    'ca2': 10,
                    'assignment': 20,
                    'exam': 60,
                },
            },
        )
        self.assertEqual(save_response.status_code, 200)
        submit_response = self.action('submit')
        self.assertEqual(submit_response.status_code, 200, submit_response.data)


class PublishedResultsAccessTests(SecurityTestBase):
    def setUp(self):
        super().setUp()
        self.sheet = results_service.create_sheet(
            school=self.school,
            academic_session=self.session,
            class_obj=self.jss1,
            subject='Mathematics',
            assessment=results_service.TERM_RESULTS_ASSESSMENT,
            term='First Term',
        )
        results_service.record_term_scores(
            self.sheet,
            {
                str(self.student.public_id): {
                    'ca1': 10,
                    'ca2': 10,
                    'assignment': 20,
                    'exam': 60,
                },
            },
        )
        for status in ResultSheet.ALLOWED_TRANSITIONS.values():
            self.sheet = results_service.advance(self.sheet, status, actor=self.admin)
        results_service.create_sheet(
            school=self.school,
            academic_session=self.session,
            class_obj=self.jss1,
            subject='Science',
            assessment=results_service.TERM_RESULTS_ASSESSMENT,
            term='Second Term',
        )

    def test_parent_sees_only_published_results_for_linked_students(self):
        self.parent.linked_students.add(self.student)
        self.auth(self.parent)

        response = self.client.get(self.url('/results/children/'))

        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['count'], 1)
        row = response.data['results'][0]
        self.assertEqual(row['studentId'], str(self.student.public_id))
        self.assertEqual(row['score'], 100.0)
        self.assertEqual(row['grade'], 'A')

    def test_parent_with_no_linked_students_sees_no_results(self):
        self.auth(self.parent)

        response = self.client.get(self.url('/results/children/'))

        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['results'], [])

    def test_school_results_report_requires_reports_permission(self):
        self.auth(self.teacher)

        response = self.client.get(self.url('/results/report/'))

        self.assertEqual(response.status_code, 403)

    def test_school_results_report_includes_only_published_results(self):
        self.auth(self.admin)

        response = self.client.get(self.url('/results/report/'))

        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['count'], 1)
        self.assertEqual(response.data['results'][0]['subject'], 'Mathematics')


class AssistantPermissionInheritanceTests(SecurityTestBase):
    """The assistant must never see more than its user can."""

    def ask(self, tool, **arguments):
        return self.client.post(
            self.url('/assistant/query/'),
            {'tool': tool, 'arguments': arguments},
            format='json',
        )

    def test_no_assistant_access_without_an_ai_permission(self):
        self.auth(self.secretary)
        self.assertEqual(self.ask('get_school_summary').status_code, 403)

    def test_unauthenticated_request_is_rejected(self):
        self.client.force_authenticate(user=None)
        self.assertEqual(self.ask('get_school_summary').status_code, 401)

    def test_parent_sees_their_own_children(self):
        self.parent.linked_students.add(self.student)
        self.auth(self.parent)
        resp = self.ask('get_my_children')
        self.assertEqual(resp.status_code, 200)
        names = [row['name'] for row in resp.data['data']['children']]
        self.assertIn('Bello, Amina', names)

    def test_parent_with_no_linked_children_sees_nobody(self):
        """The link is explicit: a parent account that has not been linked to a
        student must not fall back to a name or phone-number match."""
        self.auth(self.parent)
        resp = self.ask('get_my_children')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data['data']['children'], [])

    def test_parent_cannot_read_the_whole_roster(self):
        self.auth(self.parent)
        self.assertEqual(self.ask('search_students').status_code, 403)
        self.assertEqual(self.ask('get_school_summary').status_code, 403)

    def test_parent_cannot_read_another_familys_child(self):
        self.parent.linked_students.add(self.student)
        self.auth(self.parent)
        resp = self.ask('get_my_child_attendance', student_id=str(self.other_student.public_id))
        self.assertEqual(resp.status_code, 403)

    def test_parent_cannot_read_another_familys_child_even_within_the_same_school(self):
        second = Student.objects.create(
            school=self.school, admission_number='SUA/JSS/2026/000200',
            first_name='Bola', last_name='Adeyemi', gender='male', class_name='JSS 1',
            status=Student.Status.ACTIVE,
        )
        self.parent.linked_students.add(self.student)
        self.auth(self.parent)
        resp = self.ask('get_my_child_attendance', student_id=str(second.public_id))
        self.assertEqual(resp.status_code, 403)

    def test_parent_is_never_shown_financial_data(self):
        """A parent holds no finance permission, so the assistant must not quote
        them a balance even about their own child."""
        self.parent.linked_students.add(self.student)
        self.auth(self.parent)
        self.assertEqual(self.ask('get_fee_balance', student_id=str(self.student.public_id)).status_code, 403)
        self.assertEqual(self.ask('get_financial_summary').status_code, 403)

    def test_student_sees_only_themselves(self):
        self.student_user.student_profile = self.student
        self.student_user.save(update_fields=['student_profile'])
        self.auth(self.student_user)
        resp = self.ask('get_my_profile')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data['data']['id'], str(self.student.public_id))
        # The student role has no school-wide tools at all.
        self.assertEqual(self.ask('search_students').status_code, 403)
        self.assertEqual(self.ask('get_financial_summary').status_code, 403)

    def test_student_cannot_read_another_students_record(self):
        self.student_user.student_profile = self.student
        self.student_user.save(update_fields=['student_profile'])
        self.auth(self.student_user)
        self.assertEqual(
            self.ask('get_my_child_attendance', student_id=str(self.other_student.public_id)).status_code,
            403,
        )

    def test_teacher_cannot_read_finance(self):
        self.auth(self.teacher)
        self.assertEqual(self.ask('get_financial_summary').status_code, 403)
        self.assertEqual(self.ask('get_fee_balance', student_id=str(self.student.public_id)).status_code, 403)

    def test_teacher_is_confined_to_assigned_classes(self):
        StaffMember.objects.create(
            school=self.school, full_name='Teacher One',
            email=self.teacher.email, role='teacher', classes=['JSS 2'],
            status=StaffMember.Status.ACTIVE,
        )
        self.auth(self.teacher)
        # Assigned to JSS 2 only.
        self.assertEqual(self.ask('get_class_results', class_name='JSS 2').status_code, 200)
        self.assertEqual(self.ask('get_class_results', class_name='JSS 1').status_code, 403)
        self.assertEqual(
            self.ask('get_class_attendance', class_name='JSS 1', day='2026-01-05').status_code,
            403,
        )

    def test_a_teacher_cannot_ask_who_is_absent_school_wide(self):
        """`get_absent_students` has an OPTIONAL class argument, so `_check_scope`
        has no `class_name` to narrow on. Without the tool narrowing its own
        classes, omitting the argument would hand a teacher the whole school."""
        other_student = Student.objects.create(
            school=self.school, admission_number='SUA/JSS/2026/000500',
            first_name='Kemi', last_name='Ayo', gender='female',
            class_name='JSS 2', status=Student.Status.ACTIVE,
        )
        section = Section.objects.create(
            school=self.school, class_obj=self.jss2, name='A',
        )
        Enrollment.objects.create(
            school=self.school, student=other_student, academic_session=self.session,
            class_obj=self.jss2, section=section, status=Enrollment.Status.ACTIVE,
        )
        AttendanceRecord.objects.create(
            school=self.school, student=other_student, class_obj=self.jss2,
            class_name='JSS 2', date=datetime.date(2026, 1, 5),
            status=AttendanceRecord.Status.ABSENT,
        )
        AttendanceRecord.objects.create(
            school=self.school, student=self.student, class_obj=self.jss1,
            class_name='JSS 1', date=datetime.date(2026, 1, 5),
            status=AttendanceRecord.Status.PRESENT,
        )

        self.auth(self.teacher)
        resp = self.ask('get_absent_students', day='2026-01-05')
        self.assertEqual(resp.status_code, 200, resp.content)
        # The absent JSS 2 student must not appear: they are not in the teacher's
        # class, even though the argument was omitted.
        self.assertEqual(resp.data['data']['count'], 0)
        self.assertEqual(resp.data['data']['absent'], [])

        # An admin, who is not confined, does see them.
        self.auth(self.admin)
        admin_resp = self.ask('get_absent_students', day='2026-01-05')
        self.assertEqual(admin_resp.data['data']['count'], 1)
        self.assertEqual(
            admin_resp.data['data']['absent'][0]['className'], 'JSS 2',
        )

    def test_a_designated_class_teacher_is_confined_to_that_class(self):
        """The teacher's staff record lists no classes; the assignment is what
        makes JSS 1 theirs, and it must be enough to see their own register."""
        self.assertEqual(self.teacher_staff.classes, [])
        self.auth(self.teacher)
        data = self.ask('get_attendance_submission_status', day='2026-01-05').data['data']
        self.assertEqual([row['className'] for row in data['classes']], ['JSS 1'])

    def test_a_teacher_with_no_assignment_gets_nothing_from_the_daily_tools(self):
        self.teacher_staff.classes = []
        self.teacher_staff.save(update_fields=['classes'])
        ClassTeacherAssignment.objects.filter(staff=self.teacher_staff).delete()

        self.auth(self.teacher)
        self.assertEqual(
            self.ask('get_absent_students', day='2026-01-05').data['data']['count'], 0,
        )
        status = self.ask('get_attendance_submission_status', day='2026-01-05')
        self.assertEqual(status.data['data']['totalClasses'], 0)
        self.assertEqual(status.data['data']['notSubmitted'], [])

    def test_the_submission_status_tool_reports_classes_that_have_not_registered(self):
        self.auth(self.admin)
        resp = self.ask('get_attendance_submission_status', day='2026-01-05')
        self.assertEqual(resp.status_code, 200, resp.content)
        data = resp.data['data']
        self.assertEqual(data['submittedCount'], 0)
        self.assertEqual(data['totalClasses'], 3)
        self.assertEqual(sorted(data['notSubmitted']), ['JSS 1', 'JSS 2', 'SSS 1'])

    def test_the_submission_status_tool_reports_a_taken_register(self):
        AttendanceRecord.objects.create(
            school=self.school, student=self.student, class_obj=self.jss1,
            class_name='JSS 1', date=datetime.date(2026, 1, 5),
            status=AttendanceRecord.Status.PRESENT,
        )
        self.auth(self.admin)
        data = self.ask(
            'get_attendance_submission_status', day='2026-01-05',
        ).data['data']
        self.assertEqual(data['submittedCount'], 1)
        self.assertEqual(sorted(data['notSubmitted']), ['JSS 2', 'SSS 1'])

    def test_the_submission_status_tool_marks_a_weekend_as_not_a_school_day(self):
        saturday = '2026-01-03'
        self.assertEqual(datetime.date.fromisoformat(saturday).weekday(), 5)
        self.auth(self.admin)
        data = self.ask('get_attendance_submission_status', day=saturday).data['data']
        self.assertFalse(data['isSchoolDay'])

    def test_chronic_absence_needs_a_real_threshold(self):
        # Relative to today: the window is the last N days, so fixed dates would
        # silently fall outside it as the suite ages.
        today = datetime.date.today()
        for offset in (1, 2, 6):
            AttendanceRecord.objects.create(
                school=self.school, student=self.student, class_obj=self.jss1,
                class_name='JSS 1', date=today - datetime.timedelta(days=offset),
                status=AttendanceRecord.Status.ABSENT,
            )
        self.auth(self.admin)
        data = self.ask('get_chronic_absence', minimum_absences=3).data['data']
        self.assertEqual(data['count'], 1)
        self.assertEqual(data['students'][0]['absences'], 3)
        self.assertEqual(data['students'][0]['student'], 'Bello, Amina')

        # Above the threshold the student drops out rather than being listed.
        self.assertEqual(
            self.ask('get_chronic_absence', minimum_absences=4).data['data']['count'], 0,
        )

    def test_chronic_absence_ignores_days_outside_the_window(self):
        today = datetime.date.today()
        for offset in (1, 40, 60):
            AttendanceRecord.objects.create(
                school=self.school, student=self.student, class_obj=self.jss1,
                class_name='JSS 1', date=today - datetime.timedelta(days=offset),
                status=AttendanceRecord.Status.ABSENT,
            )
        self.auth(self.admin)
        data = self.ask(
            'get_chronic_absence', minimum_absences=1, days=30,
        ).data['data']
        self.assertEqual(data['count'], 1)
        self.assertEqual(data['students'][0]['absences'], 1)

    def test_chronic_absence_ignores_late_and_present_days(self):
        AttendanceRecord.objects.create(
            school=self.school, student=self.student, class_obj=self.jss1,
            class_name='JSS 1',
            date=datetime.date.today() - datetime.timedelta(days=1),
            status=AttendanceRecord.Status.LATE,
        )
        self.auth(self.admin)
        self.assertEqual(
            self.ask('get_chronic_absence', minimum_absences=1).data['data']['count'], 0,
        )

    def test_chronic_absence_does_not_escape_the_school(self):
        AttendanceRecord.objects.create(
            school=self.other_school, student=self.other_student,
            class_obj=self.other_jss1, class_name='JSS 1',
            date=datetime.date.today() - datetime.timedelta(days=1),
            status=AttendanceRecord.Status.ABSENT,
        )
        self.auth(self.admin)
        self.assertEqual(
            self.ask('get_chronic_absence', minimum_absences=1).data['data']['count'], 0,
        )

    def test_the_absent_list_reports_late_as_well_as_absent(self):
        AttendanceRecord.objects.create(
            school=self.school, student=self.student, class_obj=self.jss1,
            class_name='JSS 1', date=datetime.date(2026, 1, 5),
            status=AttendanceRecord.Status.LATE,
        )
        self.auth(self.admin)
        data = self.ask('get_absent_students', day='2026-01-05').data['data']
        self.assertEqual(data['count'], 1)
        self.assertEqual(data['absent'][0]['status'], 'late')

    def test_a_parent_cannot_reach_any_daily_attendance_tool(self):
        self.parent.linked_students.add(self.student)
        self.auth(self.parent)
        for tool, kwargs in (
            ('get_absent_students', {'day': '2026-01-05'}),
            ('get_attendance_submission_status', {'day': '2026-01-05'}),
            ('get_chronic_absence', {}),
        ):
            self.assertEqual(self.ask(tool, **kwargs).status_code, 403, tool)

    def test_a_malformed_date_is_rejected_by_the_daily_tools(self):
        self.auth(self.admin)
        for tool in ('get_absent_students', 'get_attendance_submission_status'):
            resp = self.ask(tool, day='05-01-2026')
            self.assertEqual(resp.status_code, 400, tool)
            self.assertIn('date', str(resp.data))

    def test_accountant_sees_finance_but_not_teaching_tools(self):
        self.auth(self.accountant)
        self.assertEqual(self.ask('get_financial_summary').status_code, 200)
        self.assertEqual(self.ask('get_class_results', class_name='JSS 1').status_code, 403)

    def test_school_admin_reaches_the_broadest_surface(self):
        self.auth(self.admin)
        resp = self.client.get(self.url('/assistant/tools/'))
        self.assertEqual(resp.status_code, 200)
        names = {tool['name'] for tool in resp.data['tools']}
        self.assertIn('get_school_summary', names)
        self.assertIn('get_financial_summary', names)
        self.assertIn('get_class_results', names)

    def test_tool_catalogue_never_overstates_access(self):
        self.auth(self.teacher)
        names = {
            tool['name']
            for tool in self.client.get(self.url('/assistant/tools/')).data['tools']
        }
        self.assertIn('get_class_results', names)
        self.assertNotIn('get_financial_summary', names)
        self.assertNotIn('get_my_children', names)

    def test_another_schools_student_is_not_found(self):
        self.auth(self.admin)
        resp = self.ask('get_student', student_id=str(self.other_student.public_id))
        self.assertEqual(resp.status_code, 400)
        self.assertIn('No such student', str(resp.data))

    def test_unknown_tool_is_rejected(self):
        self.auth(self.admin)
        self.assertEqual(self.ask('drop_all_tables').status_code, 400)


class AssistantWriteConfirmationTests(SecurityTestBase):
    def setUp(self):
        super().setUp()
        fee = FeeStructure.objects.create(
            school=self.school, academic_session=self.session, label='Tuition',
            amount=Decimal('5000'), scope='school', scope_key='*', is_required=True,
        )
        self.invoice = Invoice.objects.create(
            school=self.school, student=self.student, academic_session=self.session,
            term='First Term', total=Decimal('5000'), paid=Decimal('0'),
            items=[{
                'feeStructureId': fee.id, 'feeType': 'tuition', 'label': 'Tuition',
                'amount': str(invoice_item_amount({'amount': '5000'})),
                'scope': 'school', 'scopeKey': '*', 'term': '', 'isRequired': True,
            }],
        )
        self.payment = Payment.objects.create(
            school=self.school, invoice=self.invoice, amount=Decimal('5000'),
            reference='PAY-SUA-1', method='cash', recorded_by=self.accountant,
            status=Payment.Status.PENDING,
        )

    def propose(self, **payload):
        return self.client.post(
            self.url('/assistant/query/'),
            {'action': 'propose', 'writeAction': 'verify_payment', 'arguments': payload},
            format='json',
        )

    def test_first_call_only_proposes_and_changes_nothing(self):
        self.auth(self.accountant)
        resp = self.propose(payment_id=str(self.payment.id))
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.data['confirmationRequired'])
        self.assertIn('confirmationToken', resp.data)
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, 'pending')

    def test_confirming_performs_the_action(self):
        self.auth(self.accountant)
        token = self.propose(payment_id=str(self.payment.id)).data['confirmationToken']
        resp = self.client.post(
            self.url('/assistant/query/'),
            {
                'action': 'confirm', 'writeAction': 'verify_payment',
                'confirmationToken': token,
            },
            format='json',
        )
        self.assertEqual(resp.status_code, 200)
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, 'verified')

    def test_a_confirmation_token_cannot_be_replayed(self):
        self.auth(self.accountant)
        token = self.propose(payment_id=str(self.payment.id)).data['confirmationToken']
        body = {
            'action': 'confirm', 'writeAction': 'verify_payment', 'confirmationToken': token,
        }
        self.assertEqual(
            self.client.post(self.url('/assistant/query/'), body, format='json').status_code,
            200,
        )
        self.assertEqual(
            self.client.post(self.url('/assistant/query/'), body, format='json').status_code,
            400,
        )

    def test_another_users_token_cannot_be_used(self):
        self.auth(self.accountant)
        token = self.propose(payment_id=str(self.payment.id)).data['confirmationToken']
        self.auth(self.admin)
        self.assertEqual(
            self.client.post(
                self.url('/assistant/query/'),
                {
                    'action': 'confirm', 'writeAction': 'verify_payment',
                    'confirmationToken': token,
                },
                format='json',
            ).status_code,
            403,
        )

    def test_a_role_without_finance_verify_cannot_propose(self):
        self.auth(self.teacher)
        self.assertEqual(self.propose(payment_id=str(self.payment.id)).status_code, 403)

    def test_a_payment_from_another_school_is_not_verifiable(self):
        self.auth(self.accountant)
        other_invoice = Invoice.objects.create(
            school=self.other_school, student=self.other_student,
            academic_session=AcademicSession.objects.get(school=self.other_school),
            term='First Term', total=Decimal('5000'), paid=Decimal('0'), items=[],
        )
        other_payment = Payment.objects.create(
            school=self.other_school, invoice=other_invoice, amount=Decimal('5000'),
            reference='PAY-RVC-1', method='cash', status=Payment.Status.PENDING,
        )
        token = self.propose(payment_id=str(other_payment.id)).data['confirmationToken']
        resp = self.client.post(
            self.url('/assistant/query/'),
            {'action': 'confirm', 'writeAction': 'verify_payment', 'confirmationToken': token},
            format='json',
        )
        self.assertEqual(resp.status_code, 400)
        other_payment.refresh_from_db()
        self.assertEqual(other_payment.status, 'pending')
