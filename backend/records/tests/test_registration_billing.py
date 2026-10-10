"""New admissions pay a one-time registration invoice when one is configured.

Two behaviours are pinned here:

Regular school fees are billed separately by term. Students without a
registration fee can start immediately and receive term invoices later.

Registration activation is driven by *verified* money only, so a pending or
partial payment can never wave a student through.

The same behaviour applies to schools with no fee structure configured.
"""
from decimal import Decimal

from records.models import Invoice, Payment, Student

from .test_security import SecurityTestBase

FEES = [
    {'label': 'Registration fee', 'amount': 5000.0, 'className': '*'},
    {'label': 'Tuition', 'amount': 50000.0, 'className': '*'},
    {'label': 'Development levy', 'amount': 5000.0, 'className': 'JSS 1'},
]


def payload(**overrides):
    data = {
        'firstName': 'Ada',
        'lastName': 'Nwosu',
        'gender': 'female',
        'className': 'JSS 1',
        'guardianName': 'Mrs Nwosu',
        'guardianPhone': '+2348000001234',
        'dateOfBirth': '2014-05-02',
    }
    data.update(overrides)
    return data


class RegistrationBillingTests(SecurityTestBase):
    def setUp(self):
        super().setUp()
        self.school.fee_structure = FEES
        self.school.save(update_fields=['fee_structure'])
        self.auth(self.secretary)

    def register(self, **overrides):
        return self.client.post(self.url('/students/'), payload(**overrides), format='json')

    def latest(self, first_name='Ada'):
        return Student.objects.get(school=self.school, first_name=first_name)


class StudentStatusOnCreateTests(RegistrationBillingTests):
    def test_saving_fees_does_not_touch_students_who_are_already_billed(self):
        """An admission invoice is a snapshot; re-saving fees must not raise a
        second one or rewrite the first."""
        self.register()
        self.assertEqual(Invoice.objects.filter(student=self.latest()).count(), 1)
        self.auth(self.accountant)
        r = self.client.put(
            self.url('/fees/structure/'), {'items': FEES}, format='json',
        )
        self.assertEqual(r.json()['invoicedPendingStudents'], 0)
        self.assertEqual(Invoice.objects.filter(student=self.latest()).count(), 1)

    def test_new_student_is_not_active(self):
        r = self.register()
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(self.latest().status, Student.Status.PENDING_PAYMENT)

    def test_status_is_pending_payment_even_with_a_supplied_number(self):
        """A school-migrated admission number must not skip the payment gate."""
        r = self.register(admissionNumber='SUA/JSS/2026/009900')
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(self.latest().status, Student.Status.PENDING_PAYMENT)

    def test_pending_payment_is_not_suspended(self):
        """Unpaid is a billing hold, not a punishment on an existing student."""
        self.register()
        self.assertNotEqual(self.latest().status, Student.Status.SUSPENDED)

    def test_creation_still_issues_the_admission_number(self):
        r = self.register()
        self.assertEqual(r.status_code, 201, r.content)
        self.assertTrue(self.latest().admission_number)
        self.assertEqual(
            self.latest().admission_number_source,
            Student.AdmissionNumberSource.SYSTEM_GENERATED,
        )


