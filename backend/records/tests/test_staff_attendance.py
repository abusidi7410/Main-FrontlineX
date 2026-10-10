"""Staff check-in: GPS verification against the school's stored campus location.

These pin the rules that would otherwise fail quietly:

* A check-in inside the attendance radius counts as on site; far outside it does
  not; a reading the accuracy leaves ambiguous is held for a human.
* A missing fix is recorded but not trusted, never dropped.
* One check-in per staff member per day — a second tap updates, not duplicates.
* Check-in is a staff-only gesture; a pupil or parent cannot use it.
* A teacher only ever reads their own check-ins; a review is an admin act and is
  audited.
"""
from __future__ import annotations

import datetime
from decimal import Decimal

from django.utils import timezone as django_timezone

from accounts.models import User
from records.models import StaffAttendance, StaffMember
from schools.models import AuditLog

from .test_security import SecurityTestBase

# Roughly 111 m of latitude per 0.001 degree, so these offsets are easy to read.
LAT_INSIDE = 6.5249        # ~ +55 m from the school
LAT_OUTSIDE = 6.5344       # ~ +1110 m
LAT_NEAR_FENCE = 6.5262    # ~ +200 m
SCHOOL_LAT = Decimal('6.524400')
SCHOOL_LNG = Decimal('3.379200')


