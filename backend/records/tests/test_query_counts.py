"""Query-count guards for the endpoints Phase 1 touched.

Without these, the N+1 fixes in `Student.for_roster()` / `_student_queryset()`
can silently regress back into per-student queries. `assertNumQueries` pins the
cost so a future change that reintroduces a loop fails loudly.
"""
from django.test.utils import CaptureQueriesContext

from records.models import AttendanceRecord, Invoice, Student

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
        """A 20-student page and a 60-student page cost the same queries."""
        self._seed(60)
        self.auth(self.admin)

        with CaptureQueriesContext(self.connection) as small:
            resp = self.client.get(self.url('/students/'), {'pageSize': 20})
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(len(resp.json()['results']), 20)

        with CaptureQueriesContext(self.connection) as large:
            resp = self.client.get(self.url('/students/'), {'pageSize': 60})
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(len(resp.json()['results']), 60)

        # The serialized data must still be correct with the annotations.
        # Ordering is (last_name, first_name) so index 0 is not necessarily a
        # seeded student; look the seeded one up by admission number.
        rows = {row['admissionNumber']: row for row in resp.json()['results']}
        seeded = rows['QC-0000']
        self.assertEqual(seeded['attendanceRate'], 100)
        self.assertEqual(seeded['outstandingFees'], 600.0)
        # A student with no invoices reports zero outstanding, not None.
        self.assertEqual(rows['SUA/JSS/2026/000100']['outstandingFees'], 0.0)

        # Constant, not linear, in page size. `count()` runs before the slice.
        self.assertEqual(
            len(small.captured_queries), len(large.captured_queries),
            'query count grew with page size (N+1 regression)',
        )

    def test_student_detail_query_count_is_constant(self):
        self._seed(5)
        self.auth(self.admin)
        with CaptureQueriesContext(self.connection) as ctx:
            resp = self.client.get(self.url(f'/students/{self.student.id}/'))
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertLessEqual(
            len(ctx.captured_queries), 4,
            f'detail view issued {len(ctx.captured_queries)} queries',
        )

    def test_roster_query_count_does_not_grow_with_class_size(self):
        from records.models import Enrollment

        for i in range(40):
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
        with CaptureQueriesContext(self.connection) as ctx:
            resp = self.roster(className='JSS 1')
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(len(resp.json()['students']), 41)
        self.assertLessEqual(
            len(ctx.captured_queries), 4,
            f'roster issued {len(ctx.captured_queries)} queries',
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

    @property
    def connection(self):
        from django.db import connection
        return connection
