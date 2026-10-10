"""Query-count guards for the endpoints Phase 1 touched.

Without these, the N+1 fixes in `Student.for_roster()` / `_student_queryset()`
can silently regress back into per-student queries. `assertNumQueries` pins the
cost so a future change that reintroduces a loop fails loudly.
"""
from django.test.utils import CaptureQueriesContext

from records.models import AttendanceRecord, Invoice, Payment, Student

from .test_security import SecurityTestBase


class StudentListQueryCountTests(SecurityTestBase):
    def _seed(self, count):
        for i in range(count):
            student = Student.objects.create(
                school=self.school, admission_number=f'QC-{i:04d}',
                first_name=f'Q{i}', last_name='Count', gender='male',
                class_name='JSS 1', arm='A', status=Student.Status.ACTIVE,
            )
            AttendanceRecord.objects.create(
                school=self.school, student=student, class_name='JSS 1',
                date='2026-09-01', status=AttendanceRecord.Status.PRESENT,
            )
            Invoice.objects.create(
                school=self.school, student=student, term='First Term',
                total=1000, paid=400,
            )

    def test_student_list_query_count_does_not_grow_with_page_size(self):
        """A 20-student page and a full page cost the same queries."""
        self._seed(60)
        # Newest admission first, so this one is guaranteed to be on page one
        # and carries no invoice of its own.
        Student.objects.create(
            school=self.school, admission_number='QC-NOINVOICE',
            first_name='No', last_name='Invoice', gender='female',
            class_name='JSS 1', arm='A', status=Student.Status.ACTIVE,
        )
        self.auth(self.admin)

        with CaptureQueriesContext(self.connection) as small:
            resp = self.client.get(self.url('/students/'), {'pageSize': 20})
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(len(resp.json()['results']), 20)

        with CaptureQueriesContext(self.connection) as large:
            resp = self.client.get(self.url('/students/'), {'pageSize': 100})
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(len(resp.json()['results']), 62)

        # The serialized data must still be correct with the annotations.
        # The list is ordered newest-admission-first, so rows are looked up by
        # admission number rather than by position.
        rows = {row['admissionNumber']: row for row in resp.json()['results']}
        seeded = rows['QC-0000']
        self.assertEqual(seeded['attendanceRate'], 100)
        self.assertEqual(seeded['outstandingFees'], 600.0)
        # A student with no invoices reports zero outstanding, not None.
        self.assertEqual(rows['QC-NOINVOICE']['outstandingFees'], 0.0)

        # Constant, not linear, in page size. `count()` runs before the slice.
        self.assertEqual(
            len(small.captured_queries), len(large.captured_queries),
            'query count grew with page size (N+1 regression)',
        )

    def test_student_detail_query_count_is_constant(self):
        self._seed(5)
        self.auth(self.admin)
        with CaptureQueriesContext(self.connection) as ctx:
            resp = self.client.get(self.url(f'/students/{self.student.public_id}/'))
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertLessEqual(
            len(ctx.captured_queries), 4,
            f'detail view issued {len(ctx.captured_queries)} queries',
        )

    def test_roster_query_count_does_not_grow_with_class_size(self):
        """The register must stay a fixed number of queries, whatever the class size.

        The daily register resolves the class, its sections, the enrollment
        roster, today's existing marks and the class teacher — five lookups plus
        the current session, all constant. The point of this test is that the
        count does not move as students are added, so it measures at two sizes
        and compares rather than trusting a single magic number.
        """
        from records.models import Enrollment

        def enrol(start, count):
            for i in range(start, start + count):
                student = Student.objects.create(
                    school=self.school, admission_number=f'RO-{i:04d}',
                    first_name=f'R{i}', last_name='Roster', gender='male',
                    class_name='JSS 1', arm='A', status=Student.Status.ACTIVE,
                )
                Enrollment.objects.create(
                    school=self.school, student=student, academic_session=self.session,
                    class_obj=self.jss1, section=self.section_a,
                    status=Enrollment.Status.ACTIVE,
                )

        self.auth(self.teacher)

        enrol(0, 5)
        with CaptureQueriesContext(self.connection) as ctx:
            small = self.roster(className='JSS 1')
        self.assertEqual(small.status_code, 200, small.content)
        small_count = len(ctx.captured_queries)

        enrol(5, 40)
        with CaptureQueriesContext(self.connection) as ctx:
            large = self.roster(className='JSS 1')
        self.assertEqual(large.status_code, 200, large.content)
        self.assertEqual(len(large.json()['students']), 46)
        large_count = len(ctx.captured_queries)

        self.assertEqual(
            small_count, large_count,
            f'roster queries grew from {small_count} to {large_count} as the class filled',
        )
        self.assertLessEqual(
            large_count, 6,
            f'roster issued {large_count} queries',
        )

    def test_student_stats_aggregates_in_the_database(self):
        self._seed(5)
        self.auth(self.admin)
        with CaptureQueriesContext(self.connection) as ctx:
            resp = self.client.get(self.url('/students/stats/'))
        self.assertEqual(resp.status_code, 200, resp.content)
        # 5 invoices x 600 outstanding each.
        self.assertEqual(resp.json()['outstandingFees'], 3000.0)
        self.assertLessEqual(
            len(ctx.captured_queries), 6,
            f'stats issued {len(ctx.captured_queries)} queries',
        )

    def test_paginated_invoice_and_payment_lists_have_constant_query_counts(self):
        for index in range(40):
            invoice = Invoice.objects.create(
                school=self.school,
                student=self.student,
                term=f'Query-count term {index}',
                total=1000,
                paid=0,
            )
            Payment.objects.create(
                school=self.school,
                invoice=invoice,
                amount=100,
                method=Payment.Method.CASH,
                status=Payment.Status.PENDING,
                reference=f'QC-PAY-{index:04d}',
                recorded_by=self.admin,
            )

        self.auth(self.admin)
        counts = {}
        for endpoint in ('/invoices/', '/payments/'):
            for page_size in (10, 40):
                with CaptureQueriesContext(self.connection) as ctx:
                    response = self.client.get(
                        self.url(endpoint), {'page': 1, 'pageSize': page_size},
                    )
                self.assertEqual(response.status_code, 200, response.content)
                payload = response.json()
                self.assertEqual(len(payload['results']), page_size)
                self.assertEqual(payload['count'], 40)
                counts[(endpoint, page_size)] = len(ctx.captured_queries)

        self.assertEqual(
            counts[('/invoices/', 10)],
            counts[('/invoices/', 40)],
            'invoice list query count grew with page size',
        )
        self.assertEqual(
            counts[('/payments/', 10)],
            counts[('/payments/', 40)],
            'payment list query count grew with page size',
        )

    def test_finance_summary_uses_fixed_queries_and_returns_bounded_recent_lists(self):
        for index in range(20):
            invoice = Invoice.objects.create(
                school=self.school,
                student=self.student,
                term=self.school.current_term,
                total=1000,
                paid=400,
            )
            Payment.objects.create(
                school=self.school,
                invoice=invoice,
                amount=100,
                method=Payment.Method.CASH,
                status=Payment.Status.VERIFIED,
                reference=f'SUM-PAY-{index:04d}',
                recorded_by=self.admin,
            )
        Invoice.objects.create(
            school=self.school,
            student=self.student,
            term='',
            source=Invoice.Source.ADMISSION,
            total=5000,
            paid=0,
            items=[{'label': 'Registration fee', 'feeType': 'registration', 'amount': '5000'}],
        )

        self.auth(self.admin)
        with CaptureQueriesContext(self.connection) as ctx:
            response = self.client.get(self.url('/finance/summary/'))

        self.assertEqual(response.status_code, 200, response.content)
        payload = response.json()
        self.assertEqual(payload['outstanding'], 17000.0)
        self.assertEqual(payload['paid'], 8000.0)
        self.assertEqual(payload['pendingPaymentCount'], 0)
        self.assertEqual(len(payload['recentInvoices']), 3)
        self.assertIn(
            'registration',
            {
                item.get('feeType')
                for invoice in payload['recentInvoices']
                for item in invoice['items']
            },
        )
        self.assertEqual(len(payload['recentPayments']), 6)
        self.assertLessEqual(
            len(ctx.captured_queries), 7,
            f'finance summary issued {len(ctx.captured_queries)} queries',
        )

    @property
    def connection(self):
        from django.db import connection
        return connection
