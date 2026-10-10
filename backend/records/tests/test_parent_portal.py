"""Parent portal: auto-provisioned logins and the child-facing read endpoints.

The portal exists so a parent can see their own children - their attendance,
their promotion suggestion and their report card - without ever touching the
school's administration. The rules under test:

* every student record bearing a guardian phone provisions that parent's login
  (one account per family, temporary password, forced first change), and the
  provisioning runs on create, patch and import without ever failing a save;
* `/parents/me/children/` answers only the students linked to the login, in the
  same paginated shape as the school roster;
* attendance, promotion and report card lookups answer 404 - never 403 - for a
  child that is not linked to the caller, so a parent cannot enumerate another
  family's ids;
* a report card is assembled only from PUBLISHED/LOCKED sheets, and the
  audiences are a linked parent, the pupil themselves, and staff with `reports.read`.
"""
from __future__ import annotations

from datetime import date

from rest_framework.test import APIClient

from accounts.models import User
from accounts.utils import DEFAULT_TEMPORARY_PASSWORD
from records.models import AttendanceRecord, ResultSheet, Student
from records.services import registration as registration_service
from records.services import results as results_service

from .test_security import SecurityTestBase

PHONE_A = '+2348010000001'
PHONE_B = '+2348010000002'
PHONE_C = '+2348010000003'
PHONE_D = '+2348010000004'
PHONE_STAFF = '+2348010000009'
PHONE_GUARD = '+2348010000010'


def create_payload(admission, guardian_phone=PHONE_A, **overrides):
    payload = {
        'firstName': 'Ada',
        'lastName': 'Nwosu',
        'admissionNumber': admission,
        'gender': 'female',
        'className': 'JSS 1',
        'arm': 'A',
        'guardianName': 'Mrs Nwosu',
        'guardianPhone': guardian_phone,
    }
    payload.update(overrides)
    return payload


class ParentAccountProvisioningTests(SecurityTestBase):
    def _post(self, payload, user=None):
        client = APIClient()
        client.force_authenticate(user or self.admin)
        return client.post('/api/v1/students/', payload, format='json')

    def _student(self, admission):
        return Student.objects.get(admission_number=admission)

    def test_student_create_provisions_a_parent_login(self):
        response = self._post(create_payload('SUA/P/0001'))
        self.assertEqual(response.status_code, 201, response.content)

        student = self._student('SUA/P/0001')
        parent = User.objects.get(phone=PHONE_A, role=User.Role.PARENT)
        # The default password is temporary and forced to change on login.
        self.assertTrue(parent.check_password(DEFAULT_TEMPORARY_PASSWORD))
        self.assertIs(parent.must_change_password, True)
        self.assertEqual(parent.school, self.school)
        self.assertIn(student, parent.linked_students.all())

    def test_a_second_student_with_the_same_phone_reuses_the_account(self):
        r1 = self._post(create_payload('SUA/P/0002'))
        r2 = self._post(create_payload('SUA/P/0003', guardian_phone=PHONE_A))
        self.assertEqual(r1.status_code, 201, r1.content)
        self.assertEqual(r2.status_code, 201, r2.content)

        parents = User.objects.filter(phone=PHONE_A, role=User.Role.PARENT)
        self.assertEqual(parents.count(), 1)
        self.assertIn(self._student('SUA/P/0003'), parents.first().linked_students.all())

    def test_a_student_without_a_phone_creates_no_account(self):
        # The create serializer refuses a blank phone, so the no-phone case is
        # the provisioning rule itself: nothing is ever created for a blank
        # number (a surname-only family is recorded, not blocked).
        student = self.make_student(admission_number='SUA/P/0004')
        provisioned = registration_service.ensure_parent_account(
            school=self.school, student=student,
            guardian_name='Mrs N', guardian_phone='',
        )
        self.assertIsNone(provisioned)
        self.assertFalse(User.objects.filter(linked_students=student).exists())

    def test_patch_adding_a_phone_provisions_and_links(self):
        student = self.make_student(
            admission_number='SUA/P/0005', guardian_phone='', guardian_name='',
        )
        self.auth(self.admin)
        response = self.client.patch(
            self.url(f'/students/{student.public_id}/'),
            {'guardianName': 'Mrs Nwosu', 'guardianPhone': PHONE_A},
            format='json',
        )
        self.assertEqual(response.status_code, 200, response.content)
        parent = User.objects.get(phone=PHONE_A, role=User.Role.PARENT)
        self.assertIn(student, parent.linked_students.all())

    def test_a_phone_owned_by_another_account_is_skipped_not_fatal(self):
        User.objects.create_user(
            email='head@hub.example', password='Strong-Pass-1!',
            role=User.Role.SCHOOL_ADMIN, school=self.school,
            phone=PHONE_STAFF, is_active=True,
        )
        response = self._post(create_payload('SUA/P/0006', guardian_phone=PHONE_STAFF))
        # A number already taken by another login cannot be handed to a parent:
        # the student still saves, and nothing is provisioned for the phone.
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(User.objects.filter(phone=PHONE_STAFF).count(), 1)
        student = self._student('SUA/P/0006')
        self.assertFalse(User.objects.filter(linked_students=student).exists())

    def test_changing_a_guardian_phone_moves_the_link(self):
        registration_service.ensure_parent_account(
            school=self.school, student=self.student,
            guardian_name='Mrs Bello', guardian_phone=PHONE_B,
        )
        first = User.objects.get(phone=PHONE_B)
        self.auth(self.admin)
        response = self.client.patch(
            self.url(f'/students/{self.student.public_id}/'),
            {'guardianPhone': PHONE_C},
            format='json',
        )
        self.assertEqual(response.status_code, 200, response.content)
        first.refresh_from_db()
        self.assertNotIn(self.student, first.linked_students.all())
        second = User.objects.get(phone=PHONE_C, role=User.Role.PARENT)
        self.assertIn(self.student, second.linked_students.all())


