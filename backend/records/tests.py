import datetime
from django.test import TestCase
from rest_framework.test import APIClient

from accounts.models import User
from records.models import AttendanceRecord, Invoice, Payment, Student
from schools.models import School


class AttendanceFinanceTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name='Sunrise Academy', slug='sunrise-academy', address='1 Sunrise Way',
            state='Kano', lga='Kano Municipal', phone='+2348000000011',
            email='sunrise@example.com', is_active=True,
        )
        self.admin = User.objects.create_user(
            email='admin@sunrise.example', password='Strong-Pass-1!',
            first_name='Sunrise', last_name='Admin',
            role=User.Role.SCHOOL_ADMIN, school=self.school, is_active=True,
        )
        self.accountant = User.objects.create_user(
            email='fin@sunrise.example', password='Strong-Pass-1!',
            first_name='Aisha', last_name='Yusuf',
            role=User.Role.ACCOUNTANT, school=self.school, is_active=True,
        )
        self.teacher = User.objects.create_user(
            email='teacher@sunrise.example', password='Strong-Pass-1!',
            first_name='Teacher', last_name='Ali',
            role=User.Role.TEACHER, school=self.school, is_active=True,
        )
        self.student = Student.objects.create(
            school=self.school, admission_number='SRN-001',
            first_name='Amina', last_name='Bello', gender='female',
            class_name='JSS 1', arm='A', status=Student.Status.ACTIVE,
        )
        self.student_b = Student.objects.create(
            school=self.school, admission_number='SRN-002',
            first_name='Tunde', last_name='Okafor', gender='male',
            class_name='JSS 1', arm='B', status=Student.Status.ACTIVE,
        )
        self.client = APIClient()

    def _auth(self, user):
        self.client.force_authenticate(user)

    def _url(self, path):
        return f'/api/v1{path}'


# ── Attendance ─────────────────────────────────────────────────────────────

class AttendanceRosterTests(AttendanceFinanceTests):
    def test_roster_lists_students_for_selected_class(self):
        self._auth(self.teacher)
        resp = self.client.get(self._url('/attendance/roster/'), {'className': 'JSS 1'})
        self.assertEqual(resp.status_code, 200, resp.content)
        names = {row['firstName'] for row in resp.json()['students']}
        self.assertEqual(names, {'Amina', 'Tunde'})

    def test_roster_filters_by_arm(self):
        self._auth(self.teacher)
        resp = self.client.get(self._url('/attendance/roster/'), {'className': 'JSS 1', 'arm': 'A'})
        rows = resp.json()['students']
        self.assertEqual([r['admissionNumber'] for r in rows], ['SRN-001'])
        self.assertFalse(resp.json()['taken'])

    def test_roster_reports_taken_state_with_existing_marks(self):
        self._auth(self.teacher)
        AttendanceRecord.objects.create(
            school=self.school, student=self.student, class_name='JSS 1',
            date=datetime.date(2026, 9, 18), status=AttendanceRecord.Status.PRESENT,
        )
        resp = self.client.get(
            self._url('/attendance/roster/'),
            {'className': 'JSS 1', 'arm': 'A', 'date': '2026-09-18'},
        )
        data = resp.json()
        self.assertTrue(data['taken'])
        self.assertEqual(data['existing'][str(self.student.id)], 'present')


class AttendanceSubmitTests(AttendanceFinanceTests):
    def test_attendance_can_only_be_taken_once_per_class_and_date(self):
        self._auth(self.teacher)
        payload = {
            'className': 'JSS 1',
            'date': '2026-09-18',
            'records': [
                {'studentId': str(self.student.id), 'status': 'present'},
                {'studentId': str(self.student_b.id), 'status': 'absent'},
            ],
        }
        first = self.client.post(self._url('/attendance/'), payload, format='json')
        self.assertEqual(first.status_code, 201, first.content)
        self.assertEqual(AttendanceRecord.objects.count(), 2)

        second = self.client.post(self._url('/attendance/'), payload, format='json')
        self.assertEqual(second.status_code, 409, second.content)
        self.assertEqual(AttendanceRecord.objects.count(), 2)

    def test_partial_submission_only_marks_valid_students(self):
        self._auth(self.teacher)
        resp = self.client.post(
            self._url('/attendance/'),
            {
                'className': 'JSS 1',
                'date': '2026-09-19',
                'records': [{'studentId': '99999', 'status': 'present'}],
            },
            format='json',
        )
        self.assertEqual(resp.status_code, 201, resp.content)
        self.assertEqual(AttendanceRecord.objects.count(), 0)