class AutoInvoiceTests(RegistrationBillingTests):
    def test_registration_raises_the_invoice_immediately(self):
        r = self.register()
        self.assertEqual(r.status_code, 201, r.content)
        invoice = Invoice.objects.get(student=self.latest())
        self.assertEqual(invoice.total, Decimal('5000.00'))
        self.assertEqual(invoice.source, Invoice.Source.ADMISSION)
        self.assertEqual(invoice.paid, Decimal('0'))

    def test_invoice_is_a_snapshot_of_the_configured_fees(self):
        self.register()
        invoice = Invoice.objects.get(student=self.latest())
        self.assertEqual(
            sorted(item['label'] for item in invoice.items),
            ['Registration fee'],
        )
        self.assertIsNotNone(invoice.due_date)

    def test_response_tells_the_ui_the_invoice_exists(self):
        r = self.register()
        body = r.json()
        self.assertTrue(body['registrationFeeConfigured'])
        self.assertTrue(body['invoiceId'])
        self.assertEqual(Decimal(body['invoiceTotal']), Decimal('5000.00'))

    def test_class_specific_fee_does_not_leak_to_another_class(self):
        self.register(className='JSS 2')
        invoice = Invoice.objects.get(student=self.latest())
        self.assertEqual(invoice.total, Decimal('5000.00'))

    def test_registering_twice_creates_one_invoice_each(self):
        self.register(firstName='Ada')
        self.register(firstName='Bisi', admissionNumber='SUA/JSS/2026/009901')
        self.assertEqual(Invoice.objects.filter(school=self.school).count(), 2)

    def test_registration_and_term_fees_are_billed_as_separate_invoices(self):
        self.register()
        admission_invoice = Invoice.objects.get(student=self.latest())
        self.auth(self.accountant)
        r = self.client.post(
            self.url('/invoices/generate/'),
            {'className': 'JSS 1', 'term': 'First Term'},
            format='json',
        )
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.json()['generated'], 1)
        term_invoice = Invoice.objects.get(student=self.student, term='First Term')
        self.assertEqual(admission_invoice.total, Decimal('5000.00'))
        self.assertEqual(term_invoice.total, Decimal('55000.00'))


class NoFeeStructureTests(RegistrationBillingTests):
    """A school that has not set up fees yet must still be able to enrol."""

    def setUp(self):
        super().setUp()
        self.school.fee_structure = []
        self.school.save(update_fields=['fee_structure'])

    def test_registration_succeeds_without_raising_an_error(self):
        r = self.register()
        self.assertEqual(r.status_code, 201, r.content)

    def test_student_without_registration_fee_is_active_immediately(self):
        self.register()
        student = self.latest()
        self.assertEqual(student.status, Student.Status.ACTIVE)
        self.assertTrue(student.admission_number)

    def test_regular_fees_without_a_registration_fee_do_not_create_an_admission_invoice(self):
        self.school.fee_structure = [
            {'label': 'Tuition', 'amount': 50000.0, 'className': '*'},
        ]
        self.school.save(update_fields=['fee_structure'])
        response = self.register()
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(self.latest().status, Student.Status.ACTIVE)
        self.assertFalse(Invoice.objects.filter(student=self.latest()).exists())

    def test_no_invoice_is_created(self):
        self.register()
        self.assertFalse(Invoice.objects.filter(student=self.latest()).exists())

    def test_response_flags_that_fees_are_unconfigured(self):
        r = self.register()
        body = r.json()
        self.assertFalse(body['registrationFeeConfigured'])
        self.assertEqual(body['invoiceId'], '')

    def test_saving_fees_later_keeps_existing_active_student_active(self):
        self.register()
        student = self.latest()
        self.assertFalse(Invoice.objects.filter(student=student).exists())
        self.auth(self.accountant)
        r = self.client.put(
            self.url('/fees/structure/'), {'items': FEES}, format='json',
        )
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.json()['invoicedPendingStudents'], 0)
        self.assertEqual(r.json()['activatedPendingStudents'], 0)
        student.refresh_from_db()
        self.assertEqual(student.status, Student.Status.ACTIVE)
        self.assertFalse(Invoice.objects.filter(student=student).exists())



    def test_saving_fees_never_invoices_an_already_active_student(self):
        """Active students already carry their own history."""
        self.school.fee_structure = FEES
        self.school.save(update_fields=['fee_structure'])
        self.auth(self.accountant)
        r = self.client.put(
            self.url('/fees/structure/'), {'items': FEES}, format='json',
        )
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.json()['invoicedPendingStudents'], 0)
        self.assertFalse(Invoice.objects.filter(student=self.student).exists())