class ParentFirstLoginTests(SecurityTestBase):
    """The temporary password, the forced change, and the portal gate."""

    def setUp(self):
        super().setUp()
        self.guardian = User.objects.create_user(
            email=None, password=DEFAULT_TEMPORARY_PASSWORD,
            first_name='Guardian', last_name='One',
            role=User.Role.PARENT, school=self.school,
            phone=PHONE_GUARD, is_active=True, must_change_password=True,
        )
        self.guardian.linked_students.add(self.student)

    def _login(self, password):
        return self.client.post(
            self.url('/auth/login/'),
            {'identifier': PHONE_GUARD, 'password': password},
            format='json',
        )

    def test_the_temporary_password_logs_in_and_forces_a_change(self):
        response = self._login(DEFAULT_TEMPORARY_PASSWORD)
        self.assertEqual(response.status_code, 200, response.content)
        self.assertIs(response.json()['user']['mustChangePassword'], True)

    def test_the_temporary_password_stops_working_after_the_change(self):
        self.auth(self.guardian)
        changed = self.client.post(
            self.url('/auth/change-password/'),
            {'current': DEFAULT_TEMPORARY_PASSWORD, 'next': 'A-New-Parent-1!'},
            format='json',
        )
        self.assertEqual(changed.status_code, 200, changed.content)
        self.guardian.refresh_from_db()
        self.assertIs(self.guardian.must_change_password, False)

        self.client.force_authenticate(user=None)
        self.assertEqual(self._login(DEFAULT_TEMPORARY_PASSWORD).status_code, 401)
        fresh = self._login('A-New-Parent-1!')
        self.assertEqual(fresh.status_code, 200, fresh.content)
        self.assertIs(fresh.json()['user']['mustChangePassword'], False)

    def test_the_portal_is_blocked_until_the_password_changes(self):
        self.auth(self.guardian)
        response = self.client.get(self.url('/parents/me/children/'))
        self.assertEqual(response.status_code, 403)
        self.assertIn('temporary password', response.json()['detail'])

        changed = self.client.post(
            self.url('/auth/change-password/'),
            {'current': DEFAULT_TEMPORARY_PASSWORD, 'next': 'A-New-Parent-1!'},
            format='json',
        )
        self.assertEqual(changed.status_code, 200, changed.content)

        open_response = self.client.get(self.url('/parents/me/children/'))
        self.assertEqual(open_response.status_code, 200, open_response.content)