# ── Finance permissions ────────────────────────────────────────────────────

class FinancePermissionTests(AttendanceFinanceTests):
    def test_teacher_cannot_list_invoices_or_payments(self):
        self._auth(self.teacher)
        self.assertEqual(self.client.get(self._url('/invoices/')).status_code, 403)
        self.assertEqual(self.client.get(self._url('/payments/')).status_code, 403)

    def test_teacher_cannot_record_payment(self):
        self._auth(self.teacher)
        resp = self.client.post(self._url('/payments/'), {'amount': 100}, format='json')
        self.assertEqual(resp.status_code, 403)

    def test_treasurer_is_required_to_record_payments(self):
        invoice = Invoice.objects.create(
            school=self.school, student=self.student, term='First Term', total=1000,
        )
        self._auth(self.teacher)
        resp = self.client.post(
            self._url('/payments/'),
            {'invoiceId': str(invoice.id), 'amount': 100, 'method': 'cash'},
            format='json',
        )
        self.assertEqual(resp.status_code, 403)
        self._auth(self.accountant)
        resp = self.client.post(
            self._url('/payments/'),
            {'invoiceId': str(invoice.id), 'amount': 100, 'method': 'cash'},
            format='json',
        )
        self.assertEqual(resp.status_code, 201, resp.content)


# ── Payment business rules ─────────────────────────────────────────────────

class PaymentLifecycleTests(AttendanceFinanceTests):
    def setUp(self):
        super().setUp()
        self.school.fee_structure = [
            {'label': 'Tuition', 'amount': 100000, 'className': '*'},
        ]
        self.school.save(update_fields=['fee_structure'])
        self.invoice = Invoice.objects.create(
            school=self.school, student=self.student, term='First Term',
            total=100000, paid=0, items=[{'label': 'Tuition', 'amount': 100000}],
        )
        self._auth(self.accountant)

    def _record(self, amount, method='cash', reference=None):
        payload = {'invoiceId': str(self.invoice.id), 'amount': amount, 'method': method}
        if reference:
            payload['reference'] = reference
        return self.client.post(self._url('/payments/'), payload, format='json')

    def test_cash_payment_is_verified_immediately_and_credits_invoice(self):
        resp = self._record(20000)
        self.assertEqual(resp.status_code, 201, resp.content)
        payment = Payment.objects.get(id=resp.json()['id'])
        self.assertEqual(payment.status, Payment.Status.VERIFIED)
        self.invoice.refresh_from_db()
        self.assertEqual(float(self.invoice.paid), 20000)

    def test_bank_transfer_stays_pending_until_verified(self):
        resp = self._record(30000, method='bank_transfer')
        self.assertEqual(resp.status_code, 201, resp.content)
        payment = Payment.objects.get(id=resp.json()['id'])
        self.assertEqual(payment.status, Payment.Status.PENDING)
        self.invoice.refresh_from_db()
        self.assertEqual(float(self.invoice.paid), 0)

    def test_overpayment_is_rejected(self):
        resp = self._record(150000)
        self.assertEqual(resp.status_code, 400, resp.content)
        self.assertFalse(Payment.objects.filter(school=self.school).exists())

    def test_negative_and_zero_amounts_are_rejected(self):
        self.assertEqual(self._record(0).status_code, 400)
        self.assertEqual(self._record(-5).status_code, 400)

    def test_duplicate_reference_is_rejected(self):
        self.assertEqual(self._record(100, reference='FN-DUP').status_code, 201)
        resp = self._record(100, reference='FN-DUP')
        self.assertEqual(resp.status_code, 400)
        self.assertTrue('reference' in resp.json()['fieldErrors'])

    def test_verify_credits_invoice_and_is_idempotent(self):
        self._record(40000, method='bank_transfer')
        payment = Payment.objects.get(status=Payment.Status.PENDING)
        verify = self.client.post(self._url(f'/payments/{payment.id}/verify/'))
        self.assertEqual(verify.status_code, 200, verify.content)
        self.invoice.refresh_from_db()
        self.assertEqual(float(self.invoice.paid), 40000)
        again = self.client.post(self._url(f'/payments/{payment.id}/verify/'))
        self.assertEqual(again.status_code, 200)
        self.invoice.refresh_from_db()
        self.assertEqual(float(self.invoice.paid), 40000)

    def test_verify_rejects_payment_above_outstanding(self):
        self._record(60000, method='bank_transfer')
        self._record(50000, method='cash')
        self.invoice.refresh_from_db()
        self.assertEqual(float(self.invoice.paid), 50000)
        pending = Payment.objects.get(status=Payment.Status.PENDING)
        resp = self.client.post(self._url(f'/payments/{pending.id}/verify/'))
        self.assertEqual(resp.status_code, 400, resp.content)
        pending.refresh_from_db()
        self.assertEqual(pending.status, Payment.Status.PENDING)
        self.invoice.refresh_from_db()
        self.assertEqual(float(self.invoice.paid), 50000)

    def test_reverse_debits_invoice_and_only_for_verified(self):
        self._record(20000)
        payment = Payment.objects.get(status=Payment.Status.VERIFIED)
        resp = self.client.post(self._url(f'/payments/{payment.id}/reverse/'))
        self.assertEqual(resp.status_code, 200, resp.content)
        payment.refresh_from_db()
        self.assertEqual(payment.status, Payment.Status.REVERSED)
        self.invoice.refresh_from_db()
        self.assertEqual(float(self.invoice.paid), 0)
        again = self.client.post(self._url(f'/payments/{payment.id}/reverse/'))
        self.assertEqual(again.status_code, 400)

    def test_cancel_only_cancels_pending(self):
        self._record(20000, method='bank_transfer')
        pending = Payment.objects.get(status=Payment.Status.PENDING)
        resp = self.client.post(self._url(f'/payments/{pending.id}/cancel/'))
        self.assertEqual(resp.status_code, 200, resp.content)
        pending.refresh_from_db()
        self.assertEqual(pending.status, Payment.Status.CANCELLED)
        again = self.client.post(self._url(f'/payments/{pending.id}/cancel/'))
        self.assertEqual(again.status_code, 400)


