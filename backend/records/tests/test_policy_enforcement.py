"""Central policy enforcement: positive and negative security tests.

Each rule below is enforced by the API itself, never by hiding UI. The tests
prove both directions: valid operations succeed, violations are rejected, and
School A can never reach School B's data by crafting IDs.

Covered here (see records/services/policy.py for the shared guards):
- payment references are scoped to the caller's school (no cross-tenant
  oracle, no bogus duplicate blocks);
- teachers may only open and score result sheets for classes in their academic
  context (staff taught-class list or class-teacher designation), with the
  school-admin override intact;
- admission numbers are frozen once issued (rename rejected, no-op allowed);
- staff contact details are stripped for callers without staff.write while
  the directory itself stays readable (pinned behaviour);
- invoice re-issue never rewrites an invoice that has verified payments, and
  `paid` always equals the verified sum (no drift through verify/reverse).
"""
from decimal import Decimal

from accounts.models import User
from records.models import (
    AcademicSession,
    Invoice,
    ResultSheet,
    Student,
)
from records.services import results as results_service

from .test_security import SecurityTestBase


class PaymentReferenceIsolationTests(SecurityTestBase):
    def _pay(self, invoice, amount, reference, method='cash'):
        return self.client.post(
            self.url('/payments/'),
            {
                'invoiceId': str(invoice.id),
                'amount': amount,
                'method': method,
                'reference': reference,
            },
            format='json',
        )

    def _invoice_for(self, school, student, total='50000'):
        return Invoice.objects.create(
            school=school,
            student=student,
            academic_session=AcademicSession.objects.get(school=school),
            term='First Term',
            total=Decimal(total),
            paid=Decimal('0'),
            items=[{'label': 'Tuition', 'amount': total}],
        )

    def test_same_reference_in_another_school_is_allowed(self):
        self.auth(self.admin)
        home_invoice = self._invoice_for(self.school, self.student)
        resp = self._pay(home_invoice, 500, 'SHARED-REF')
        self.assertEqual(resp.status_code, 201, resp.content)

        rival_student = Student.objects.create(
            school=self.other_school, admission_number='RVC/P/1',
            first_name='R', last_name='ival', gender='male',
        )
        rival_invoice = self._invoice_for(self.other_school, rival_student)
        self.auth(self.other_admin)
        resp = self._pay(rival_invoice, 500, 'SHARED-REF')
        # The other school's reference must neither leak nor block this school.
        self.assertEqual(resp.status_code, 201, resp.content)

    def test_duplicate_reference_inside_the_school_is_rejected(self):
        self.auth(self.admin)
        invoice = self._invoice_for(self.school, self.student)
        self.assertEqual(self._pay(invoice, 500, 'DUP-REF').status_code, 201)
        resp = self._pay(invoice, 500, 'DUP-REF')
        self.assertEqual(resp.status_code, 400)
        self.assertIn('reference', str(resp.data))


class ResultsTeacherScopeTests(SecurityTestBase):
    def _sheet(self, class_obj, subject='Mathematics'):
        return results_service.create_sheet(
            school=self.school,
            academic_session=self.session,
            class_obj=class_obj,
            subject=subject,
            assessment='First Term Test',
        )

    def _create_via_api(self, class_obj):
        return self.client.post(
            self.url('/results/create/'),
            {'classId': str(class_obj.id), 'subject': 'Mathematics', 'term': 'First Term'},
            format='json',
        )

    def test_teacher_opens_a_sheet_for_their_assigned_class(self):
        self.auth(self.teacher)
        resp = self._create_via_api(self.jss1)
        self.assertEqual(resp.status_code, 201, resp.data)

    def test_teacher_cannot_open_a_sheet_for_an_unassigned_class(self):
        self.auth(self.teacher)
        resp = self._create_via_api(self.jss2)
        self.assertEqual(resp.status_code, 403)
        self.assertIn('assign', str(resp.data).lower())
        self.assertFalse(
            ResultSheet.objects.filter(school=self.school, class_obj=self.jss2).exists()
        )

    def test_teacher_without_a_staff_record_cannot_open_any_sheet(self):
        lone = User.objects.create_user(
            email='lone@success.example', password='Strong-Pass-1!',
            first_name='Lone', last_name='Teacher',
            role=User.Role.TEACHER, school=self.school, is_active=True,
        )
        self.auth(lone)
        resp = self._create_via_api(self.jss1)
        self.assertEqual(resp.status_code, 403)

    def test_school_admin_keeps_the_override(self):
        self.auth(self.admin)
        resp = self._create_via_api(self.jss2)
        self.assertEqual(resp.status_code, 201, resp.data)

    def test_subject_teacher_may_score_their_taught_class(self):
        sheet = self._sheet(self.jss1)
        self.auth(self.subject_teacher)
        resp = self.client.post(
            self.url(f'/results/{sheet.id}/action/'),
            {'action': 'scores', 'scores': {str(self.student.id): 75}},
            format='json',
        )
        self.assertEqual(resp.status_code, 200, resp.data)

    def test_teacher_cannot_score_or_submit_an_unassigned_class(self):
        sheet = self._sheet(self.jss2)
        self.auth(self.teacher)
        for action in ('scores', 'submit'):
            with self.subTest(action=action):
                payload = (
                    {'action': 'scores', 'scores': {}}
                    if action == 'scores'
                    else {'action': 'submit'}
                )
                resp = self.client.post(
                    self.url(f'/results/{sheet.id}/action/'), payload, format='json',
                )
                self.assertEqual(resp.status_code, 403, action)