class ParentChildrenTests(SecurityTestBase):
    """The children list is the linked family, never the school roster."""

    def test_lists_only_the_linked_children(self):
        second = self.make_student(admission_number='SUA/P/0007')
        self.make_student(admission_number='SUA/P/0008', first_name='Noor')
        self.parent.linked_students.add(self.student, second)
        self.parent.save()

        self.auth(self.parent)
        response = self.client.get(self.url('/parents/me/children/?pageSize=50'))
        self.assertEqual(response.status_code, 200, response.content)
        body = response.json()
        self.assertEqual(body['count'], 2)
        self.assertEqual(
            {row['id'] for row in body['results']},
            {str(self.student.public_id), str(second.public_id)},
        )
        for key in ('page', 'pageSize', 'totalPages'):
            self.assertIn(key, body)

    def test_no_linked_children_is_an_empty_list(self):
        self.auth(self.parent)
        response = self.client.get(self.url('/parents/me/children/'))
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()['results'], [])

    def test_non_parent_roles_are_refused(self):
        for user in (self.admin, self.teacher, self.student_user):
            with self.subTest(role=user.role):
                self.auth(user)
                response = self.client.get(self.url('/parents/me/children/'))
                self.assertEqual(response.status_code, 403)

    def test_a_parent_cannot_read_the_school_roster(self):
        self.auth(self.parent)
        response = self.client.get(self.url('/students/'))
        self.assertEqual(response.status_code, 403)


class ParentChildEndpointGuardTests(SecurityTestBase):
    """One parent login, one family: every other child is a 404."""

    def setUp(self):
        super().setUp()
        self.parent.linked_students.add(self.student)
        self.other = self.make_student(admission_number='SUA/P/0009')
        self.auth(self.parent)

    def _child_urls(self, student_id):
        return (
            self.url(f'/parents/me/children/{student_id}/attendance/'),
            self.url(f'/parents/me/children/{student_id}/promotion/'),
        )

    def test_an_unlinked_child_of_the_same_school_is_a_404(self):
        for path in self._child_urls(self.other.id):
            self.assertEqual(self.client.get(path).status_code, 404)

    def test_a_student_of_another_school_is_a_404(self):
        for path in self._child_urls(self.other_student.public_id):
            self.assertEqual(self.client.get(path).status_code, 404)

    def test_reports_require_a_linked_child(self):
        self.assertEqual(
            self.client.get(self.url(f'/reports/report-cards/{self.other.id}/')).status_code,
            404,
        )
        self.assertEqual(
            self.client.get(
                self.url(f'/reports/report-cards/{self.other_student.public_id}/')
            ).status_code,
            404,
        )


class ParentAttendanceTests(SecurityTestBase):
    """Summaries are the child's own register, excused days kept out of the rate."""

    def setUp(self):
        super().setUp()
        self.parent.linked_students.add(self.student)
        self.auth(self.parent)

    def _attendance(self, student, day, status):
        AttendanceRecord.objects.create(
            school=self.school, student=student, class_obj=self.jss1,
            class_name='JSS 1', date=date(2026, 9, day), status=status,
        )

    def test_summary_counts_and_records_belong_to_the_child(self):
        self._attendance(self.student, 18, AttendanceRecord.Status.PRESENT)
        self._attendance(self.student, 21, AttendanceRecord.Status.ABSENT)
        self._attendance(self.student, 23, AttendanceRecord.Status.EXCUSED)
        self._attendance(self.other_student, 18, AttendanceRecord.Status.ABSENT)

        response = self.client.get(self.url(f'/parents/me/children/{self.student.public_id}/attendance/'))
        self.assertEqual(response.status_code, 200, response.content)
        summary = response.json()['summary']
        self.assertEqual(summary['recorded'], 3)
        self.assertEqual(summary['present'], 1)
        self.assertEqual(summary['absent'], 1)
        self.assertEqual(summary['excused'], 1)
        # (present) / (present + late + absent) rather than the whole register.
        self.assertEqual(summary['attendanceRate'], 50.0)

        records = response.json()['records']
        self.assertEqual(len(records), 3)
        self.assertEqual(records[0]['date'], '2026-09-23')
        self.assertEqual(records[0]['status'], 'excused')
        self.assertEqual(records[0]['className'], 'JSS 1')

    def test_date_range_limits_the_register(self):
        self._attendance(self.student, 18, AttendanceRecord.Status.PRESENT)
        self._attendance(self.student, 21, AttendanceRecord.Status.ABSENT)

        response = self.client.get(
            self.url(f'/parents/me/children/{self.student.public_id}/attendance/'),
            {'dateFrom': '2026-09-20', 'dateTo': '2026-09-22'},
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()['summary']['recorded'], 1)

    def test_invalid_dates_are_a_400(self):
        response = self.client.get(
            self.url(f'/parents/me/children/{self.student.public_id}/attendance/'),
            {'dateFrom': 'not-a-date'},
        )
        self.assertEqual(response.status_code, 400)