# ── Fee structure & invoice generation ─────────────────────────────────────

class FeeInvoiceTests(AttendanceFinanceTests):
    def setUp(self):
        super().setUp()
        self._auth(self.admin)

    def test_fee_structure_get_and_update(self):
        resp = self.client.put(
            self._url('/fees/structure/'),
            {
                'items': [
                    {'label': 'Tuition', 'amount': 50000, 'className': '*'},
                    {'label': 'Boarding', 'amount': 20000, 'className': 'SS 1'},
                ],
            },
            format='json',
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        self.school.refresh_from_db()
        self.assertEqual(len(self.school.fee_structure), 2)

    def test_fee_structure_rejects_invalid_amounts(self):
        resp = self.client.put(
            self._url('/fees/structure/'),
            {'items': [{'label': 'Tuition', 'amount': -5, 'className': '*'}]},
            format='json',
        )
        self.assertEqual(resp.status_code, 400)

    def test_generate_invoice_creates_one_per_active_student(self):
        self.school.fee_structure = [
            {'label': 'Tuition', 'amount': 50000, 'className': '*'},
            {'label': 'Sport', 'amount': 5000, 'className': 'JSS 1'},
        ]
        self.school.save(update_fields=['fee_structure'])
        resp = self.client.post(
            self._url('/invoices/generate/'),
            {'className': 'JSS 1', 'term': 'First Term'},
            format='json',
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(resp.json()['generated'], 2)
        invoices = Invoice.objects.filter(school=self.school)
        self.assertEqual(invoices.count(), 2)
        for invoice in invoices:
            self.assertEqual(float(invoice.total), 55000)
            self.assertEqual(invoice.status, 'unpaid')

    def test_generate_invoice_is_idempotent_per_term(self):
        self.school.fee_structure = [{'label': 'Tuition', 'amount': 50000, 'className': '*'}]
        self.school.save(update_fields=['fee_structure'])
        self.client.post(
            self._url('/invoices/generate/'),
            {'className': 'JSS 1', 'term': 'First Term'},
            format='json',
        )
        second = self.client.post(
            self._url('/invoices/generate/'),
            {'className': 'JSS 1', 'term': 'First Term'},
            format='json',
        )
        self.assertEqual(second.json()['generated'], 0)
        self.assertEqual(Invoice.objects.count(), 2)

    def test_generate_requires_fee_structure(self):
        resp = self.client.post(
            self._url('/invoices/generate/'),
            {'className': 'JSS 1', 'term': 'First Term'},
            format='json',
        )
        self.assertEqual(resp.status_code, 400, resp.content)