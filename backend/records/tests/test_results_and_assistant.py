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

from django.urls import reverse

from records.models import (
    AcademicSession,
    Enrollment,
    FeeStructure,
    Invoice,
    Payment,
    ResultEntry,
    ResultSheet,
    SchoolClass,
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
        resp = self.act('scores', scores={str(self.other_student.id): 40})
        self.assertEqual(resp.status_code, 400)
        self.assertIn('roster', str(resp.data))

    def test_score_above_the_assessment_maximum_is_rejected(self):
        self.auth(self.teacher)
        resp = self.act('scores', scores={str(self.student.id): 150})
        self.assertEqual(resp.status_code, 400)
        self.assertIn('maximum', str(resp.data))

    def test_score_is_graded_and_saved(self):
        self.auth(self.teacher)
        resp = self.act('scores', scores={str(self.student.id): 75})
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
        resp = self.act('scores', scores={str(self.student.id): 10})
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
        self.assertEqual(self.sheet.status, ResultSheet.Status.APPROVED)
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
        resp = self.ask('get_my_child_attendance', student_id=str(self.other_student.id))
        self.assertEqual(resp.status_code, 403)

    def test_parent_cannot_read_another_familys_child_even_within_the_same_school(self):
        second = Student.objects.create(
            school=self.school, admission_number='SUA/JSS/2026/000200',
            first_name='Bola', last_name='Adeyemi', gender='male', class_name='JSS 1',
            status=Student.Status.ACTIVE,
        )
        self.parent.linked_students.add(self.student)
        self.auth(self.parent)
        resp = self.ask('get_my_child_attendance', student_id=str(second.id))
        self.assertEqual(resp.status_code, 403)

    def test_parent_is_never_shown_financial_data(self):
        """A parent holds no finance permission, so the assistant must not quote
        them a balance even about their own child."""
        self.parent.linked_students.add(self.student)
        self.auth(self.parent)
        self.assertEqual(self.ask('get_fee_balance', student_id=str(self.student.id)).status_code, 403)
        self.assertEqual(self.ask('get_financial_summary').status_code, 403)

    def test_student_sees_only_themselves(self):
        self.student_user.student_profile = self.student
        self.student_user.save(update_fields=['student_profile'])
        self.auth(self.student_user)
        resp = self.ask('get_my_profile')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data['data']['id'], str(self.student.id))
        # The student role has no school-wide tools at all.
        self.assertEqual(self.ask('search_students').status_code, 403)
        self.assertEqual(self.ask('get_financial_summary').status_code, 403)

    def test_student_cannot_read_another_students_record(self):
        self.student_user.student_profile = self.student
        self.student_user.save(update_fields=['student_profile'])
        self.auth(self.student_user)
        self.assertEqual(
            self.ask('get_my_child_attendance', student_id=str(self.other_student.id)).status_code,
            403,
        )

    def test_teacher_cannot_read_finance(self):
        self.auth(self.teacher)
        self.assertEqual(self.ask('get_financial_summary').status_code, 403)
        self.assertEqual(self.ask('get_fee_balance', student_id=str(self.student.id)).status_code, 403)

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
        resp = self.ask('get_student', student_id=str(self.other_student.id))
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