class ParentPromotionTests(SecurityTestBase):
    """The suggestion echoes the promotion screen's own calculation."""

    def setUp(self):
        super().setUp()
        self.parent.linked_students.add(self.student)
        self._publish_maths()

    def _publish_maths(self):
        sheet = results_service.create_sheet(
            school=self.school,
            academic_session=self.session,
            class_obj=self.jss1,
            subject='Mathematics',
            assessment=results_service.TERM_RESULTS_ASSESSMENT,
            term='First Term',
        )
        results_service.record_term_scores(sheet, {
            str(self.student.public_id): {'ca1': 10, 'ca2': 10, 'assignment': 20, 'exam': 60},
        })
        for to_status in list(ResultSheet.ALLOWED_TRANSITIONS.values())[:4]:
            sheet = results_service.advance(sheet, to_status, actor=self.admin)
        AttendanceRecord.objects.create(
            school=self.school, student=self.student, class_obj=self.jss1,
            class_name='JSS 1', date=date(2026, 9, 18),
            status=AttendanceRecord.Status.PRESENT,
        )
        AttendanceRecord.objects.create(
            school=self.school, student=self.student, class_obj=self.jss1,
            class_name='JSS 1', date=date(2026, 9, 21),
            status=AttendanceRecord.Status.PRESENT,
        )

    def test_suggestion_reason_and_next_class_are_returned(self):
        self.auth(self.parent)
        response = self.client.get(self.url(f'/parents/me/children/{self.student.public_id}/promotion/'))
        self.assertEqual(response.status_code, 200, response.content)
        body = response.json()
        self.assertIs(body['enrolled'], True)
        self.assertEqual(body['className'], 'JSS 1')
        self.assertEqual(body['suggested'], 'promote')
        self.assertEqual(body['average'], 100.0)
        self.assertEqual(body['attendanceRate'], 100.0)
        self.assertEqual(body['nextClass'], 'JSS 2')
        self.assertIs(body['isFinalClass'], False)
        self.assertIsNotNone(body['policy'])
        # The class record, untouched by the suggestion.
        self.assertEqual(len(body['history']), 1)
        self.assertEqual(body['history'][0]['className'], 'JSS 1')

    def test_an_unenrolled_child_has_no_suggestion(self):
        unenrolled = self.make_student(admission_number='SUA/P/0010')
        self.parent.linked_students.add(unenrolled)

        self.auth(self.parent)
        response = self.client.get(self.url(f'/parents/me/children/{unenrolled.public_id}/promotion/'))
        self.assertEqual(response.status_code, 200, response.content)
        body = response.json()
        self.assertIs(body['enrolled'], False)
        self.assertIsNone(body['suggested'])
        self.assertIn('enrollment', body['reason'])


