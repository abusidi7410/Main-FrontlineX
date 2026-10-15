"""Teacher class check-ins: timetable-linked sessions, GPS, late alerts.

These pin the rules that would otherwise fail quietly:

* One independent check-in per timetabled lesson per day — checking into one
  lesson never touches another, and never touches the student register.
* The timetable link is authoritative: another teacher's lesson, another
  school's lesson, or a lesson on a different weekday is refused server-side.
* GPS is verified against the campus like the daily staff check-in: inside
  counts, outside is persisted as evidence but denied, no fix is recorded
  unverified and never trusted.
* Lateness is computed against the school's own clock and the bell, with a
  fixed tolerance separating "on time" from "late".
* The sweep marks a session missed only after the school's configurable grace
  period, alerts exactly once (idempotent across runs), never touches a
  cancelled or checked-in session, and a later check-in converts a missed row
  back into a real (late) arrival.
* The admin board is admin/principal only, filterable, and never leaks
  another school's rows; decisions (cancel/override) are audited.
"""
from __future__ import annotations

import datetime
from decimal import Decimal

from accounts.models import Notification
from records.models import (
    AttendanceRecord,
    TeacherClassCheckIn,
    TimetableEntry,
    TimetablePeriod,
)
from records.services import staff_attendance as staff_attendance_service
from records.services import teacher_checkin as teacher_checkin_service
from schools.models import AuditLog

from .test_security import SecurityTestBase

# Roughly 111 m of latitude per 0.001 degree, matching the staff suite.
LAT_INSIDE = 6.5249        # ~ +55 m from the school
LAT_OUTSIDE = 6.5344       # ~ +1110 m
SCHOOL_LAT = Decimal('6.524400')
SCHOOL_LNG = Decimal('3.379200')

MIDNIGHT = datetime.time(0, 0)

CHECK_IN_URL = '/api/v1/attendance/teacher-checkins/check-in/'
MY_DAY_URL = '/api/v1/attendance/teacher-checkins/my-day/'
MONITOR_URL = '/api/v1/attendance/teacher-checkins/'


