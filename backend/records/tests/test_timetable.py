"""Timetable module tests (spec §22).

Covers the three conflicts the spec names (teacher, class, room), cross-school
isolation, the role matrix, the bell schedule, and the query budget for the grid
-- the screen a teacher opens every morning.
"""
from __future__ import annotations

from django.db import IntegrityError, connection, transaction
from django.test.utils import CaptureQueriesContext

from records.models import (
    Enrollment,
    StaffMember,
    TimetableEntry,
    TimetablePeriod,
)
from records.services import ai_tools
from records.services import timetable as timetable_service
from records.tests.base import SchoolTestCase


class TimetableTestCase(SchoolTestCase):
    """A school with a seeded bell schedule and two staff members to place."""

    def setUp(self):
        super().setUp()
        self.periods = timetable_service.ensure_periods(self.school)
        # Grab the default bells by name so a change to the seeded day cannot
        # silently break these tests.
        self.p1 = TimetablePeriod.objects.get(school=self.school, name='P1')
        self.p2 = TimetablePeriod.objects.get(school=self.school, name='P2')
        self.break_period = TimetablePeriod.objects.get(school=self.school, name='Break')

        self.teacher_a = StaffMember.objects.create(
            school=self.school, full_name='Amoah Grace', email=self.teacher.email,
            role='teacher', subjects=['Mathematics'], classes=['JSS 1'],
        )
        self.teacher_b = StaffMember.objects.create(
            school=self.school, full_name='Bello Musa', email='bello@success.example',
            role='teacher', subjects=['English Language'], classes=['JSS 2'],
        )

    def entry_payload(self, **overrides):
        payload = {
            'weekday': 0,
            'periodId': str(self.p1.pk),
            'classId': str(self.jss1.pk),
            'subject': 'Mathematics',
            'teacherId': str(self.teacher_a.public_id),
            'room': 'Room 1',
        }
        payload.update(overrides)
        return payload

    def create_entry(self, **overrides):
        return timetable_service.create_entry(self.school, self.entry_payload(**overrides))

    # ── bell schedule ──────────────────────────────────────────────────────

    def test_ensure_periods_seeds_once_and_is_idempotent(self):
        again = timetable_service.ensure_periods(self.school)
        self.assertEqual(len(again), len(self.periods))
        self.assertEqual(
            TimetablePeriod.objects.filter(school=self.school).count(), len(self.periods),
        )

    def test_ensure_periods_leaves_a_custom_day_alone(self):
        """A school that has renamed its bells must not be re-seeded."""
        self.p1.name = 'Morning Assembly'
        self.p1.save()
        timetable_service.ensure_periods(self.school)
        self.assertFalse(
            TimetablePeriod.objects.filter(school=self.school, name='P1').exists()
        )
        self.assertEqual(
            TimetablePeriod.objects.filter(
                school=self.school, name='Morning Assembly',
            ).count(),
            1,
        )

    def test_period_cannot_end_before_it_starts(self):
        with self.assertRaises(Exception) as caught:
            timetable_service.create_period(self.school, {
                'name': 'Night', 'startTime': '18:00', 'endTime': '07:00',
            })
        self.assertIn('endTime', caught.exception.detail)

    def test_duplicate_period_name_refused(self):
        with self.assertRaises(Exception) as caught:
            timetable_service.create_period(self.school, {
                'name': 'P1', 'startTime': '15:00', 'endTime': '15:40',
            })
        self.assertIn('name', caught.exception.detail)

    def test_overlapping_lesson_period_refused_on_create(self):
        with self.assertRaises(Exception) as caught:
            timetable_service.create_period(self.school, {
                'name': 'Overlap', 'startTime': '08:20', 'endTime': '09:00',
            })
        self.assertIn('startTime', caught.exception.detail)

    def test_overlapping_lesson_period_refused_on_update(self):
        with self.assertRaises(Exception) as caught:
            timetable_service.update_period(
                self.school, self.p2, {'startTime': '08:20', 'endTime': '09:00'},
            )
        self.assertIn('startTime', caught.exception.detail)

    def test_break_may_sit_inside_a_lesson_period(self):
        """Breaks are dividers, so overlapping a lesson window is intentional."""
        created = timetable_service.create_period(self.school, {
            'name': 'Chapel', 'startTime': '09:30', 'endTime': '09:50', 'isBreak': True,
        })
        self.assertTrue(created.is_break)

    def test_lesson_cannot_be_placed_in_a_break(self):
        with self.assertRaises(Exception) as caught:
            self.create_entry(periodId=str(self.break_period.pk))
        self.assertIn('periodId', caught.exception.detail)

    def test_in_use_period_cannot_be_deleted(self):
        self.create_entry()
        self.auth(self.admin)
        response = self.client.delete(self.url('/timetable/periods/%s/' % self.p1.pk))
        self.assertEqual(response.status_code, 400)
        self.assertIn('still holds 1 lesson', str(response.data['fieldErrors']['name']))

    def test_unused_period_can_be_deleted(self):
        self.auth(self.admin)
        response = self.client.delete(self.url('/timetable/periods/%s/' % self.p2.pk))
        self.assertEqual(response.status_code, 204)
        self.assertFalse(TimetablePeriod.objects.filter(pk=self.p2.pk).exists())

    # ── the three conflicts ────────────────────────────────────────────────

    def test_class_conflict_refused_with_a_readable_message(self):
        self.create_entry()
        with self.assertRaises(Exception) as caught:
            self.create_entry(subject='English Language', teacherId=str(self.teacher_b.public_id))
        message = str(caught.exception.detail['classId'])
        self.assertIn('JSS 1', message)
        self.assertIn('P1', message)
        self.assertIn('Monday', message)

    def test_teacher_conflict_refused_with_a_readable_message(self):
        self.create_entry()
        with self.assertRaises(Exception) as caught:
            # Same teacher, different class, same period.
            self.create_entry(classId=str(self.jss2.pk))
        message = str(caught.exception.detail['teacherId'])
        self.assertIn('Amoah Grace', message)
        self.assertIn('JSS 1', message)

    def test_room_conflict_refused_with_a_readable_message(self):
        self.create_entry()
        with self.assertRaises(Exception) as caught:
            self.create_entry(
classId=str(self.jss2.pk), teacherId=str(self.teacher_b.public_id),
                subject='English',
            )
        message = str(caught.exception.detail['room'])
        self.assertIn('Room 1', message)
        self.assertIn('JSS 1', message)

    def test_same_slot_on_a_different_day_is_fine(self):
        self.create_entry(weekday=0)
        second = self.create_entry(weekday=1)
        self.assertEqual(second.weekday, 1)
        self.assertEqual(TimetableEntry.objects.count(), 2)

    def test_lesson_without_teacher_or_room_does_not_collide_with_itself(self):
        """Partial constraints: an unassigned lesson is not a self-conflict."""
        first = self.create_entry(teacherId='', room='')
        second = self.create_entry(
            classId=str(self.jss2.pk), teacherId='', room='', subject='Basic Science',
        )
        self.assertNotEqual(first.pk, second.pk)
        self.assertEqual(TimetableEntry.objects.count(), 2)

    def test_room_frees_up_when_the_lesson_moves(self):
        entry = self.create_entry()
        timetable_service.update_entry(self.school, entry, self.entry_payload(room='Lab 1'))
        entry.refresh_from_db()
        self.assertEqual(entry.room, 'Lab 1')
        # Room 1 is now free in P1 on Monday.
        replacement = self.create_entry(
            classId=str(self.jss2.pk), teacherId=str(self.teacher_b.public_id), subject='English',
        )
        self.assertEqual(replacement.room, 'Room 1')

    def test_updating_an_entry_ignores_its_own_current_slot(self):
        """Re-saving a lesson unchanged must not conflict with itself."""
        entry = self.create_entry()
        again = timetable_service.update_entry(self.school, entry, self.entry_payload())
        self.assertEqual(again.pk, entry.pk)
        self.assertEqual(TimetableEntry.objects.count(), 1)

    def test_partial_update_keeps_the_fields_it_was_not_given(self):
        """The editor moves one lesson at a time and should not resend the row."""
        entry = self.create_entry()
        moved = timetable_service.update_entry(
            self.school, entry, {'subject': 'Basic Science'},
        )
        self.assertEqual(moved.subject, 'Basic Science')
        self.assertEqual(moved.weekday, 0)
        self.assertEqual(moved.period_id, self.p1.pk)
        self.assertEqual(moved.class_obj_id, self.jss1.pk)
        self.assertEqual(moved.teacher_id, self.teacher_a.pk)
        self.assertEqual(moved.room, 'Room 1')

    def test_partial_update_can_unassign_the_teacher(self):
        entry = self.create_entry()
        cleared = timetable_service.update_entry(self.school, entry, {'teacherId': ''})
        self.assertIsNone(cleared.teacher_id)
        # With the teacher gone, the slot is free for someone else.
        taken = self.create_entry(
            classId=str(self.jss2.pk), weekday=0, periodId=str(self.p1.pk),
            subject='English Language', teacherId=str(self.teacher_a.public_id), room='Room 5',
        )
        self.assertEqual(taken.teacher_id, self.teacher_a.pk)
        # The original lesson kept its slot; it just has nobody assigned now.
        self.assertEqual(TimetableEntry.objects.count(), 2)

    def test_database_rejects_a_double_booked_teacher_without_the_service(self):
        """The constraints, not just the service, are the real guarantee."""
        self.create_entry()
        duplicate = TimetableEntry(
            school=self.school, period=self.p1, class_obj=self.jss2,
            subject='English Language', teacher=self.teacher_a, room='Room 9', weekday=0,
        )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                duplicate.save()

    def test_database_rejects_a_double_booked_room(self):
        self.create_entry()
        duplicate = TimetableEntry(
            school=self.school, period=self.p1, class_obj=self.jss2,
            subject='English Language', teacher=self.teacher_b, room='Room 1', weekday=0,
        )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                duplicate.save()

    def test_database_rejects_a_double_booked_class(self):
        self.create_entry()
        duplicate = TimetableEntry(
            school=self.school, period=self.p1, class_obj=self.jss1,
            subject='Basic Science', teacher=self.teacher_b, room='Room 7', weekday=0,
        )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                duplicate.save()

    # ── validation ─────────────────────────────────────────────────────────

    def test_weekday_must_be_a_real_day(self):
        with self.assertRaises(Exception) as caught:
            self.create_entry(weekday=9)
        self.assertIn('weekday', caught.exception.detail)

    def test_weekday_must_be_a_number(self):
        with self.assertRaises(Exception) as caught:
            self.create_entry(weekday='Monday')
        self.assertIn('weekday', caught.exception.detail)

    def test_subject_is_required(self):
        with self.assertRaises(Exception) as caught:
            self.create_entry(subject='   ')
        self.assertIn('subject', caught.exception.detail)

    def test_unknown_period_class_or_teacher_is_refused(self):
        for field in ('periodId', 'classId', 'teacherId'):
            with self.subTest(field=field):
                with self.assertRaises(Exception) as caught:
                    self.create_entry(**{field: '999999'})
                self.assertIn(field, caught.exception.detail)

    def test_period_from_another_school_cannot_be_used(self):
        rival_period = TimetablePeriod.objects.create(
            school=self.other_school, name='P1', start_time='08:00', end_time='08:40',
        )
        with self.assertRaises(Exception) as caught:
            self.create_entry(periodId=str(rival_period.pk))
        self.assertIn('periodId', caught.exception.detail)

    def test_day_range_is_enforced_by_a_check_constraint(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                TimetableEntry.objects.create(
                    school=self.school, period=self.p1, class_obj=self.jss1,
                    subject='Mathematics', weekday=7,
                )


class TimetableApiTests(SchoolTestCase):
    def setUp(self):
        super().setUp()
        self.periods = timetable_service.ensure_periods(self.school)
        self.p1 = TimetablePeriod.objects.get(school=self.school, name='P1')
        self.p2 = TimetablePeriod.objects.get(school=self.school, name='P2')
        self.teacher_staff = StaffMember.objects.create(
            school=self.school, full_name='Amoah Grace', email=self.teacher.email,
            role='teacher', classes=['JSS 1'],
        )

    def post_entry(self, user, **overrides):
        payload = {
            'weekday': 0,
            'periodId': str(self.p1.pk),
            'classId': str(self.jss1.pk),
            'subject': 'Mathematics',
            'teacherId': str(self.teacher_staff.public_id),
            'room': 'Room 1',
        }
        payload.update(overrides)
        self.auth(user)
        return self.client.post(self.url('/timetable/entries/'), payload, format='json')

    def enrol(self, student, school_class):
        Enrollment.objects.create(
            school=self.school, student=student, academic_session=self.session,
            class_obj=school_class, status=Enrollment.Status.ACTIVE,
            activation_source=Enrollment.ActivationSource.MIGRATION,
        )

    def schedule_all_classes(self, weekday=0):
        for school_class in (self.jss1, self.jss2):
            timetable_service.create_entry(self.school, {
                'weekday': weekday, 'periodId': str(self.p1.pk),
                'classId': str(school_class.pk), 'subject': 'Mathematics', 'room': '',
            })

    # ── grid read ──────────────────────────────────────────────────────────

    def test_grid_returns_periods_entries_and_reference_data(self):
        timetable_service.create_entry(self.school, {
            'weekday': 0, 'periodId': str(self.p1.pk), 'classId': str(self.jss1.pk),
            'subject': 'Mathematics', 'teacherId': str(self.teacher_staff.public_id),
            'room': 'Room 1',
        })
        self.auth(self.admin)
        response = self.client.get(self.url('/timetable/'))
        self.assertEqual(response.status_code, 200)
        body = response.data
        self.assertTrue(body['periods'])
        self.assertEqual(body['days'], [0, 1, 2, 3, 4])
        self.assertEqual(len(body['entries']), 1)
        entry = body['entries'][0]
        # Legacy TimetableSlot keys, kept so existing consumers keep working.
        self.assertEqual(entry['className'], 'JSS 1')
        self.assertEqual(entry['subject'], 'Mathematics')
        self.assertEqual(entry['teacher'], 'Amoah Grace')
        self.assertEqual(entry['room'], 'Room 1')
        self.assertEqual(entry['period'], 'P1')
        # Editor keys.
        self.assertEqual(entry['weekday'], 0)
        self.assertEqual(entry['teacherId'], str(self.teacher_staff.public_id))
        self.assertIn('JSS 1', body['classIds'])
        self.assertIn('Mathematics', body['subjects'])
        self.assertIn('Amoah Grace', [t['name'] for t in body['teachers']])
        self.assertIn('Room 1', body['rooms'])

    def test_grid_reflects_the_school_calendar_weekend(self):
        self.school.attendance_weekend_days = [5, 6, 0]
        self.school.save()
        self.auth(self.admin)
        response = self.client.get(self.url('/timetable/'))
        self.assertEqual(response.data['days'], [1, 2, 3, 4])

    def test_grid_is_empty_before_anything_is_scheduled(self):
        self.auth(self.admin)
        response = self.client.get(self.url('/timetable/'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['entries'], [])
        self.assertTrue(response.data['periods'])

    def test_grid_can_be_narrowed_to_a_class(self):
        self.schedule_all_classes()
        self.auth(self.admin)
        response = self.client.get(
            self.url('/timetable/'), {'classId': str(self.jss2.pk)},
        )
        self.assertEqual(len(response.data['entries']), 1)
        self.assertEqual(response.data['entries'][0]['className'], 'JSS 2')

    def test_teacher_sees_their_own_week_by_default(self):
        timetable_service.create_entry(self.school, {
            'weekday': 0, 'periodId': str(self.p1.pk), 'classId': str(self.jss1.pk),
            'subject': 'Mathematics', 'teacherId': str(self.teacher_staff.public_id),
        })
        timetable_service.create_entry(self.school, {
            'weekday': 1, 'periodId': str(self.p2.pk), 'classId': str(self.jss2.pk),
            'subject': 'English Language', 'room': 'Room 2',
        })
        self.auth(self.teacher)
        response = self.client.get(self.url('/timetable/'))
        self.assertEqual(len(response.data['entries']), 1)
        self.assertEqual(response.data['entries'][0]['subject'], 'Mathematics')

    def test_student_sees_only_their_own_class(self):
        student = self.make_student(first_name='Ada', last_name='Nwosu')
        self.student_user.student_profile = student
        self.student_user.save()
        self.enrol(student, self.jss1)
        self.schedule_all_classes()
        self.auth(self.student_user)
        response = self.client.get(self.url('/timetable/'))
        self.assertEqual(len(response.data['entries']), 1)
        self.assertEqual(response.data['entries'][0]['className'], 'JSS 1')

    def test_student_cannot_widen_the_scope_to_another_class(self):
        student = self.make_student()
        self.student_user.student_profile = student
        self.student_user.save()
        self.auth(self.student_user)
        response = self.client.get(self.url('/timetable/'), {'classId': str(self.jss2.pk)})
        self.assertEqual(response.status_code, 400)

    def test_parent_sees_only_the_classes_of_their_children(self):
        child = self.make_student()
        self.enrol(child, self.jss2)
        self.parent.linked_students.add(child)
        self.schedule_all_classes()
        self.auth(self.parent)
        response = self.client.get(self.url('/timetable/'))
        self.assertEqual(len(response.data['entries']), 1)
        self.assertEqual(response.data['entries'][0]['className'], 'JSS 2')

    def test_one_school_cannot_read_another_schools_entry(self):
        self.post_entry(self.admin)
        entry = TimetableEntry.objects.get()
        self.auth(self.other_admin)
        response = self.client.get(self.url('/timetable/entries/%s/' % entry.pk))
        self.assertEqual(response.status_code, 404)

    # ── permissions ────────────────────────────────────────────────────────

    def test_school_staff_can_read_the_timetable(self):
        for user in (self.admin, self.principal, self.teacher, self.accountant):
            with self.subTest(role=user.role):
                self.auth(user)
                response = self.client.get(self.url('/timetable/'))
                self.assertEqual(response.status_code, 200)

    def test_only_the_school_admin_can_build_the_timetable(self):
        self.post_entry(self.admin)
        for user in (self.principal, self.teacher, self.accountant, self.secretary):
            with self.subTest(role=user.role):
                response = self.post_entry(
                    user, weekday=1, periodId=str(self.p2.pk),
                )
                self.assertEqual(response.status_code, 403)
        self.assertEqual(TimetableEntry.objects.count(), 1)

    def test_pupil_and_parent_cannot_write(self):
        for user in (self.student_user, self.parent):
            with self.subTest(role=user.role):
                response = self.post_entry(
                    user, weekday=1, periodId=str(self.p2.pk),
                )
                self.assertEqual(response.status_code, 403)

    def test_anonymous_cannot_read_the_timetable(self):
        response = self.client.get(self.url('/timetable/'))
        self.assertEqual(response.status_code, 401)

    # ── writes over HTTP ───────────────────────────────────────────────────

    def test_admin_can_create_update_and_delete_a_lesson(self):
        created = self.post_entry(self.admin)
        self.assertEqual(created.status_code, 201)
        entry_id = created.data['id']

        self.auth(self.admin)
        updated = self.client.patch(
            self.url('/timetable/entries/%s/' % entry_id),
            {'subject': 'Further Mathematics', 'room': 'Lab 2'},
            format='json',
        )
        self.assertEqual(updated.status_code, 200)
        self.assertEqual(updated.data['subject'], 'Further Mathematics')
        self.assertEqual(updated.data['room'], 'Lab 2')

        deleted = self.client.delete(self.url('/timetable/entries/%s/' % entry_id))
        self.assertEqual(deleted.status_code, 204)
        self.assertFalse(TimetableEntry.objects.filter(pk=entry_id).exists())

    def test_conflict_is_reported_to_the_caller(self):
        self.post_entry(self.admin)
        response = self.post_entry(self.admin, subject='Basic Science')
        self.assertEqual(response.status_code, 400)
        self.assertIn('classId', response.data['fieldErrors'])
        self.assertEqual(TimetableEntry.objects.count(), 1)

    def test_period_can_be_created_and_updated_over_http(self):
        self.auth(self.admin)
        created = self.client.post(
            self.url('/timetable/periods/'),
            {'name': 'Chapel', 'startTime': '10:00', 'endTime': '10:25', 'isBreak': True},
            format='json',
        )
        self.assertEqual(created.status_code, 201)
        self.assertEqual(created.data['name'], 'Chapel')
        self.assertTrue(created.data['isBreak'])

        updated = self.client.patch(
            self.url("/timetable/periods/%s/" % created.data['id']),
            {'name': 'Chapel', 'startTime': '10:05', 'endTime': '10:30'},
            format='json',
        )
        self.assertEqual(updated.status_code, 200)
        self.assertEqual(updated.data['startTime'], '10:05')

    def test_bad_period_time_is_reported(self):
        self.auth(self.admin)
        response = self.client.post(
            self.url('/timetable/periods/'),
            {'name': 'Night', 'startTime': '18:00', 'endTime': '07:00'},
            format='json',
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn('endTime', response.data['fieldErrors'])

    def test_teacher_cannot_add_a_period(self):
        self.auth(self.teacher)
        response = self.client.post(
            self.url('/timetable/periods/'),
            {'name': 'Extra', 'startTime': '16:00', 'endTime': '16:40'},
            format='json',
        )
        self.assertEqual(response.status_code, 403)

    def test_another_school_cannot_write_an_entry_onto_our_period(self):
        self.auth(self.other_admin)
        response = self.client.post(self.url('/timetable/entries/'), {
            'weekday': 0, 'periodId': str(self.p1.pk),
            'classId': str(self.jss1.pk), 'subject': 'Mathematics',
        }, format='json')
        self.assertEqual(response.status_code, 400)

    def test_delete_from_another_school_is_a_404(self):
        self.post_entry(self.admin)
        entry = TimetableEntry.objects.get()
        self.auth(self.other_admin)
        response = self.client.delete(self.url('/timetable/entries/%s/' % entry.pk))
        self.assertEqual(response.status_code, 404)
        self.assertTrue(TimetableEntry.objects.filter(pk=entry.pk).exists())


class TimetableQueryBudgetTests(SchoolTestCase):
    """The grid must not degrade into one query per lesson."""

    def setUp(self):
        super().setUp()
        periods = timetable_service.ensure_periods(self.school)
        # Six lesson bells, so a day can hold six lessons per class. The seeded
        # day interleaves Break and Lunch, which cannot hold a lesson.
        self.lesson_periods = [p for p in periods if not p.is_break][:6]
        self.teachers = [
            StaffMember.objects.create(
                school=self.school, full_name='Teacher %s' % n,
                email='t%s@success.example' % n, role='teacher',
            )
            for n in range(5)
        ]
        # One class's full week: 5 days x 6 periods.
        for weekday in range(5):
            for index, period in enumerate(self.lesson_periods):
                timetable_service.create_entry(self.school, {
                    'weekday': weekday,
                    'periodId': str(period.pk),
                    'classId': str(self.jss1.pk),
                    'subject': 'Mathematics',
                    'teacherId': str(self.teachers[index % len(self.teachers)].public_id),
                    'room': 'Room %s' % index,
                })
        # Two more classes sharing Monday morning, so the school is not
        # single-class. Left unassigned on purpose: a period holds one lesson per
        # class, so these need no teacher or room to avoid conflicting.
        for school_class in (self.jss2, self.sss1):
            for period in self.lesson_periods[:2]:
                timetable_service.create_entry(self.school, {
                    'weekday': 0,
                    'periodId': str(period.pk),
                    'classId': str(school_class.pk),
                    'subject': 'English Language',
                    'teacherId': '',
                    'room': '',
                })

    def query_count(self, **params):
        with CaptureQueriesContext(connection) as captured:
            timetable_service.grid_payload(self.admin, self.school, params)
        return len(captured.captured_queries)

    def test_scoped_grid_read_has_a_fixed_query_count(self):
        """Thirty lessons must not mean thirty queries."""
        queries = self.query_count(classId=str(self.jss1.pk))
        self.assertLessEqual(queries, 6, 'grid read used %s queries' % queries)

    def test_query_count_does_not_grow_with_the_number_of_lessons(self):
        small = self.query_count(classId=str(self.jss1.pk))
        # Fill the rest of the week for the other two classes, in the periods
        # setUp deliberately left free.
        for school_class in (self.jss2, self.sss1):
            for weekday in range(5):
                for period in self.lesson_periods[2:]:
                    timetable_service.create_entry(self.school, {
                        'weekday': weekday,
                        'periodId': str(period.pk),
                        'classId': str(school_class.pk),
                        'subject': 'Basic Science',
                        'teacherId': '',
                        'room': '',
                    })
        # 30 for JSS 1, plus 2 Monday lessons each for the other two classes from
        # setUp, plus the 40 added here.
        self.assertEqual(TimetableEntry.objects.count(), 74)
        self.assertEqual(small, self.query_count(classId=str(self.jss1.pk)))


class TimetableAssistantTests(SchoolTestCase):
    """The assistant must answer from the timetable, not from an empty stub."""

    def setUp(self):
        super().setUp()
        timetable_service.ensure_periods(self.school)
        self.p1 = TimetablePeriod.objects.get(school=self.school, name='P1')
        self.staff = StaffMember.objects.create(
            school=self.school, full_name='Amoah Grace', email=self.teacher.email,
            role='teacher', classes=['JSS 1'],
        )
        timetable_service.create_entry(self.school, {
            'weekday': 2, 'periodId': str(self.p1.pk), 'classId': str(self.jss1.pk),
            'subject': 'Mathematics', 'teacherId': str(self.staff.public_id), 'room': 'Room 1',
        })

    def test_teacher_schedule_reports_the_real_week(self):
        schedule = ai_tools.get_teacher_schedule(self.teacher)
        self.assertEqual(schedule['teacher'], 'Amoah Grace')
        self.assertEqual(schedule['lessonCount'], 1)
        self.assertEqual(schedule['days'][0]['day'], 'Wednesday')
        lesson = schedule['days'][0]['lessons'][0]
        self.assertEqual(lesson['className'], 'JSS 1')
        self.assertEqual(lesson['subject'], 'Mathematics')
        self.assertEqual(lesson['period'], 'P1')
        self.assertEqual(lesson['room'], 'Room 1')
        self.assertEqual(lesson['startTime'], '08:00')

    def test_teacher_schedule_is_empty_for_a_teacher_with_no_staff_record(self):
        """No staff row means no lessons, rather than a crash."""
        schedule = ai_tools.get_teacher_schedule(self.accountant)
        self.assertEqual(schedule['lessonCount'], 0)
        self.assertEqual(schedule['days'], [])

    def test_class_timetable_reports_the_real_week(self):
        result = ai_tools.get_class_timetable(self.principal, class_name='JSS 1')
        self.assertEqual(result['className'], 'JSS 1')
        self.assertEqual(result['lessonCount'], 1)
        self.assertEqual(result['entries'][0]['subject'], 'Mathematics')
        self.assertEqual(result['entries'][0]['teacher'], 'Amoah Grace')
        self.assertEqual(result['days'][0]['day'], 'Wednesday')

    def test_class_timetable_for_an_unscheduled_class_is_empty_not_broken(self):
        result = ai_tools.get_class_timetable(self.principal, class_name='SSS 1')
        self.assertEqual(result['lessonCount'], 0)
        self.assertEqual(result['entries'], [])

    def test_class_timetable_cannot_read_another_school(self):
        with self.assertRaises(Exception):
            ai_tools.get_class_timetable(self.other_admin, class_name='JSS 1')