class ActivationOnSettlementTests(RegistrationBillingTests):
    def settle(self, amount, verified=True, invoice=None):
        """Record a payment the way the bursar would, through the API."""
        if invoice is None:
            invoice = Invoice.objects.get(
                student=self.latest(), term='', source=Invoice.Source.ADMISSION,
            )
        self.auth(self.accountant)
        method = Payment.Method.CASH if verified else Payment.Method.BANK_TRANSFER
        return self.client.post(
            self.url('/payments/'),
            {'invoiceId': str(invoice.id), 'amount': str(amount), 'method': method},
            format='json',
        )

    def test_full_verified_payment_activates_the_student(self):
        self.register()
        r = self.settle('5000.00')
        self.assertEqual(r.status_code, 201, r.content)
        self.assertTrue(r.json()['studentActivated'])
        self.assertEqual(self.latest().status, Student.Status.ACTIVE)

    def test_partial_payment_does_not_activate(self):
        self.register()
        self.settle('2000.00')
        self.assertEqual(self.latest().status, Student.Status.PENDING_PAYMENT)

    def test_pending_payment_does_not_activate(self):
        """Only verified money counts, so a bank transfer in flight is not paid."""
        self.register()
        self.settle('5000.00', verified=False)
        self.assertEqual(self.latest().status, Student.Status.PENDING_PAYMENT)
        self.assertEqual(
            Invoice.objects.get(student=self.latest()).status, 'unpaid',
        )

    def test_second_instalment_activates_the_student(self):
        self.register()
        self.settle('2000.00')
        self.assertEqual(self.latest().status, Student.Status.PENDING_PAYMENT)
        self.settle('3000.00')
        self.assertEqual(self.latest().status, Student.Status.ACTIVE)

    def test_verifying_a_pending_transfer_activates_the_student(self):
        self.register()
        created = self.settle('5000.00', verified=False)
        payment_id = created.json()['id']
        self.assertEqual(self.latest().status, Student.Status.PENDING_PAYMENT)
        self.auth(self.accountant)
        r = self.client.post(self.url(f'/payments/{payment_id}/verify/'), {}, format='json')
        self.assertEqual(r.status_code, 200, r.content)
        self.assertTrue(r.json()['studentActivated'])
        self.assertEqual(self.latest().status, Student.Status.ACTIVE)

    def test_cancelled_invoice_does_not_count_as_settled(self):
        self.register()
        invoice = Invoice.objects.get(
            student=self.latest(), term='', source=Invoice.Source.ADMISSION,
        )
        invoice.is_cancelled = True
        invoice.save(update_fields=['is_cancelled'])
        from records.services import billing

        self.assertFalse(
            billing.activate_student_if_fully_paid(self.latest()),
        )
        self.assertEqual(self.latest().status, Student.Status.PENDING_PAYMENT)

    def test_a_student_who_was_never_billed_is_not_treated_as_settled(self):
        """Zero invoices is the brand-new-school case, not a free pass."""
        self.register()
        student = self.latest()
        Invoice.objects.all().delete()
        from records.services import billing

        self.assertFalse(billing.activate_student_if_fully_paid(student))
        self.assertEqual(self.latest().status, Student.Status.PENDING_PAYMENT)

    def test_activation_never_demotes_a_suspended_student(self):
        """A stray payment must not undo a disciplinary suspension."""
        self.register()
        student = self.latest()
        student.status = Student.Status.SUSPENDED
        student.save(update_fields=['status'])
        self.settle('5000.00')
        self.assertEqual(self.latest().status, Student.Status.SUSPENDED)

    def test_activation_never_reactivates_a_graduated_student(self):
        self.register()
        student = self.latest()
        student.status = Student.Status.GRADUATED
        student.save(update_fields=['status'])
        self.settle('5000.00')
        self.assertEqual(self.latest().status, Student.Status.GRADUATED)

    def test_outstanding_school_fees_do_not_hold_a_settled_registration(self):
        """Registration state comes from the registration workflow alone.

        A later term invoice is a separate business process: once the
        registration fee is settled the student starts school, whatever the
        normal-fee balance happens to be.
        """
        self.register()
        student = self.latest()
        registration_invoice = Invoice.objects.get(
            student=student, term='', source=Invoice.Source.ADMISSION,
        )
        Invoice.objects.create(
            school=self.school, student=student, term='Second Term',
            total=Decimal('10000.00'), items=[{'label': 'Exam', 'amount': '10000.00'}],
        )
        self.settle('5000.00', invoice=registration_invoice)
        self.assertEqual(self.latest().status, Student.Status.ACTIVE)

    def test_paid_term_fees_never_clear_an_unsettled_registration(self):
        """The mirror image: ordinary school fees are not registration money."""
        self.register()
        student = self.latest()
        term_invoice = Invoice.objects.create(
            school=self.school, student=student, term='Second Term',
            total=Decimal('10000.00'), items=[{'label': 'Exam', 'amount': '10000.00'}],
        )
        self.settle('10000.00', invoice=term_invoice)
        self.assertEqual(self.latest().status, Student.Status.PENDING_PAYMENT)