class TeacherCheckInTestBase(SecurityTestBase):
    """Shared fixture: campus GPS, today's timetable, and URL helpers."""

    def setUp(self):
        super().setUp()
        self.school.latitude = SCHOOL_LAT
        self.school.longitude = SCHOOL_LNG
        self.school.attendance_radius = 150
        self.school.teacher_checkin_grace_minutes = 30
        # Every calendar day is a school day in these tests, so the sweep
        # behaves the same whether the suite runs on a weekday or a weekend.
        self.school.attendance_weekend_days = []
        self.school.save(update_fields=[
            'latitude', 'longitude', 'attendance_radius',
            'teacher_checkin_grace_minutes', 'attendance_weekend_days',
        ])

        self.today = staff_attendance_service.local_day(self.school)
        self.weekday = self.today.weekday()

        self.period1 = TimetablePeriod.objects.create(
            school=self.school, name='Period 1',
            start_time=datetime.time(8, 0), end_time=datetime.time(8, 40),
            sort_order=1,
        )
        self.period2 = TimetablePeriod.objects.create(
            school=self.school, name='Period 2',
            start_time=datetime.time(9, 0), end_time=datetime.time(9, 40),
            sort_order=2,
        )
        self.entry = TimetableEntry.objects.create(
            school=self.school, period=self.period1, class_obj=self.jss1,
            subject='Mathematics', teacher=self.teacher_staff,
            weekday=self.weekday, room='A1',
        )
        self.entry2 = TimetableEntry.objects.create(
            school=self.school, period=self.period2, class_obj=self.jss1,
            subject='English', teacher=self.teacher_staff,
            weekday=self.weekday, room='A1',
        )
        # Another teacher's lesson, on another weekday: never visible or
        # check-in-able by `self.teacher`, and never swept as today's session.
        self.other_entry = TimetableEntry.objects.create(
            school=self.school, period=self.period1, class_obj=self.jss2,
            subject='Science', teacher=self.subject_staff,
            weekday=(self.weekday + 2) % 7, room='B2',
        )
        # A lesson on a different weekday: out of scope for "today".
        self.tomorrow_entry = TimetableEntry.objects.create(
            school=self.school, period=self.period1, class_obj=self.jss1,
            subject='Biology', teacher=self.teacher_staff,
            weekday=(self.weekday + 1) % 7, room='A1',
        )
        # The rival school's timetable: must be invisible from over here.
        self.rival_period = TimetablePeriod.objects.create(
            school=self.other_school, name='Period 1',
            start_time=datetime.time(8, 0), end_time=datetime.time(8, 40),
            sort_order=1,
        )
        self.rival_entry = TimetableEntry.objects.create(
            school=self.other_school, period=self.rival_period,
            class_obj=self.other_jss1, subject='Mathematics',
            teacher=None, weekday=self.weekday,
        )

    # ── helpers ────────────────────────────────────────────────────────────

    def check_in(self, user, entry_id=None, **body):
        self.auth(user)
        payload = {
            'entryId': entry_id if entry_id is not None else self.entry.pk,
            'latitude': LAT_INSIDE,
            'longitude': float(SCHOOL_LNG),
        }
        payload.update(body)
        return self.client.post(CHECK_IN_URL, payload, format='json')

    def at_time(self, moment):
        """An aware datetime for `moment` on the school's today."""
        return teacher_checkin_service.session_datetime(
            self.school, self.today, moment,
        )

    def service_check_in(self, entry, *, at, latitude=LAT_INSIDE,
                         longitude=float(SCHOOL_LNG), accuracy=None):
        return teacher_checkin_service.check_in(
            user=self.teacher, school=self.school,
            staff=entry.teacher, entry_id=entry.pk,
            latitude=latitude, longitude=longitude,
            accuracy=accuracy, at=at,
        )