class ParentReportCardTests(SecurityTestBase):
    """The card reads only published sheets and serves exactly its audiences."""

    def setUp(self):
        super().setUp()
        self.parent.linked_students.add(self.student)

    def _publish(self, subject='Mathematics', term='First Term', day=18):
        sheet = results_service.create_sheet(
            school=self.school,
            academic_session=self.session,
            class_obj=self.jss1,
            subject=subject,
            assessment=results_service.TERM_RESULTS_ASSESSMENT,
            term=term,
        )
        results_service.record_term_scores(sheet, {
            str(self.student.public_id): {'ca1': 10, 'ca2': 10, 'assignment': 20, 'exam': 60},
        })
        for to_status in list(ResultSheet.ALLOWED_TRANSITIONS.values())[:4]:
            sheet = results_service.advance(sheet, to_status, actor=self.admin)
        AttendanceRecord.objects.create(
            school=self.school, student=self.student, class_obj=self.jss1,
            class_name='JSS 1', date=date(2026, 9, day),
            status=AttendanceRecord.Status.PRESENT,
        )
        return sheet

    def test_a_linked_parent_reads_the_full_card(self):
        self._publish()

        self.auth(self.parent)
        response = self.client.get(self.url(f'/reports/report-cards/{self.student.public_id}/'))
        self.assertEqual(response.status_code, 200, response.content)
        body = response.json()
        self.assertEqual(body['student']['id'], str(self.student.public_id))
        self.assertEqual(body['student']['name'], 'Amina Bello')
        self.assertEqual(body['student']['className'], 'JSS 1')
        self.assertEqual(body['session'], self.session.name)
        self.assertEqual(body['term'], 'First Term')

        row = body['subjects'][0]
        self.assertEqual(row['subject'], 'Mathematics')
        self.assertEqual(row['total'], 100.0)
        self.assertEqual(row['grade'], 'A')
        self.assertEqual(body['totalScore'], 100.0)
        self.assertEqual(body['maxScore'], 100.0)
        self.assertEqual(body['average'], 100.0)
        self.assertTrue(body['remark'])

        # One child in the class is first of one; the promotion block uses the
        # same thresholds the promotion screen would.
        self.assertEqual(body['position'], {'rank': 1, 'outOf': 1})
        self.assertEqual(body['promotion']['suggested'], 'promote')
        self.assertEqual(body['attendance']['attendanceRate'], 100.0)

    def test_a_draft_sheet_is_never_visible(self):
        results_service.create_sheet(
            school=self.school,
            academic_session=self.session,
            class_obj=self.jss1,
            subject='Science',
            assessment=results_service.TERM_RESULTS_ASSESSMENT,
            term='First Term',
        )
        self.auth(self.parent)
        response = self.client.get(self.url(f'/reports/report-cards/{self.student.public_id}/'))
        self.assertEqual(response.status_code, 404)

    def test_the_term_filter_selects_one_term(self):
        self._publish(subject='Mathematics', term='First Term')
        self._publish(subject='Science', term='Second Term', day=21)

        self.auth(self.parent)
        response = self.client.get(
            self.url(f'/reports/report-cards/{self.student.public_id}/'),
            {'term': 'Second Term'},
        )
        self.assertEqual(response.status_code, 200, response.content)
        subjects = {row['subject'] for row in response.json()['subjects']}
        self.assertEqual(subjects, {'Science'})

    def test_a_student_login_sees_only_their_own_card(self):
        self._publish()
        self.student_user.student_profile = self.student
        self.student_user.save(update_fields=['student_profile'])
        unlinked = self.make_student(admission_number='SUA/P/0011')

        self.auth(self.student_user)
        self.assertEqual(
            self.client.get(self.url(f'/reports/report-cards/{self.student.public_id}/')).status_code,
            200,
        )
        self.assertEqual(
            self.client.get(self.url(f'/reports/report-cards/{unlinked.id}/')).status_code,
            404,
        )

    def test_staff_with_the_reports_permission_read_any_own_school_card(self):
        self._publish()
        self.auth(self.admin)
        self.assertEqual(
            self.client.get(self.url(f'/reports/report-cards/{self.student.public_id}/')).status_code,
            200,
        )

    def test_a_teacher_without_reports_permission_is_refused(self):
        self._publish()
        self.auth(self.teacher)
        response = self.client.get(self.url(f'/reports/report-cards/{self.student.public_id}/'))
        self.assertEqual(response.status_code, 403)

    def test_an_admin_of_another_school_gets_a_404(self):
        self._publish()
        self.auth(self.other_admin)
        response = self.client.get(self.url(f'/reports/report-cards/{self.student.public_id}/'))
        self.assertEqual(response.status_code, 404)

    def test_a_parent_before_the_password_change_is_gated_out(self):
        self._publish()
        self.parent.must_change_password = True
        self.parent.save(update_fields=['must_change_password'])

        self.auth(self.parent)
        response = self.client.get(self.url(f'/reports/report-cards/{self.student.public_id}/'))
        self.assertEqual(response.status_code, 403)