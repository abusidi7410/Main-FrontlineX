"""Class/section/session announcement targeting via active enrollments.

These tests pin the contract from the task: a notice aimed at a class must
reach exactly the students currently enrolled in it, and a class move on
the student's record must move them — no hand-maintained recipient list.
"""
from django.test import TestCase

from accounts.models import Notification, User
from records.models import Enrollment, Section, Student
from records.services import announcements as announcement_service
from records.services import enrollment as enrollment_service
from records.tests.base import SchoolTestCase


class AnnouncementTargetingTests(SchoolTestCase):
    def setUp(self):
        super().setUp()
        Notification.objects.all().delete()
        self.section_a = Section.objects.create(school=self.school, class_obj=self.jss2, name='A')
        self.section_b = Section.objects.create(school=self.school, class_obj=self.jss2, name='B')
        self.jss1_section = Section.objects.create(school=self.school, class_obj=self.jss1, name='A')

        self.student_a = self.make_student(first_name='Ada', admission_number='STUA')
        self.student_b = self.make_student(first_name='Bello', admission_number='STUB')
        enrollment_service.activate_enrollment(
            student=self.student_a, academic_session=self.session,
            class_obj=self.jss2, section=self.section_a,
        )
        enrollment_service.activate_enrollment(
            student=self.student_b, academic_session=self.session,
            class_obj=self.jss1, section=self.jss1_section,
        )
        self.user_a = User.objects.create_user(
            email='studenta@success.example', password='Strong-Pass-1!',
            first_name='Ada', last_name='Test', role=User.Role.STUDENT,
            school=self.school, student_profile=self.student_a,
        )
        self.user_b = User.objects.create_user(
            email='studentb@success.example', password='Strong-Pass-1!',
            first_name='Bello', last_name='Test', role=User.Role.STUDENT,
            school=self.school, student_profile=self.student_b,
        )
        self.parent_a = User.objects.create_user(
            email='parent_a@success.example', password='Strong-Pass-1!',
            first_name='Ada', last_name='Guardian', role=User.Role.PARENT,
            school=self.school,
        )
        self.parent_a.linked_students.add(self.student_a)

    def _targeted(self, **kwargs):
        return announcement_service.create(
            school=self.school, author=self.admin, title='JSS 2 only', body='Body',
            audience=['Students', 'Parents'], **kwargs,
        )

    def _titles(self, user):
        self.auth(user)
        response = self.client.get(self.url('/announcements/'))
        self.assertEqual(response.status_code, 200)
        return [row['title'] for row in response.data]

    def test_class_target_reaches_only_enrolled_students(self):
        self._targeted(target_class=self.jss2, target_academic_session=self.session)

        self.assertEqual(self._titles(self.user_a), ['JSS 2 only'])
        self.assertEqual(self._titles(self.user_b), [])

    def test_section_target_narrows_within_the_class(self):
        self._targeted(
            target_class=self.jss2, target_section=self.section_b,
            target_academic_session=self.session,
        )
        # Ada is in Section A, not B.
        self.assertEqual(self._titles(self.user_a), [])
        self.assertEqual(self._titles(self.parent_a), [])

    def test_transfer_moves_the_targeting(self):
        self._targeted(target_class=self.jss2, target_academic_session=self.session)
        self.assertEqual(self._titles(self.user_a), ['JSS 2 only'])

        enrollment_service.transfer_active_enrollment(
            self.student_a, self.session, self.jss1, self.jss1_section, actor=self.admin,
        )
        self.assertEqual(self._titles(self.user_a), [])

    def test_publish_notifies_only_the_targeted_students_and_parents(self):
        item = self._targeted(target_class=self.jss2, target_academic_session=self.session)

        recipients = set(
            Notification.objects.filter(dedupe_key=f'announcement:{item.pk}')
            .values_list('user_id', flat=True),
        )
        self.assertEqual(recipients, {self.user_a.pk, self.parent_a.pk})

    def test_other_schools_enrollments_never_targeted(self):
        other_session = self.other_school.sessions.first()
        other_student = Student.objects.create(
            school=self.other_school, admission_number='RVC/1', first_name='Rival',
            last_name='Kid', gender=Student.Gender.MALE, class_name='JSS 2',
        )
        other_user = User.objects.create_user(
            email='rival_student@rival.example', password='Strong-Pass-1!',
            first_name='Rival', last_name='Kid', role=User.Role.STUDENT,
            school=self.other_school, student_profile=other_student,
        )
        self._targeted(target_class=self.jss2, target_academic_session=self.session)

        Notification.objects.filter(user=other_user).delete()
        # Publishing again must not reach the other tenant.
        item = self._targeted(target_class=self.jss2, target_academic_session=self.session)
        self.assertFalse(
            Notification.objects.filter(user=other_user, dedupe_key=f'announcement:{item.pk}').exists(),
        )

    def test_cross_school_target_ids_are_rejected(self):
        from records.models import Level, SchoolClass
        other_level = Level.objects.create(
            school=self.other_school, code=Level.JUNIOR_SECONDARY,
            name='Junior Secondary', sort_order=30,
        )
        other_class = SchoolClass.objects.create(
            school=self.other_school, level=other_level, name='JSS 2', sort_order=31,
        )
        item_kwargs = dict(
            school=self.school, author=self.admin, title='Bad', body='Body', audience=['All'],
        )
        with self.assertRaises(Exception):
            announcement_service.create(
                **item_kwargs, target_class=other_class, target_academic_session=self.session,
            )

    def test_section_must_belong_to_the_target_class(self):
        with self.assertRaises(Exception):
            announcement_service.create(
                school=self.school, author=self.admin, title='Bad', body='Body',
                audience=['All'], target_class=self.jss1, target_section=self.section_a,
                target_academic_session=self.session,
            )

    def test_serialise_exposes_targets(self):
        item = self._targeted(target_class=self.jss2, target_academic_session=self.session)
        payload = announcement_service.serialise(item)
        self.assertEqual(payload['targetClassId'], str(self.jss2.pk))
        self.assertEqual(payload['targetAcademicSessionId'], str(self.session.pk))