class AdmissionNumberFrozenTests(SecurityTestBase):
    def test_patch_changing_the_admission_number_is_rejected(self):
        self.auth(self.admin)
        resp = self.client.patch(
            self.url(f'/students/{self.student.id}/'),
            {'admissionNumber': 'SUA/CHANGED/1'},
            format='json',
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn('admissionNumber', str(resp.data))
        self.student.refresh_from_db()
        self.assertEqual(self.student.admission_number, 'SUA/JSS/2026/000100')

    def test_patch_repeating_the_same_number_is_allowed(self):
        self.auth(self.admin)
        resp = self.client.patch(
            self.url(f'/students/{self.student.id}/'),
            {'admissionNumber': 'SUA/JSS/2026/000100', 'firstName': 'Amina'},
            format='json',
        )
        self.assertEqual(resp.status_code, 200, resp.data)


class StaffDirectoryPrivacyTests(SecurityTestBase):
    def test_student_reads_names_but_not_contact_details(self):
        self.auth(self.student_user)
        resp = self.client.get(self.url('/staff/'))
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(len(resp.data) > 0)
        for row in resp.data:
            self.assertIn('fullName', row)
            self.assertNotIn('email', row)
            self.assertNotIn('phone', row)

    def test_admin_keeps_full_contact_details(self):
        self.auth(self.admin)
        resp = self.client.get(self.url('/staff/'))
        self.assertEqual(resp.status_code, 200)
        row = next(r for r in resp.data if r['id'] == str(self.teacher_staff.id))
        self.assertEqual(row['email'], 'teacher@success.example')

    def test_parent_staff_detail_has_no_contact_details(self):
        self.auth(self.parent)
        resp = self.client.get(self.url(f'/staff/{self.teacher_staff.id}/'))
        self.assertEqual(resp.status_code, 200)
        self.assertNotIn('email', resp.data)
        self.assertNotIn('phone', resp.data)
        self.assertEqual(resp.data['fullName'], 'Teacher Test')


class InvoiceRewriteGuardTests(SecurityTestBase):
    def setUp(self):
        super().setUp()
        self.school.fee_structure = [
            {'label': 'Tuition', 'amount': '50000', 'className': '*'},
        ]
        self.school.save(update_fields=['fee_structure'])

    def _generate(self, overwrite=False):
        return self.client.post(
            self.url('/invoices/generate/'),
            {'className': 'JSS 1', 'term': 'First Term', 'overwrite': overwrite},
            format='json',
        )

    def _pay_cash(self, invoice, amount, reference):
        return self.client.post(
            self.url('/payments/'),
            {
                'invoiceId': str(invoice.id),
                'amount': amount,
                'method': 'cash',
                'reference': reference,
            },
            format='json',
        )

    def test_overwrite_updates_an_untouched_invoice(self):
        self.auth(self.admin)
        self.assertEqual(self._generate().status_code, 200)
        resp = self._generate(overwrite=True)
        self.assertEqual(resp.status_code, 200, resp.data)
        self.assertEqual(resp.data['updated'], 1)

    def test_overwrite_of_a_paid_invoice_is_rejected(self):
        self.auth(self.admin)
        self.assertEqual(self._generate().status_code, 200)
        invoice = Invoice.objects.get(
            school=self.school, student=self.student, term='First Term',
            is_cancelled=False,
        )
        self.assertEqual(
            self._pay_cash(invoice, 1000, 'POL-PAID-1').status_code, 201,
        )
        invoice.refresh_from_db()
        before = (invoice.total, invoice.items)

        resp = self._generate(overwrite=True)
        self.assertEqual(resp.status_code, 400)
        self.assertIn('overwrite', str(resp.data))
        invoice.refresh_from_db()
        self.assertEqual((invoice.total, invoice.items), before)

    def test_paid_always_equals_the_verified_sum(self):
        self.auth(self.admin)
        self.assertEqual(self._generate().status_code, 200)
        invoice = Invoice.objects.get(
            school=self.school, student=self.student, term='First Term',
            is_cancelled=False,
        )
        self.assertEqual(self._pay_cash(invoice, 1000, 'POL-SUM-1').status_code, 201)
        self.assertEqual(self._pay_cash(invoice, 2000, 'POL-SUM-2').status_code, 201)
        invoice.refresh_from_db()
        self.assertEqual(invoice.paid, Decimal('3000'))

        payment = invoice.payments.get(reference='POL-SUM-2')
        reverse = self.client.post(self.url(f'/payments/{payment.id}/reverse/'))
        self.assertEqual(reverse.status_code, 200, reverse.content)
        invoice.refresh_from_db()
        self.assertEqual(invoice.paid, Decimal('1000'))


class TamperedSessionIsRejectedTests(SecurityTestBase):
    def test_parent_report_card_with_another_schools_session_is_404(self):
        self.parent.linked_students.add(self.student)
        self.auth(self.parent)
        other_session = AcademicSession.objects.get(school=self.other_school)
        resp = self.client.get(
            self.url(f'/reports/report-cards/{self.student.id}/'),
            {'sessionId': str(other_session.id)},
        )
        self.assertEqual(resp.status_code, 404)