class TeacherCheckInTests(TeacherCheckInTestBase):
    # ── link to the timetable ──────────────────────────────────────────────

    def test_check_in_persists_one_row_for_one_lesson(self):
        record, created = teacher_checkin_service.check_in(
            user=self.teacher, school=self.school, staff=self.teacher_staff,
            entry_id=self.entry.pk, latitude=LAT_INSIDE,
            longitude=float(SCHOOL_LNG), at=self.at_time(datetime.time(8, 2)),
        )
        self.assertTrue(created)
        self.assertEqual(record.entry, self.entry)
        self.assertEqual(record.staff, self.teacher_staff)
        self.assertEqual(record.date, self.today)
        self.assertEqual(record.class_name, 'JSS 1')
        self.assertEqual(record.subject, 'Mathematics')
        self.assertEqual(record.scheduled_start, datetime.time(8, 0))

    def test_check_in_to_another_teachers_lesson_is_forbidden(self):
        # The assignment check runs before the weekday check, so this is a
        # refusal on ownership, not on scheduling.
        response = self.check_in(self.teacher, entry_id=self.other_entry.pk)
        self.assertEqual(response.status_code, 403, response.content)
        self.assertFalse(TeacherClassCheckIn.objects.exists())

    def test_check_in_to_another_schools_lesson_is_not_found(self):
        response = self.check_in(self.teacher, entry_id=self.rival_entry.pk)
        self.assertEqual(response.status_code, 400, response.content)
        self.assertFalse(TeacherClassCheckIn.objects.exists())

    def test_check_in_on_a_different_weekday_is_refused(self):
        response = self.check_in(self.teacher, entry_id=self.tomorrow_entry.pk)
        self.assertEqual(response.status_code, 400, response.content)

    def test_unknown_lesson_id_is_a_client_error(self):
        response = self.check_in(self.teacher, entry_id=999999)
        self.assertEqual(response.status_code, 400, response.content)

    # ── GPS verification ───────────────────────────────────────────────────

    def test_inside_the_fence_is_present_verified(self):
        record, _ = self.service_check_in(
            self.entry, at=self.at_time(datetime.time(8, 2)),
        )
        self.assertEqual(record.status, TeacherClassCheckIn.Status.PRESENT_VERIFIED)
        self.assertEqual(record.gps_status, TeacherClassCheckIn.Gps.INSIDE)
        self.assertLess(record.distance_meters, 150)

    def test_outside_the_fence_is_denied_but_persisted_as_evidence(self):
        response = self.check_in(self.teacher, latitude=LAT_OUTSIDE)
        self.assertEqual(response.status_code, 201, response.content)
        body = response.json()
        self.assertTrue(body['denied'])
        self.assertEqual(body['status'], 'outside')
        self.assertEqual(body['gpsStatus'], 'outside')
        self.assertIn('outside the approved school location', body['deniedReason'])
        record = TeacherClassCheckIn.objects.get()
        self.assertEqual(record.gps_status, TeacherClassCheckIn.Gps.OUTSIDE)
        self.assertIsNotNone(record.distance_meters)

    def test_outside_attempt_then_arrival_converts_the_same_row(self):
        self.check_in(self.teacher, latitude=LAT_OUTSIDE)
        response = self.check_in(self.teacher)
        self.assertEqual(response.status_code, 200, response.content)
        body = response.json()
        self.assertFalse(body['denied'])
        # Present or late depends on the wall clock; the denial is gone.
        self.assertIn(body['status'], {'present_verified', 'late_verified'})
        self.assertEqual(
            TeacherClassCheckIn.objects.filter(
                staff=self.teacher_staff, date=self.today,
            ).count(),
            1,
        )

    def test_no_fix_is_recorded_unverified_and_never_trusted(self):
        response = self.check_in(self.teacher, latitude=None, longitude=None)
        self.assertEqual(response.status_code, 201, response.content)
        body = response.json()
        self.assertEqual(body['status'], 'unverified')
        self.assertEqual(body['gpsStatus'], 'unverified')
        self.assertIsNone(body['distanceMeters'])
        self.assertFalse(body['denied'])

    def test_lone_coordinate_is_rejected(self):
        self.auth(self.teacher)
        response = self.client.post(
            CHECK_IN_URL,
            {'entryId': self.entry.pk, 'latitude': LAT_INSIDE},
            format='json',
        )
        self.assertEqual(response.status_code, 400, response.content)

    # ── one row per lesson, idempotent ─────────────────────────────────────

    def test_second_tap_never_duplicates_a_verified_check_in(self):
        first, _ = self.service_check_in(
            self.entry, at=self.at_time(datetime.time(8, 2)),
        )
        second, created = self.service_check_in(
            self.entry, at=self.at_time(datetime.time(8, 3)),
        )
        self.assertFalse(created)
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(
            TeacherClassCheckIn.objects.filter(staff=self.teacher_staff).count(),
            1,
        )
        # The original on-time reading is not rewritten by the second tap.
        self.assertEqual(second.check_in_at, first.check_in_at)

    def test_each_lesson_of_the_day_is_independent(self):
        self.check_in(self.teacher)  # entry1 only
        statuses = {
            row.subject: row.status
            for row in TeacherClassCheckIn.objects.filter(staff=self.teacher_staff)
        }
        # Present or late depends on the wall clock; the point is that only
        # the tapped lesson got a row at all.
        self.assertEqual(set(statuses), {'Mathematics'})
        self.assertIn(
            statuses['Mathematics'],
            {'present_verified', 'late_verified'},
        )

        response = self.check_in(self.teacher, entry_id=self.entry2.pk)
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(
            TeacherClassCheckIn.objects.filter(staff=self.teacher_staff).count(),
            2,
        )

    # ── lateness ───────────────────────────────────────────────────────────

    def test_check_in_within_the_tolerance_is_on_time(self):
        record, _ = self.service_check_in(
            self.entry, at=self.at_time(datetime.time(8, 5)),
        )
        self.assertEqual(record.status, TeacherClassCheckIn.Status.PRESENT_VERIFIED)
        self.assertEqual(record.minutes_late, 5)

    def test_check_in_after_the_tolerance_is_late(self):
        record, _ = self.service_check_in(
            self.entry, at=self.at_time(datetime.time(8, 10)),
        )
        self.assertEqual(record.status, TeacherClassCheckIn.Status.LATE_VERIFIED)
        self.assertEqual(record.minutes_late, 10)

    def test_early_check_in_counts_as_on_time(self):
        record, _ = self.service_check_in(
            self.entry, at=self.at_time(datetime.time(7, 50)),
        )
        self.assertEqual(record.status, TeacherClassCheckIn.Status.PRESENT_VERIFIED)
        self.assertEqual(record.minutes_late, 0)

    # ── authorisation ──────────────────────────────────────────────────────

    def test_pupil_and_parent_cannot_check_in_to_a_lesson(self):
        for user in (self.student_user, self.parent):
            response = self.check_in(user)
            self.assertEqual(response.status_code, 403, response.content)
        self.assertFalse(TeacherClassCheckIn.objects.exists())

    def test_account_without_a_staff_record_is_refused(self):
        response = self.check_in(self.admin)
        self.assertEqual(response.status_code, 400, response.content)

    def test_check_in_is_audited(self):
        self.check_in(self.teacher)
        self.assertTrue(
            AuditLog.objects.filter(action='attendance.teacher.check_in').exists(),
        )

    # ── independence from the student register ─────────────────────────────

    def test_check_in_writes_no_student_attendance(self):
        self.check_in(self.teacher)
        self.assertEqual(AttendanceRecord.objects.count(), 0)

    def test_student_register_writes_no_teacher_check_in(self):
        self.auth(self.teacher)
        self.submit_attendance(date=self.today.isoformat())
        self.assertEqual(TeacherClassCheckIn.objects.count(), 0)