class ConsequenceTests(RegistrationBillingTests):
    """The point of the gate: an unpaid student is not a student yet.

    These pin the visible effects so nobody "fixes" the status back to ACTIVE
    and silently reopens the hole.
    """

    def activate(self):
        from records.services import billing

        invoice = Invoice.objects.get(
            student=self.latest(), term='', source=Invoice.Source.ADMISSION,
        )
        invoice.paid = invoice.total
        invoice.save(update_fields=['paid'])
        payment = Payment.objects.create(
            school=self.school, invoice=invoice, amount=invoice.total,
            method=Payment.Method.CASH, status=Payment.Status.VERIFIED,
            reference=f'PAID-{invoice.id}',
        )
        billing.activate_student_if_fully_paid(self.latest())
        return payment

    def test_unpaid_student_is_absent_from_the_active_count(self):
        self.register()
        self.auth(self.admin)
        before = self.client.get(self.url('/students/stats/')).json()
        self.activate()
        after = self.client.get(self.url('/students/stats/')).json()
        self.assertEqual(after['active'], before['active'] + 1)

    def test_unpaid_student_is_not_listed_as_active(self):
        self.register()
        self.auth(self.admin)
        r = self.client.get(
            self.url('/students/'), {'status': Student.Status.ACTIVE}, format='json',
        )
        self.assertEqual(r.status_code, 200, r.content)
        ids = [row['id'] for row in r.json()['results']]
        self.assertNotIn(str(self.latest().public_id), ids)
        self.assertIn(str(self.student.public_id), ids)

    def test_paid_student_is_listed_as_active(self):
        self.register()
        self.activate()
        self.auth(self.admin)
        r = self.client.get(
            self.url('/students/'), {'status': Student.Status.ACTIVE}, format='json',
        )
        self.assertIn(str(self.latest().public_id), [row['id'] for row in r.json()['results']])

    def test_pending_student_is_still_visible_in_the_unfiltered_list(self):
        """The registrar must be able to see who is waiting on payment."""
        self.register()
        self.auth(self.admin)
        r = self.client.get(self.url('/students/'), format='json')
        self.assertEqual(r.status_code, 200, r.content)
        self.assertIn(str(self.latest().public_id), [row['id'] for row in r.json()['results']])


class ExistingStudentsUnaffectedTests(SecurityTestBase):
    def test_the_migration_does_not_relabel_existing_students(self):
        self.assertEqual(self.student.status, Student.Status.ACTIVE)
        self.assertEqual(self.other_student.status, Student.Status.ACTIVE)

    def test_pre_existing_active_students_keep_working(self):
        self.assertEqual(
            Student.objects.filter(
                school=self.school, status=Student.Status.ACTIVE,
            ).count(),
            1,
        )
