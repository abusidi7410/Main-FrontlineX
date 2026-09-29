"""A student with no attendance records is at 0%, not 100%.

`get_attendanceRate` used to return 100 when a student had zero records, so
every newly registered student showed flawless attendance and the students list
painted it green. Attendance has to start at zero and move only as days are
actually marked.
"""
from datetime import date, timedelta

from records.models import AttendanceRecord, Student
from records.serializers import StudentSerializer

from .test_security import SecurityTestBase


class AttendanceRateTests(SecurityTestBase):
    def rate_for(self, student):
        # The list endpoint annotates; the detail endpoint does not. Both paths
        # must agree, so each case is checked through both.
        annotated = StudentSerializer(
            Student.objects.for_roster().filter(pk=student.pk),
            many=True,
        ).data[0]['attendanceRate']
        plain = StudentSerializer(student).data['attendanceRate']
        self.assertEqual(annotated, plain)
        return plain

    def mark(self, student, statuses):
        today = date(2026, 1, 5)
        AttendanceRecord.objects.all().delete()
        for index, status in enumerate(statuses):
            AttendanceRecord.objects.create(
                school=self.school, student=student, class_name='JSS 1',
                date=today + timedelta(days=index), status=status,
            )

    def test_a_brand_new_student_is_at_zero(self):
        self.assertEqual(self.rate_for(self.student), 0)

    def test_a_brand_new_student_is_not_reported_as_perfect(self):
        """The regression this pins: 100 here made every school look flawless."""
        self.assertNotEqual(self.rate_for(self.student), 100)

    def test_registering_a_student_reports_zero(self):
        self.auth(self.secretary)
        r = self.client.post(self.url('/students/'), {
            'firstName': 'Ada', 'lastName': 'Nwosu', 'gender': 'female',
            'className': 'JSS 1', 'guardianName': 'Mrs N',
            'guardianPhone': '08012345678', 'dateOfBirth': '2014-05-02',
        }, format='json')
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(r.json()['attendanceRate'], 0)

    def test_one_present_day_is_100(self):
        self.mark(self.student, [AttendanceRecord.Status.PRESENT])
        self.assertEqual(self.rate_for(self.student), 100)

    def test_the_rate_moves_as_days_are_marked(self):
        self.mark(self.student, [AttendanceRecord.Status.PRESENT])
        self.assertEqual(self.rate_for(self.student), 100)
        self.mark(
            self.student,
            [AttendanceRecord.Status.PRESENT, AttendanceRecord.Status.ABSENT],
        )
        self.assertEqual(self.rate_for(self.student), 50)
        self.mark(
            self.student,
            [AttendanceRecord.Status.PRESENT, AttendanceRecord.Status.ABSENT,
             AttendanceRecord.Status.PRESENT],
        )
        self.assertEqual(self.rate_for(self.student), 66.7)

    def test_a_single_absence_drops_it_below_a_clean_record(self):
        self.mark(
            self.student,
            [AttendanceRecord.Status.PRESENT] * 9 + [AttendanceRecord.Status.ABSENT],
        )
        self.assertEqual(self.rate_for(self.student), 90)

    def test_late_counts_as_attending(self):
        self.mark(
            self.student,
            [AttendanceRecord.Status.PRESENT, AttendanceRecord.Status.LATE],
        )
        self.assertEqual(self.rate_for(self.student), 100)

    def test_excused_is_not_counted_as_attending(self):
        self.mark(
            self.student,
            [AttendanceRecord.Status.PRESENT, AttendanceRecord.Status.EXCUSED],
        )
        self.assertEqual(self.rate_for(self.student), 50)

    def test_all_absent_is_zero(self):
        self.mark(
            self.student,
            [AttendanceRecord.Status.ABSENT, AttendanceRecord.Status.ABSENT],
        )
        self.assertEqual(self.rate_for(self.student), 0)

    def test_a_new_students_record_does_not_leak_into_another(self):
        self.mark(self.student, [AttendanceRecord.Status.PRESENT])
        other = Student.objects.create(
            school=self.school, admission_number='SUA/JSS/2026/000200',
            first_name='Bisi', last_name='Ade', gender='female', class_name='JSS 1',
        )
        self.assertEqual(self.rate_for(self.student), 100)
        self.assertEqual(self.rate_for(other), 0)