class TeacherCheckInMyDayTests(TeacherCheckInTestBase):
    def test_my_day_lists_every_lesson_with_a_state(self):
        self.auth(self.teacher)
        response = self.client.get(MY_DAY_URL)
        self.assertEqual(response.status_code, 200, response.content)
        body = response.json()
        self.assertEqual(body['date'], self.today.isoformat())
        self.assertEqual(body['graceMinutes'], 30)
        self.assertEqual(len(body['sessions']), 2)
        self.assertEqual(
            {row['subject'] for row in body['sessions']},
            {'Mathematics', 'English'},
        )
        for row in body['sessions']:
            self.assertEqual(row['status'], 'not_checked_in')
            self.assertTrue(row['canCheckIn'])
        self.assertEqual(body['summary']['total'], 2)
        self.assertEqual(body['summary']['not_checked_in'], 2)

    def test_my_day_reflects_a_check_in_without_claiming_another_lesson(self):
        self.check_in(self.teacher)
        self.auth(self.teacher)
        response = self.client.get(MY_DAY_URL)
        body = response.json()
        by_subject = {row['subject']: row for row in body['sessions']}
        self.assertIn(
            by_subject['Mathematics']['status'],
            {'present_verified', 'late_verified'},
        )
        self.assertEqual(by_subject['English']['status'], 'not_checked_in')
        self.assertEqual(body['summary']['not_checked_in'], 1)
        self.assertFalse(by_subject['Mathematics']['studentRegisterTaken'])

    def test_my_day_never_lists_another_teachers_lesson(self):
        # A colleague's lesson *today* — the case that matters for the list.
        TimetableEntry.objects.create(
            school=self.school, period=self.period1, class_obj=self.jss2,
            subject='Science', teacher=self.subject_staff,
            weekday=self.weekday, room='B2',
        )
        self.auth(self.teacher)
        response = self.client.get(MY_DAY_URL)
        subjects = {row['subject'] for row in response.json()['sessions']}
        self.assertNotIn('Science', subjects)

    def test_my_day_honours_an_explicit_date(self):
        self.auth(self.teacher)
        response = self.client.get(MY_DAY_URL, {'date': self.today.isoformat()})
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(len(response.json()['sessions']), 2)

    def test_my_day_rejects_a_garbage_date(self):
        self.auth(self.teacher)
        response = self.client.get(MY_DAY_URL, {'date': 'yesterday'})
        self.assertEqual(response.status_code, 400, response.content)


