"""The Phase 1 backfill migration (0003) must not lose existing students.

Attendance rosters now read `Enrollment` instead of `Student.class_name`. If
this migration failed, every student a real school already had would silently
disappear from their attendance roster — a severe data-visible regression that
no other test would catch. So the migration is exercised directly here.
"""
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase

from accounts.models import User
from records.models import Enrollment, Level, SchoolClass, Section, Student
from schools.models import School


class BackfillMigrationTests(TransactionTestCase):
    """Migrate back to the pre-backfill state, seed legacy data, migrate forward."""

    migrate_from = [('records', '0002_admission_foundation')]
    migrate_to = [('records', '0003_backfill_class_enrollments')]

    def _migrate(self, targets):
        executor = MigrationExecutor(connection)
        executor.loader.build_graph()
        executor.migrate(targets)
        return executor.loader.project_state(targets).apps

    def setUp(self):
        self.old_apps = self._migrate(self.migrate_from)

    def tearDown(self):
        # Re-apply the latest migration so the schema matches the rest of the
        # suite; unapplying a leaf node is not a valid target.
        executor = MigrationExecutor(connection)
        executor.loader.build_graph()
        executor.migrate(self.migrate_to)

    def test_legacy_students_gain_class_section_and_enrollment(self):
        SchoolModel = self.old_apps.get_model('schools', 'School')
        StudentModel = self.old_apps.get_model('records', 'Student')

        school = SchoolModel.objects.create(
            name='Legacy School', slug='legacy', code='LGC',
            address='1 Old Road', state='Kano', lga='Kano',
            phone='1', email='legacy@example.com',
            current_session='2026/2027', current_term='First Term',
        )
        for number, (klass, arm) in enumerate(
            [('JSS 1', 'A'), ('JSS 1', 'B'), ('SS 1', '')], start=1,
        ):
            StudentModel.objects.create(
                school_id=school.id, admission_number=f'OLD-{number}',
                first_name=f'Old{number}', last_name='Student', gender='male',
                class_name=klass, arm=arm, status='active',
            )

        school_id = school.pk

        self._migrate(self.migrate_to)

        self.assertEqual(Student.objects.filter(school_id=school_id).count(), 3)
        # Levels, class and sections were created for the legacy names.
        self.assertTrue(SchoolClass.objects.filter(school_id=school_id, name='JSS 1').exists())
        self.assertTrue(SchoolClass.objects.filter(school_id=school_id, name='SS 1').exists())
        self.assertEqual(Section.objects.filter(school_id=school_id, name='A').count(), 1)
        # Every legacy student is now on a roster.
        self.assertEqual(
            Enrollment.objects.filter(school_id=school_id, status=Enrollment.Status.ACTIVE,
            ).count(), 3,
        )
        jss1 = SchoolClass.objects.get(school_id=school_id, name='JSS 1')
        self.assertEqual(
            Enrollment.objects.filter(school_id=school_id, class_obj=jss1).count(), 2,
        )
        # Student rows themselves are untouched.
        for number in (1, 2, 3):
            student = Student.objects.get(admission_number=f'OLD-{number}')
            self.assertTrue(student.class_name)

    def test_migration_is_idempotent(self):
        SchoolModel = self.old_apps.get_model('schools', 'School')
        StudentModel = self.old_apps.get_model('records', 'Student')
        school = SchoolModel.objects.create(
            name='Idem School', slug='idem', code='IDM',
            address='1 Idem Road', state='Kano', lga='Kano',
            phone='1', email='idem@example.com', current_session='2026/2027',
        )
        StudentModel.objects.create(
            school_id=school.id, admission_number='IDM-1', first_name='A',
            last_name='B', gender='male', class_name='JSS 1', arm='A', status='active',
        )

        school_id = school.pk

        self._migrate(self.migrate_to)
        first = Enrollment.objects.filter(school_id=school_id).count()
        self.assertEqual(first, 1)
        # Re-running must not create a second active enrollment (the partial
        # unique index would raise IntegrityError).
        school_id = school.pk
        self._migrate(self.migrate_to)
        self.assertEqual(Enrollment.objects.filter(school_id=school_id).count(), 1)

    def test_school_without_a_usable_session_is_skipped_safely(self):
        SchoolModel = self.old_apps.get_model('schools', 'School')
        StudentModel = self.old_apps.get_model('records', 'Student')
        school = SchoolModel.objects.create(
            name='No Session', slug='no-session', code='NOS',
            address='1 None Road', state='Kano', lga='Kano',
            phone='1', email='nos@example.com', current_session='',
        )
        StudentModel.objects.create(
            school_id=school.id, admission_number='NOS-1', first_name='A',
            last_name='B', gender='male', class_name='JSS 1', arm='A', status='active',
        )
        # Must not raise; the student is left for an operator to enroll.
        school_id = school.pk
        self._migrate(self.migrate_to)
        self.assertEqual(Enrollment.objects.filter(school_id=school_id).count(), 0)
        self.assertTrue(Student.objects.filter(school_id=school_id).exists())

    def test_unrecognised_class_name_does_not_lose_the_student(self):
        SchoolModel = self.old_apps.get_model('schools', 'School')
        StudentModel = self.old_apps.get_model('records', 'Student')
        school = SchoolModel.objects.create(
            name='Odd School', slug='odd', code='ODD',
            address='1 Odd Road', state='Kano', lga='Kano',
            phone='1', email='odd@example.com', current_session='2026/2027',
        )
        StudentModel.objects.create(
            school_id=school.id, admission_number='ODD-1', first_name='A',
            last_name='B', gender='male', class_name='Band 7', arm='', status='active',
        )
        school_id = school.pk
        self._migrate(self.migrate_to)
        # The student survives and is enrolled under a real level.
        enrollment = Enrollment.objects.get(school_id=school_id)
        self.assertEqual(enrollment.class_obj.name, 'Band 7')
        self.assertTrue(enrollment.class_obj.level_id)

    def test_legacy_student_appears_in_the_roster_after_migration(self):
        """End-to-end: the whole point of the migration is a non-empty roster."""
        SchoolModel = self.old_apps.get_model('schools', 'School')
        StudentModel = self.old_apps.get_model('records', 'Student')
        school = SchoolModel.objects.create(
            name='Roster School', slug='roster', code='ROS',
            address='1 Ros Road', state='Kano', lga='Kano',
            phone='1', email='ros@example.com', current_session='2026/2027',
        )
        StudentModel.objects.create(
            school_id=school.id, admission_number='ROS-1', first_name='Roster',
            last_name='Student', gender='male', class_name='JSS 1', arm='A',
            status='active',
        )
        school_id = school.pk
        self._migrate(self.migrate_to)

        from accounts.models import User as RealUser
        from rest_framework.test import APIClient

        admin = RealUser.objects.create_user(
            email='ros-admin@example.com', password='Strong-Pass-1!',
            first_name='Ros', last_name='Admin', role=RealUser.Role.SCHOOL_ADMIN,
            school_id=school.id, is_active=True,
        )
        client = APIClient()
        client.force_authenticate(admin)
        resp = client.get('/api/v1/attendance/roster/', {'className': 'JSS 1'})
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(
            [row['firstName'] for row in resp.json()['students']], ['Roster'],
        )