class StaffAttendanceTests(SecurityTestBase):
    def setUp(self):
        super().setUp()
        self.school.latitude = SCHOOL_LAT
        self.school.longitude = SCHOOL_LNG
        self.school.attendance_radius = 150
        self.school.save(update_fields=['latitude', 'longitude', 'attendance_radius'])
        self.today = datetime.date(2026, 9, 18)
        self.url = '/api/v1/attendance/check-in/'
        self.list_url = '/api/v1/attendance/staff-records/'

    def check_in(self, user, **body):
        self.auth(user)
        payload = {'latitude': LAT_INSIDE, 'longitude': float(SCHOOL_LNG)}
        payload.update(body)
        return self.client.post(self.url, payload, format='json')

    # ── distance classification ────────────────────────────────────────────

    def test_check_in_inside_radius_is_at_school(self):
        response = self.check_in(self.teacher)
        self.assertEqual(response.status_code, 201, response.content)
        body = response.json()
        self.assertEqual(body['status'], 'at_school')
        self.assertLess(body['distanceMeters'], 150)
        self.assertEqual(body['staffName'], 'Teacher Test')

    def test_check_in_outside_radius_is_outside(self):
        response = self.check_in(self.teacher, latitude=LAT_OUTSIDE)
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(response.json()['status'], 'outside')

    def test_check_in_near_fence_with_coarse_accuracy_pends_review(self):
        response = self.check_in(self.teacher, latitude=LAT_NEAR_FENCE, accuracy=100)
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(response.json()['status'], 'pending_review')

    def test_check_in_without_a_fix_is_recorded_but_unverified(self):
        response = self.check_in(self.teacher, latitude=None, longitude=None)
        self.assertEqual(response.status_code, 201, response.content)
        body = response.json()
        self.assertEqual(body['status'], 'unverified')
        self.assertIsNone(body['distanceMeters'])
        self.assertIsNone(body['latitude'])

    def test_check_in_without_school_coordinates_is_unverified(self):
        self.school.latitude = None
        self.school.longitude = None
        self.school.save(update_fields=['latitude', 'longitude'])
        response = self.check_in(self.teacher)
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(response.json()['status'], 'unverified')

    def test_lone_coordinate_is_rejected(self):
        self.auth(self.teacher)
        response = self.client.post(
            self.url, {'latitude': LAT_INSIDE}, format='json',
        )
        self.assertEqual(response.status_code, 400, response.content)

    # ── one per day ────────────────────────────────────────────────────────

    def test_second_check_in_same_day_updates_the_same_row(self):
        self.check_in(self.teacher)
        response = self.check_in(self.teacher, latitude=LAT_OUTSIDE)
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(
            StaffAttendance.objects.filter(staff=self.teacher_staff).count(), 1,
        )
        self.assertEqual(response.json()['status'], 'outside')

    def test_check_in_is_audited(self):
        self.check_in(self.teacher)
        self.assertTrue(
            AuditLog.objects.filter(action='attendance.staff.check_in').exists(),
        )

    def test_future_date_is_rejected(self):
        future = (datetime.date.today() + datetime.timedelta(days=2)).isoformat()
        response = self.check_in(self.teacher, date=future)
        self.assertEqual(response.status_code, 400, response.content)

    # ── authorisation ──────────────────────────────────────────────────────

    def test_account_without_a_staff_record_is_refused(self):
        self.auth(self.admin)
        response = self.client.post(
            self.url,
            {'latitude': LAT_INSIDE, 'longitude': float(SCHOOL_LNG)},
            format='json',
        )
        self.assertEqual(response.status_code, 400, response.content)

    def test_pupil_and_parent_cannot_check_in(self):
        for user in (self.student_user, self.parent):
            self.auth(user)
            response = self.client.post(
                self.url,
                {'latitude': LAT_INSIDE, 'longitude': float(SCHOOL_LNG)},
                format='json',
            )
            self.assertEqual(response.status_code, 403, response.content)

    def test_teacher_reads_only_their_own_check_ins(self):
        StaffAttendance.objects.create(
            school=self.school, staff=self.subject_staff, date=self.today,
            check_in_at=django_timezone.now(), status='at_school',
        )
        self.check_in(self.teacher)

        self.auth(self.teacher)
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, 200, response.content)
        names = {row['staffName'] for row in response.json()['records']}
        self.assertEqual(names, {'Teacher Test'})

    def test_admin_sees_everyone(self):
        StaffAttendance.objects.create(
            school=self.school, staff=self.subject_staff, date=self.today,
            check_in_at=django_timezone.now(), status='at_school',
        )
        self.check_in(self.teacher)

        self.auth(self.admin)
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, 200, response.content)
        names = {row['staffName'] for row in response.json()['records']}
        self.assertEqual(names, {'Teacher Test', 'Subject Teacher'})

    # ── review ─────────────────────────────────────────────────────────────

    def test_admin_can_approve_an_uncertain_check_in(self):
        record = StaffAttendance.objects.create(
            school=self.school, staff=self.teacher_staff, date=self.today,
            check_in_at=django_timezone.now(),
            status='pending_review', distance_meters=200,
        )
        self.auth(self.admin)
        response = self.client.post(
            f'{self.list_url}{record.public_id}/review/',
            {'decision': 'approve', 'note': 'Confirmed at the gate'},
            format='json',
        )
        self.assertEqual(response.status_code, 200, response.content)
        record.refresh_from_db()
        self.assertEqual(record.status, 'at_school')
        self.assertEqual(record.reviewed_by, self.admin)
        self.assertTrue(
            AuditLog.objects.filter(action='attendance.staff.review').exists(),
        )

    def test_teacher_cannot_review(self):
        record = StaffAttendance.objects.create(
            school=self.school, staff=self.teacher_staff, date=self.today,
            check_in_at=django_timezone.now(),
            status='pending_review',
        )
        self.auth(self.teacher)
        response = self.client.post(
            f'{self.list_url}{record.public_id}/review/',
            {'decision': 'approve'},
            format='json',
        )
        self.assertEqual(response.status_code, 403, response.content)

    def test_review_of_another_schools_record_is_not_found(self):
        other_staff = StaffMember.objects.create(
            school=self.other_school, full_name='Rival Teacher', role='teacher',
        )
        record = StaffAttendance.objects.create(
            school=self.other_school, staff=other_staff, date=self.today,
            check_in_at=django_timezone.now(), status='pending_review',
        )
        self.auth(self.admin)
        response = self.client.post(
            f'{self.list_url}{record.public_id}/review/',
            {'decision': 'approve'},
            format='json',
        )
        self.assertEqual(response.status_code, 404, response.content)

    def test_invalid_review_id_is_not_a_server_error(self):
        self.auth(self.admin)
        response = self.client.post(
            f'{self.list_url}not-a-uuid/review/',
            {'decision': 'approve'},
            format='json',
        )
        self.assertEqual(response.status_code, 404, response.content)