class TeacherCheckInSweepTests(TeacherCheckInTestBase):
    """Late-alert sweep: deadline, idempotence, excusals, late conversions."""

    def sweep(self, now_moment):
        return teacher_checkin_service.sweep_school_day(
            self.school, self.today, now=self.at_time(now_moment),
        )

    def test_nothing_is_marked_missed_before_the_deadline(self):
        missed = self.sweep(datetime.time(8, 15))  # grace ends 08:30
        self.assertEqual(missed, [])
        self.assertFalse(TeacherClassCheckIn.objects.exists())
        self.assertEqual(Notification.objects.count(), 0)

    def test_after_the_deadline_the_session_is_missed_and_alerted(self):
        missed = self.sweep(datetime.time(8, 31))
        self.assertEqual(len(missed), 1)
        record = TeacherClassCheckIn.objects.get(entry=self.entry)
        self.assertEqual(record.status, TeacherClassCheckIn.Status.MISSED)
        self.assertTrue(record.late_alert_sent)
        self.assertTrue(
            Notification.objects.filter(
                user=self.admin, type=Notification.Type.ATTENDANCE,
                dedupe_key=f'teacher-checkin-missed:{record.pk}',
            ).exists(),
        )
        # The teacher is not told they are missing; the admin acts on it.
        self.assertFalse(Notification.objects.filter(user=self.teacher).exists())

    def test_reruns_never_double_alert(self):
        self.sweep(datetime.time(8, 31))
        before = Notification.objects.count()
        self.sweep(datetime.time(8, 35))
        self.sweep(datetime.time(8, 59))
        self.assertEqual(Notification.objects.count(), before)
        self.assertEqual(
            TeacherClassCheckIn.objects.filter(
                staff=self.teacher_staff, date=self.today,
            ).count(),
            1,
        )

    def test_grace_period_is_school_configurable(self):
        self.school.teacher_checkin_grace_minutes = 5
        self.school.save(update_fields=['teacher_checkin_grace_minutes'])
        # 08:06 is past a 5-minute grace (deadline 08:05)…
        self.assertEqual(len(self.sweep(datetime.time(8, 6))), 1)

    def test_cancelled_session_is_never_marked_missed(self):
        record, _ = self.service_check_in(
            self.entry, at=self.at_time(datetime.time(7, 55)),
        )
        teacher_checkin_service.cancel_session(
            school=self.school, record=record, note='Venue flooded',
        )
        missed = self.sweep(datetime.time(9, 0))
        # The cancelled lesson is skipped; only entry2 (09:00 + grace) is not
        # yet due, so nothing is due at all.
        self.assertEqual(missed, [])
        record.refresh_from_db()
        self.assertEqual(record.status, TeacherClassCheckIn.Status.CANCELLED)
        self.assertFalse(record.late_alert_sent)

    def test_checked_in_session_is_not_marked_missed(self):
        self.check_in(self.teacher)
        missed = self.sweep(datetime.time(9, 0))
        self.assertEqual(missed, [])
        record = TeacherClassCheckIn.objects.get(entry=self.entry)
        self.assertIn(
            record.status,
            {'present_verified', 'late_verified'},
        )

    def test_late_check_in_after_a_miss_converts_the_row(self):
        self.sweep(datetime.time(8, 31))
        record = TeacherClassCheckIn.objects.get(entry=self.entry)
        self.assertEqual(record.status, TeacherClassCheckIn.Status.MISSED)

        record, created = self.service_check_in(
            self.entry, at=self.at_time(datetime.time(8, 45)),
        )
        self.assertFalse(created)
        self.assertEqual(record.status, TeacherClassCheckIn.Status.LATE_VERIFIED)
        self.assertIsNotNone(record.check_in_at)
        self.assertEqual(record.minutes_late, 45)

    def test_a_day_the_school_is_closed_is_not_swept(self):
        self.school.attendance_weekend_days = [self.weekday]
        self.school.save(update_fields=['attendance_weekend_days'])
        missed = self.sweep(datetime.time(9, 0))
        self.assertEqual(missed, [])
        self.assertFalse(TeacherClassCheckIn.objects.exists())

    def test_a_lesson_on_another_weekday_is_not_swept(self):
        # `tomorrow_entry` sits on another weekday: today's sweep ignores it.
        self.sweep(datetime.time(9, 0))
        self.assertFalse(
            TeacherClassCheckIn.objects.filter(entry=self.tomorrow_entry).exists(),
        )

    def test_sweep_ignores_a_school_with_no_coordinates_context(self):
        # The sweep must work even where GPS was never captured: missed is a
        # timing fact, not a location one.
        self.school.latitude = None
        self.school.longitude = None
        self.school.save(update_fields=['latitude', 'longitude'])
        missed = self.sweep(datetime.time(8, 31))
        self.assertEqual(len(missed), 1)


