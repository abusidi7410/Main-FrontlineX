from decimal import Decimal

from records.models import (
    AcademicSession,
    AttendanceRecord,
    Enrollment,
    LessonPlan,
    PromotionPolicy,
    ResultEntry,
    ResultSheet,
    SchoolClass,
    StaffMember,
    Student,
)
from records.tests.test_security import SecurityTestBase


class LessonPlanApiTests(SecurityTestBase):
    def setUp(self):
        super().setUp()
        self.teacher_staff = StaffMember.objects.create(
            school=self.school,
            full_name='Teacher Test',
            email=self.teacher.email,
            role='teacher',
            subjects=['Mathematics'],
            classes=['JSS 1'],
            status=StaffMember.Status.ACTIVE,
        )
        self.teacher.staff_profile = self.teacher_staff
        self.teacher.save(update_fields=['staff_profile'])
        self.payload = {
            'subject': 'Mathematics',
            'className': 'JSS 1',
            'topic': 'Fractions',
            'durationMinutes': 40,
            'objectives': 'Compare fractions with unlike denominators.',
            'previousKnowledge': 'Equivalent fractions',
        }

    def test_teacher_can_create_edit_list_and_delete_an_assigned_plan(self):
        self.auth(self.teacher)
        created = self.client.post(self.url('/lesson-plans/'), self.payload, format='json')
        self.assertEqual(created.status_code, 201, created.data)
        self.assertEqual(created.data['session'], self.session.name)
        self.assertEqual(created.data['term'], self.school.current_term)
        self.assertEqual(created.data['durationMinutes'], 40)

        plan_id = created.data['id']
        listed = self.client.get(self.url('/lesson-plans/'))
        self.assertEqual(listed.status_code, 200)
        self.assertEqual(len(listed.data), 1)

        updated = self.client.patch(
            self.url(f'/lesson-plans/{plan_id}/'),
            {'topic': 'Adding fractions'},
            format='json',
        )
        self.assertEqual(updated.status_code, 200, updated.data)
        self.assertEqual(updated.data['topic'], 'Adding fractions')
        self.assertEqual(updated.data['className'], 'JSS 1')

        deleted = self.client.delete(self.url(f'/lesson-plans/{plan_id}/'))
        self.assertEqual(deleted.status_code, 204)
        self.assertFalse(LessonPlan.objects.filter(pk=plan_id).exists())

    def test_teacher_cannot_write_a_plan_for_an_unassigned_class(self):
        self.auth(self.teacher)
        response = self.client.post(
            self.url('/lesson-plans/'),
            {**self.payload, 'className': 'JSS 2'},
            format='json',
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(LessonPlan.objects.count(), 0)

    def test_invalid_subject_and_duration_are_rejected(self):
        self.auth(self.teacher)
        invalid_subject = self.client.post(
            self.url('/lesson-plans/'),
            {**self.payload, 'subject': 'Unconfigured subject'},
            format='json',
        )
        self.assertEqual(invalid_subject.status_code, 400)
        invalid_duration = self.client.post(
            self.url('/lesson-plans/'),
            {**self.payload, 'durationMinutes': 241},
            format='json',
        )
        self.assertEqual(invalid_duration.status_code, 400)
        self.assertEqual(LessonPlan.objects.count(), 0)

    def test_plan_is_scoped_to_the_callers_school(self):
        plan = LessonPlan.objects.create(
            school=self.other_school,
            class_obj=SchoolClass.objects.get(school=self.other_school),
            academic_session=AcademicSession.objects.get(school=self.other_school),
            term='First Term',
            subject='Mathematics',
            topic='Other school plan',
            objectives='Test objective',
        )
        self.auth(self.admin)
        response = self.client.get(self.url(f'/lesson-plans/{plan.pk}/'))
        self.assertEqual(response.status_code, 404)

    def test_school_admin_can_create_without_teacher_assignment(self):
        self.auth(self.admin)
        response = self.client.post(self.url('/lesson-plans/'), self.payload, format='json')
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(
            LessonPlan.objects.get(pk=response.data['id']).created_by,
            self.admin,
        )

    def test_academic_session_updates_are_used_by_new_lesson_plans(self):
        self.auth(self.admin)
        updated = self.client.patch(
            self.url('/academics/'),
            {'session': '2027/2028'},
            format='json',
        )
        self.assertEqual(updated.status_code, 200, updated.data)
        self.session.refresh_from_db()
        current = AcademicSession.objects.get(school=self.school, name='2027/2028')
        self.assertFalse(self.session.is_current)
        self.assertTrue(current.is_current)
        created = self.client.post(self.url('/lesson-plans/'), self.payload, format='json')
        self.assertEqual(created.status_code, 201, created.data)
        self.assertEqual(created.data['session'], '2027/2028')


class PromotionApiTests(SecurityTestBase):
    def setUp(self):
        super().setUp()
        self.sss2 = SchoolClass.objects.create(
            school=self.school, level=self.sss_level, name='SSS 2', sort_order=41,
        )
        self.sss3 = SchoolClass.objects.create(
            school=self.school, level=self.sss_level, name='SSS 3', sort_order=42,
        )
        self.section = self.section_a
        self.enrollment = Enrollment.objects.get(
            school=self.school,
            student=self.student,
            academic_session=self.session,
            class_obj=self.jss1,
            status=Enrollment.Status.ACTIVE,
        )

    def add_student(self, suffix, school_class=None):
        student = Student.objects.create(
            school=self.school,
            admission_number=f'SUA/JSS/2026/{suffix}',
            first_name='Test',
            last_name=f'Student {suffix}',
            gender=Student.Gender.FEMALE,
            class_name=(school_class or self.jss1).name,
            status=Student.Status.ACTIVE,
        )
        enrollment = Enrollment.objects.create(
            school=self.school,
            student=student,
            academic_session=self.session,
            class_obj=school_class or self.jss1,
            status=Enrollment.Status.ACTIVE,
        )
        return student, enrollment

    def record_performance(self, student, enrollment, *, score=80, attendance='present',
                           school_class=None):
        school_class = school_class or self.jss1
        sheet, _ = ResultSheet.objects.get_or_create(
            school=self.school,
            academic_session=self.session,
            class_obj=school_class,
            subject='Mathematics',
            assessment='Annual Examination',
            term='Third Term',
            defaults={
                'assessment_max': Decimal('100'),
                'status': ResultSheet.Status.PUBLISHED,
            },
        )
        ResultEntry.objects.create(
            sheet=sheet,
            student=student,
            enrollment=enrollment,
            score=Decimal(str(score)),
        )
        AttendanceRecord.objects.create(
            school=self.school,
            student=student,
            class_obj=school_class,
            class_name=school_class.name,
            date='2027-03-01',
            status=attendance,
        )

    def test_default_policy_is_explainable_and_saved_per_school(self):
        self.auth(self.admin)
        response = self.client.get(self.url('/promotion/policy/'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['promoteMinAverage'], 50)
        self.assertEqual(response.data['promoteMinAttendance'], 75)
        self.assertEqual(response.data['conditionalMaxFailedSubjects'], 2)
        self.assertTrue(PromotionPolicy.objects.filter(school=self.school).exists())

    def test_policy_rejects_conditional_threshold_above_promotion_threshold(self):
        self.auth(self.admin)
        response = self.client.patch(
            self.url('/promotion/policy/'),
            {'promoteMinAverage': 50, 'conditionalMinAverage': 60},
            format='json',
        )
        self.assertEqual(response.status_code, 400)

    def test_only_academic_read_roles_can_read_promotion_recommendations(self):
        self.auth(self.teacher)
        response = self.client.get(self.url('/promotion/classes/'))
        self.assertEqual(response.status_code, 403)

    def test_missing_results_or_attendance_require_review(self):
        self.auth(self.admin)
        response = self.client.get(self.url('/promotion/classes/JSS 1/'))
        self.assertEqual(response.status_code, 200, response.data)
        candidate = response.data['candidates'][0]
        self.assertEqual(candidate['suggested'], 'review')
        self.assertIsNone(candidate['average'])
        self.assertIsNone(candidate['attendanceRate'])
        self.assertTrue(candidate['incomplete'])

    def test_policy_drives_promote_conditional_repeat_recommendations(self):
        conditional, conditional_enrollment = self.add_student('000201')
        repeat, repeat_enrollment = self.add_student('000202')
        self.record_performance(self.student, self.enrollment, score=80)
        self.record_performance(conditional, conditional_enrollment, score=45)
        self.record_performance(repeat, repeat_enrollment, score=30, attendance='absent')

        self.auth(self.admin)
        response = self.client.get(self.url('/promotion/classes/JSS 1/'))
        self.assertEqual(response.status_code, 200, response.data)
        by_id = {candidate['studentId']: candidate for candidate in response.data['candidates']}
        self.assertEqual(by_id[str(self.student.pk)]['suggested'], 'promote')
        self.assertEqual(by_id[str(conditional.pk)]['suggested'], 'conditional')
        self.assertEqual(by_id[str(repeat.pk)]['suggested'], 'repeat')
        self.assertEqual(by_id[str(conditional.pk)]['failedSubjects'], 1)

    def test_apply_promote_creates_next_session_enrollment_and_preserves_history(self):
        self.record_performance(self.student, self.enrollment)
        self.auth(self.admin)
        response = self.client.post(
            self.url('/promotion/classes/JSS 1/apply/'),
            {'decisions': {str(self.student.pk): 'promote'}},
            format='json',
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['promoted'], 1)
        self.assertEqual(response.data['targetSession'], '2027/2028')
        self.enrollment.refresh_from_db()
        self.student.refresh_from_db()
        self.assertEqual(self.enrollment.status, Enrollment.Status.COMPLETED)
        self.assertEqual(self.student.class_name, 'JSS 2')
        next_session = AcademicSession.objects.get(school=self.school, name='2027/2028')
        self.assertTrue(Enrollment.objects.filter(
            student=self.student, academic_session=next_session,
            class_obj=self.jss2, status=Enrollment.Status.ACTIVE,
        ).exists())

    def test_apply_repeat_keeps_the_class_and_conditional_records_a_note(self):
        conditional, conditional_enrollment = self.add_student('000203')
        self.record_performance(self.student, self.enrollment, score=20)
        self.record_performance(conditional, conditional_enrollment, score=45)
        self.auth(self.admin)
        response = self.client.post(
            self.url('/promotion/classes/JSS 1/apply/'),
            {'decisions': {
                str(self.student.pk): 'repeat',
                str(conditional.pk): 'conditional',
            }},
            format='json',
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['repeated'], 1)
        self.assertEqual(response.data['conditional'], 1)
        next_session = AcademicSession.objects.get(school=self.school, name='2027/2028')
        repeated_enrollment = Enrollment.objects.get(
            student=self.student, academic_session=next_session,
            status=Enrollment.Status.ACTIVE,
        )
        conditional_enrollment = Enrollment.objects.get(
            student=conditional, academic_session=next_session,
            status=Enrollment.Status.ACTIVE,
        )
        self.assertEqual(repeated_enrollment.class_obj, self.jss1)
        self.assertIn('Promoted with conditions', conditional_enrollment.review_note)
        student_detail = self.client.get(self.url(f'/students/{conditional.pk}/'))
        self.assertEqual(student_detail.status_code, 200)
        self.assertTrue(any(
            history['reviewNote'].startswith('Promoted with conditions')
            for history in student_detail.data['enrollmentHistory']
        ))

    def test_review_decision_leaves_the_student_in_the_current_session(self):
        self.auth(self.admin)
        response = self.client.post(
            self.url('/promotion/classes/JSS 1/apply/'),
            {'decisions': {str(self.student.pk): 'review'}},
            format='json',
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['underReview'], 1)
        self.enrollment.refresh_from_db()
        self.assertEqual(self.enrollment.status, Enrollment.Status.ACTIVE)

    def test_final_class_promote_decision_graduates_without_a_new_enrollment(self):
        student, enrollment = self.add_student('000204', self.sss3)
        self.record_performance(student, enrollment, school_class=self.sss3)
        self.auth(self.admin)
        response = self.client.post(
            self.url('/promotion/classes/SSS 3/apply/'),
            {'decisions': {str(student.pk): 'promote'}},
            format='json',
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['graduated'], 1)
        student.refresh_from_db()
        enrollment.refresh_from_db()
        self.assertEqual(student.status, Student.Status.GRADUATED)
        self.assertEqual(enrollment.status, Enrollment.Status.COMPLETED)
        self.assertFalse(Enrollment.objects.filter(
            student=student,
            academic_session__name='2027/2028',
            status=Enrollment.Status.ACTIVE,
        ).exists())

    def test_apply_rejects_stale_or_invalid_decision_sets_without_changes(self):
        self.auth(self.admin)
        missing_student = self.client.post(
            self.url('/promotion/classes/JSS 1/apply/'),
            {'decisions': {}},
            format='json',
        )
        invalid_choice = self.client.post(
            self.url('/promotion/classes/JSS 1/apply/'),
            {'decisions': {str(self.student.pk): 'skip'}},
            format='json',
        )
        self.assertEqual(missing_student.status_code, 400)
        self.assertEqual(invalid_choice.status_code, 400)
        self.enrollment.refresh_from_db()
        self.assertEqual(self.enrollment.status, Enrollment.Status.ACTIVE)
        self.assertFalse(AcademicSession.objects.filter(school=self.school, name='2027/2028').exists())

    def test_class_and_student_data_are_school_scoped(self):
        other_class = SchoolClass.objects.get(school=self.other_school)
        other_class.name = 'Rival Class'
        other_class.save(update_fields=['name'])
        self.auth(self.admin)
        response = self.client.get(self.url(f'/promotion/classes/{other_class.name}/'))
        self.assertEqual(response.status_code, 404)
        response = self.client.post(
            self.url(f'/promotion/classes/{other_class.name}/apply/'),
            {'decisions': {}},
            format='json',
        )
        self.assertEqual(response.status_code, 404)
