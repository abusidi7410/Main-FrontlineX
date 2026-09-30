"""Cancelling an invoice must not permanently block re-issuing it.

A cancelled invoice is retained as history. The uniqueness rule on
(student, academic session, term) therefore only applies to *live* invoices -
otherwise a student who had an invoice cancelled could never be billed that
term again, and the finance screen's "overwrite" path would silently rewrite
the cancelled row instead of raising a fresh charge.
"""

from decimal import Decimal

from django.test import TestCase
from rest_framework.test import APIClient

from accounts.models import User
from records.models import AcademicSession, Invoice, Student
from schools.models import School


def make_invoice(**kwargs):
    defaults = {
        'total': Decimal('50000'),
        'paid': Decimal('0'),
        'items': [{'label': 'Tuition', 'amount': '50000'}],
    }
    defaults.update(kwargs)
    return Invoice.objects.create(**defaults)


class CancelledInvoiceDoesNotBlockReissue(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name='Reissue Academy', slug='reissue-academy', address='a',
            state='Kano', lga='Kano', phone='0800', email='r@e.com')
        self.session = AcademicSession.objects.create(
            school=self.school, name='2026/2027', start_year=2026,
            end_year=2027, is_current=True)
        self.student = Student.objects.create(
            school=self.school, admission_number='R/1', first_name='A',
            last_name='B', gender='male', class_name='JSS 1')

    def test_live_invoice_still_blocks_a_duplicate(self):
        """The guard itself must still work - this is not a free-for-all."""
        make_invoice(school_id=self.school.id, student_id=self.student.id,
                     academic_session=self.session, term='First Term')
        with self.assertRaises(Exception):
            make_invoice(school_id=self.school.id, student_id=self.student.id,
                         academic_session=self.session, term='First Term')

    def test_cancelled_invoice_frees_the_slot(self):
        cancelled = make_invoice(
            school_id=self.school.id, student_id=self.student.id,
            academic_session=self.session, term='First Term')
        cancelled.is_cancelled = True
        cancelled.save(update_fields=['is_cancelled'])

        replacement = make_invoice(
            school_id=self.school.id, student_id=self.student.id,
            academic_session=self.session, term='First Term')

        self.assertNotEqual(replacement.id, cancelled.id)
        self.assertFalse(replacement.is_cancelled)
        # The cancelled row is still there as history.
        self.assertTrue(Invoice.objects.filter(id=cancelled.id).exists())


class GenerateInvoicesSkipsCancelledRows(TestCase):
    """The bulk generator must issue a new invoice, not revive a cancelled one."""

    def setUp(self):
        self.client = APIClient()
        self.school = School.objects.create(
            name='Bulk Academy', slug='bulk-academy', address='a', state='Kano',
            lga='Kano', phone='0800', email='b@e.com',
            fee_structure=[{'label': 'Tuition', 'amount': '50000', 'className': '*'}],
        )
        self.student = Student.objects.create(
            school=self.school, admission_number='B/1', first_name='A',
            last_name='B', gender='male', class_name='JSS 1',
            status=Student.Status.ACTIVE)
        self.cancelled = make_invoice(
            school_id=self.school.id, student_id=self.student.id,
            term='First Term', total=Decimal('1000'),
            items=[{'label': 'Old charge', 'amount': '1000'}])
        self.cancelled.is_cancelled = True
        self.cancelled.save(update_fields=['is_cancelled'])

        user = User.objects.create_user(
            email='acct@bulk-academy.com', password='Str0ng!Passw0rd',
            role='accountant', school=self.school)
        self.client.force_authenticate(user=user)

    def test_generate_creates_a_fresh_invoice(self):
        r = self.client.post('/api/v1/invoices/generate/', {
            'className': 'JSS 1', 'term': 'First Term', 'overwrite': True,
        }, format='json')
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(r.data['generated'], 1)

        self.cancelled.refresh_from_db()
        # The cancelled row must be untouched, not rewritten and revived.
        self.assertTrue(self.cancelled.is_cancelled)
        self.assertEqual(self.cancelled.total, Decimal('1000'))
        self.assertEqual(self.cancelled.items, [{'label': 'Old charge', 'amount': '1000'}])

        live = Invoice.objects.filter(
            student=self.student, term='First Term', is_cancelled=False)
        self.assertEqual(live.count(), 1)
        self.assertEqual(live.get().total, Decimal('50000'))