class TeacherCheckInMonitorTests(TeacherCheckInTestBase):
    def setUp(self):
        super().setUp()
        # Two rows for the board: a verified arrival and a missed session.
        self.service_check_in(
            self.entry, at=self.at_time(datetime.time(8, 2)),
        )
        missed, _ = self.service_check_in(
            self.entry2, at=self.at_time(datetime.time(8, 2)),
        )
        TeacherClassCheckIn.objects.filter(pk=missed.pk).update(status='missed')

    def test_teacher_cannot_open_the_monitor_board(self):
        self.auth(self.teacher)
        response = self.client.get(MONITOR_URL)
        self.assertEqual(response.status_code, 403, response.content)

    def test_student_and_parent_cannot_open_the_monitor_board(self):
        for user in (self.student_user, self.parent):
            self.auth(user)
            response = self.client.get(MONITOR_URL)
            self.assertEqual(response.status_code, 403, response.content)

    def test_admin_sees_rows_with_summary_counts(self):
        self.auth(self.admin)
        response = self.client.get(MONITOR_URL, {'date': self.today.isoformat()})
        self.assertEqual(response.status_code, 200, response.content)
        body = response.json()
        self.assertEqual(body['count'], 2)
        self.assertEqual(body['summary']['counts']['present_verified'], 1)
        self.assertEqual(body['summary']['counts']['missed'], 1)

    def test_filters_by_class_and_status(self):
        self.auth(self.admin)
        response = self.client.get(
            MONITOR_URL,
            {'className': 'JSS 1', 'status': 'missed'},
        )
        self.assertEqual(response.status_code, 200, response.content)
        rows = response.json()['records']
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['status'], 'missed')
        self.assertEqual(rows[0]['subject'], 'English')

    def test_filter_by_teacher(self):
        self.auth(self.admin)
        response = self.client.get(
            MONITOR_URL, {'staffId': str(self.teacher_staff.public_id)},
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()['count'], 2)
        self.assertEqual(
            {row['staffName'] for row in response.json()['records']},
            {'Teacher Test'},
        )

    def test_another_schools_rows_are_never_visible(self):
        rival_staff = self.other_school.staff.create(
            full_name='Rival Teacher', role='teacher',
        )
        TeacherClassCheckIn.objects.create(
            school=self.other_school, staff=rival_staff,
            date=self.today, weekday=self.weekday,
            scheduled_start=datetime.time(8, 0),
            scheduled_end=datetime.time(8, 40),
            class_name='JSS 1', subject='Mathematics',
            status='missed', gps_status='unverified',
        )
        self.auth(self.admin)
        response = self.client.get(MONITOR_URL)
        self.assertEqual(response.status_code, 200, response.content)
        names = {row['staffName'] for row in response.json()['records']}
        self.assertNotIn('Rival Teacher', names)

    def test_invalid_date_is_a_client_error(self):
        self.auth(self.admin)
        response = self.client.get(MONITOR_URL, {'date': 'not-a-date'})
        self.assertEqual(response.status_code, 400, response.content)


class TeacherCheckInDecisionTests(TeacherCheckInTestBase):
    def setUp(self):
        super().setUp()
        self.record, _ = self.service_check_in(
            self.entry, at=self.at_time(datetime.time(8, 45)),
        )
        self.decision_url = f'{MONITOR_URL}{self.record.pk}/decision/'

    def test_admin_can_cancel_a_lesson(self):
        self.auth(self.admin)
        response = self.client.post(
            self.decision_url,
            {'action': 'cancel', 'note': 'Hall unavailable'},
            format='json',
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.record.refresh_from_db()
        self.assertEqual(self.record.status, TeacherClassCheckIn.Status.CANCELLED)
        self.assertEqual(self.record.decision_note, 'Hall unavailable')
        self.assertTrue(
            AuditLog.objects.filter(action='attendance.teacher.cancel').exists(),
        )

    def test_cancelled_lesson_cannot_be_checked_into(self):
        teacher_checkin_service.cancel_session(
            school=self.school, record=self.record, note='Cancelled',
        )
        response = self.check_in(self.teacher)
        self.assertEqual(response.status_code, 400, response.content)

    def test_override_requires_a_reason(self):
        self.auth(self.admin)
        response = self.client.post(
            self.decision_url,
            {'action': 'override', 'status': 'present_verified'},
            format='json',
        )
        self.assertEqual(response.status_code, 400, response.content)
        self.record.refresh_from_db()
        self.assertEqual(self.record.status, TeacherClassCheckIn.Status.LATE_VERIFIED)

    def test_admin_override_records_status_and_is_audited(self):
        self.auth(self.admin)
        response = self.client.post(
            self.decision_url,
            {
                'action': 'override',
                'status': 'present_verified',
                'note': 'Traffic confirmed by call',
            },
            format='json',
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.record.refresh_from_db()
        self.assertEqual(self.record.status, 'present_verified')
        self.assertEqual(self.record.decided_by, self.admin)
        self.assertTrue(
            AuditLog.objects.filter(action='attendance.teacher.override').exists(),
        )

    def test_override_cannot_forge_a_missed_state(self):
        self.auth(self.admin)
        response = self.client.post(
            self.decision_url,
            {'action': 'override', 'status': 'missed', 'note': 'nope'},
            format='json',
        )
        self.assertEqual(response.status_code, 400, response.content)

    def test_teacher_cannot_decide(self):
        self.auth(self.teacher)
        response = self.client.post(
            self.decision_url, {'action': 'cancel'}, format='json',
        )
        self.assertEqual(response.status_code, 403, response.content)

    def test_other_schools_record_is_not_found(self):
        rival_staff = self.other_school.staff.create(
            full_name='Rival Teacher', role='teacher',
        )
        rival_record = TeacherClassCheckIn.objects.create(
            school=self.other_school, staff=rival_staff,
            date=self.today, weekday=self.weekday,
            scheduled_start=datetime.time(8, 0),
            scheduled_end=datetime.time(8, 40),
            class_name='JSS 1', subject='Mathematics',
            status='missed', gps_status='unverified',
        )
        self.auth(self.admin)
        response = self.client.post(
            f'{MONITOR_URL}{rival_record.pk}/decision/',
            {'action': 'cancel'},
            format='json',
        )
        self.assertEqual(response.status_code, 404, response.content)
