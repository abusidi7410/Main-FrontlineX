"""Teacher class check-ins linked to timetable sessions.

A teacher's day is a set of timetabled lessons, and this module records their
arrival at each one separately from the daily staff check-in (which only says
they reached the campus) and from the student register (which says who was
taught). Three independent facts, three tables:

* ``StaffAttendance`` — the teacher reached the school that day;
* ``TeacherClassCheckIn`` (here) — the teacher arrived at a specific lesson,
  with GPS evidence and lateness against the bell;
* ``AttendanceRecord`` — which students were marked for the class that day.

Checking into one lesson never marks any other lesson, and neither the
check-in nor the student register ever writes the other. The timetable is
recurring weekly, so a session is identified by (date + weekday + period
times + class + subject) and snapshotted onto every row: later timetable
edits cannot rewrite what the teacher actually checked into.
"""
from __future__ import annotations

import datetime as dt

from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError

from schools.models import School

from ..models import StaffMember, TeacherClassCheckIn, TimetableEntry
from . import attendance as attendance_service
from . import staff_attendance as staff_attendance_service

#: Minutes after the scheduled start a check-in still counts as on time.
#: The late *alert* grace is separate and lives on the school
#: (`teacher_checkin_grace_minutes`, default 30).
LATE_TOLERANCE_MINUTES = 5


def school_now(school: School, at=None):
    """Current time in the school's own time zone."""
    at = at or timezone.now()
    tz_name = getattr(school, 'timezone', '') or ''
    if tz_name:
        try:
            from zoneinfo import ZoneInfo

            return at.astimezone(ZoneInfo(tz_name))
        except Exception:
            pass
    return timezone.localtime(at)


def session_datetime(school: School, day: dt.date, moment: dt.time):
    """An aware datetime for a bell time on a school day."""
    tz_name = getattr(school, 'timezone', '') or ''
    naive = dt.datetime.combine(day, moment)
    if tz_name:
        try:
            from zoneinfo import ZoneInfo

            return naive.replace(tzinfo=ZoneInfo(tz_name))
        except Exception:
            pass
    return timezone.make_aware(naive)


def grace_minutes(school: School) -> int:
    try:
        return max(int(getattr(school, 'teacher_checkin_grace_minutes', 30) or 30), 0)
    except (TypeError, ValueError):
        return 30


def sessions_for_staff(school: School, staff: StaffMember, day: dt.date):
    """Timetabled lessons this staff member teaches on `day`, with check-in state."""
    entries = (
        school.timetable_entries.filter(teacher=staff, weekday=day.weekday())
        .select_related('period', 'class_obj')
        .order_by('period__sort_order', 'period__start_time')
    )
    rows = {
        (
            row.weekday, row.scheduled_start, row.class_name, row.subject,
        ): row
        for row in TeacherClassCheckIn.objects.filter(
            school=school, staff=staff, date=day,
        )
    }
    sessions = []
    for entry in entries:
        key = (
            entry.weekday, entry.period.start_time,
            entry.class_obj.name, entry.subject,
        )
        sessions.append((entry, rows.get(key)))
    return sessions


def session_payload(school: School, entry: TimetableEntry, record, day: dt.date) -> dict:
    start = entry.period.start_time
    end = entry.period.end_time
    scheduled = session_datetime(school, day, start)
    now = school_now(school)
    payload = {
        'entryId': entry.pk,
        'className': entry.class_obj.name,
        'subject': entry.subject,
        'room': entry.room or '',
        'period': entry.period.name,
        'date': day.isoformat(),
        'weekday': entry.weekday,
        'scheduledStart': start.strftime('%H:%M'),
        'scheduledEnd': end.strftime('%H:%M'),
        'scheduledAt': scheduled.isoformat(),
        'checkInAt': record.check_in_at.isoformat() if record and record.check_in_at else None,
        'minutesLate': record.minutes_late if record else None,
        'status': record.status if record else 'not_checked_in',
        'gpsStatus': record.gps_status if record else 'unverified',
        'distanceMeters': record.distance_meters if record else None,
        'studentRegisterTaken': bool(
            attendance_service.existing_marks(school, entry.class_obj, day),
        ),
        'canCheckIn': (
            record is None or record.status in (
                TeacherClassCheckIn.Status.OUTSIDE,
                TeacherClassCheckIn.Status.UNVERIFIED,
                TeacherClassCheckIn.Status.MISSED,
            )
        ) and day == staff_attendance_service.local_day(school, now)
        and entry.weekday == day.weekday(),
    }
    return payload


def _snapshot(entry: TimetableEntry, day: dt.date) -> dict:
    return {
        'weekday': entry.weekday,
        'period_name': entry.period.name,
        'scheduled_start': entry.period.start_time,
        'scheduled_end': entry.period.end_time,
        'class_name': entry.class_obj.name,
        'subject': entry.subject,
        'room': entry.room or '',
    }


@transaction.atomic
def check_in(
    *, user, school: School, staff: StaffMember, entry_id: int,
    latitude=None, longitude=None, accuracy=None, at=None,
):
    """Check a teacher into one timetabled lesson, with GPS verification.

    Every critical check runs here on the server: the lesson belongs to this
    school, it is assigned to this teacher, and it falls on today's school
    day. The coordinates are verified against the campus with the same
    classifier as the daily staff check-in. An outside-fence reading is persisted as a denied
    attempt (the view answers it with a refusal, not a 500); a missing reading
    is recorded as unverified rather than trusted. The record is committed
    either way — evidence of where a check-in was attempted is exactly what an
    administrator needs to see.
    """
    at = at or timezone.now()
    today = staff_attendance_service.local_day(school, at)
    try:
        entry = (
            school.timetable_entries.select_related('period', 'class_obj')
            .get(pk=entry_id)
        )
    except (TimetableEntry.DoesNotExist, ValueError, TypeError):
        raise ValidationError({'entry': 'That lesson does not exist in this school.'})
    if entry.teacher_id != staff.pk:
        raise PermissionDenied('You are not assigned to teach that lesson.')
    if entry.weekday != today.weekday():
        raise ValidationError({'entry': 'That lesson is not scheduled for today.'})

    gps_status, distance = staff_attendance_service.classify(
        school, latitude, longitude, accuracy,
    )
    if gps_status == staff_attendance_service.STATUS_PENDING_REVIEW:
        # Too close to call from one reading: record it, do not trust it.
        gps_status = TeacherClassCheckIn.Gps.UNVERIFIED
    elif gps_status == staff_attendance_service.STATUS_AT_SCHOOL:
        gps_status = TeacherClassCheckIn.Gps.INSIDE
    elif gps_status == staff_attendance_service.STATUS_OUTSIDE:
        gps_status = TeacherClassCheckIn.Gps.OUTSIDE
    else:
        gps_status = TeacherClassCheckIn.Gps.UNVERIFIED

    scheduled = session_datetime(school, today, entry.period.start_time)
    late_by = int((at - scheduled).total_seconds() // 60)
    verified = gps_status == TeacherClassCheckIn.Gps.INSIDE
    if not verified:
        status = (
            TeacherClassCheckIn.Status.OUTSIDE
            if gps_status == TeacherClassCheckIn.Gps.OUTSIDE
            else TeacherClassCheckIn.Status.UNVERIFIED
        )
    elif late_by > LATE_TOLERANCE_MINUTES:
        status = TeacherClassCheckIn.Status.LATE_VERIFIED
    else:
        status = TeacherClassCheckIn.Status.PRESENT_VERIFIED

    key = {
        'school': school,
        'staff': staff,
        'date': today,
        **_snapshot(entry, today),
    }
    try:
        record, created = TeacherClassCheckIn.objects.get_or_create(
            **key,
            defaults={
                'entry': entry,
                'check_in_at': at,
                'minutes_late': max(late_by, 0),
                'status': status,
                'gps_status': gps_status,
                'latitude': latitude,
                'longitude': longitude,
                'accuracy_meters': accuracy,
                'distance_meters': distance,
            },
        )
    except IntegrityError:
        # A concurrent sweep or tap inserted the row first. Refetch by the
        # *constraint* fields only — the snapshot's room or period name may
        # differ from ours (the timetable changed after the sweep wrote), and
        # a lookup on those would miss the row this race is about.
        record = TeacherClassCheckIn.objects.select_for_update(of=('self',)).get(
            school=school,
            staff=staff,
            date=today,
            weekday=entry.weekday,
            scheduled_start=entry.period.start_time,
            class_name=entry.class_obj.name,
            subject=entry.subject,
        )
        created = False
    if not created:
        if record.status in (
            TeacherClassCheckIn.Status.PRESENT_VERIFIED,
            TeacherClassCheckIn.Status.LATE_VERIFIED,
        ):
            # Already verified: a second tap is a no-op, never a duplicate.
            return record, False
        record = TeacherClassCheckIn.objects.select_for_update(of=('self',)).get(pk=record.pk)
        if record.status == TeacherClassCheckIn.Status.CANCELLED:
            raise ValidationError({'entry': 'That lesson was cancelled.'})
        record.entry = entry
        record.check_in_at = at
        record.minutes_late = max(late_by, 0)
        record.status = status
        record.gps_status = gps_status
        record.latitude = latitude
        record.longitude = longitude
        record.accuracy_meters = accuracy
        record.distance_meters = distance
        record.decided_by = None
        record.decision_note = ''
        record.decided_at = None
        record.save()
    return record, created


def missed_deadline_passed(school: School, day: dt.date, entry: TimetableEntry, now) -> bool:
    """Whether a session's check-in deadline has passed without excusing it."""
    if day != staff_attendance_service.local_day(school, now):
        # Only today's sessions can newly go missed; history is admin territory.
        return False
    scheduled = session_datetime(school, day, entry.period.start_time)
    deadline = scheduled + dt.timedelta(minutes=grace_minutes(school))
    return now >= deadline


@transaction.atomic
def sweep_school_day(school: School, day: dt.date, now=None) -> list[dict]:
    """Mark newly-missed sessions and alert the administrator, once each.

    Idempotent: rows carry `late_alert_sent` and notifications use a per-session
    dedupe key, so re-runs and overlapping workers change nothing. A teacher
    who checks in late afterwards converts the MISSED row into a verified
    late check-in with the real time preserved.
    """
    from . import events as event_service

    now = now or timezone.now()
    if not attendance_service.is_school_day(school, day):
        return []
    entries = (
        school.timetable_entries.filter(weekday=day.weekday())
        .select_related('period', 'class_obj', 'teacher')
        .order_by('period__sort_order', 'period__start_time')
    )
    existing = {
        (
            row.staff_id, row.weekday, row.scheduled_start,
            row.class_name, row.subject,
        ): row
        for row in TeacherClassCheckIn.objects.filter(school=school, date=day)
    }
    missed = []
    for entry in entries:
        if entry.teacher_id is None:
            continue
        if not missed_deadline_passed(school, day, entry, now):
            continue
        key = (
            entry.teacher_id, entry.weekday, entry.period.start_time,
            entry.class_obj.name, entry.subject,
        )
        record = existing.get(key)
        if record is not None:
            if record.status in (
                TeacherClassCheckIn.Status.PRESENT_VERIFIED,
                TeacherClassCheckIn.Status.LATE_VERIFIED,
                TeacherClassCheckIn.Status.UNVERIFIED,
                TeacherClassCheckIn.Status.CANCELLED,
            ):
                continue
            if record.late_alert_sent:
                continue
        if record is None:
            try:
                record, _ = TeacherClassCheckIn.objects.get_or_create(
                    school=school,
                    staff_id=entry.teacher_id,
                    date=day,
                    weekday=entry.weekday,
                    period_name=entry.period.name,
                    scheduled_start=entry.period.start_time,
                    scheduled_end=entry.period.end_time,
                    class_name=entry.class_obj.name,
                    subject=entry.subject,
                    room=entry.room or '',
                    defaults={
                        'entry': entry,
                        'status': TeacherClassCheckIn.Status.MISSED,
                        'gps_status': TeacherClassCheckIn.Gps.UNVERIFIED,
                    },
                )
            except IntegrityError:
                record = TeacherClassCheckIn.objects.get(
                    school=school,
                    staff_id=entry.teacher_id,
                    date=day,
                    weekday=entry.weekday,
                    scheduled_start=entry.period.start_time,
                    class_name=entry.class_obj.name,
                    subject=entry.subject,
                )
                if record.late_alert_sent or record.status in (
                    TeacherClassCheckIn.Status.PRESENT_VERIFIED,
                    TeacherClassCheckIn.Status.LATE_VERIFIED,
                    TeacherClassCheckIn.Status.UNVERIFIED,
                    TeacherClassCheckIn.Status.CANCELLED,
                ):
                    continue
        if record.status != TeacherClassCheckIn.Status.MISSED:
            record.status = TeacherClassCheckIn.Status.MISSED
            record.save(update_fields=['status', 'updated_at'])
        record.late_alert_sent = True
        record.late_alert_sent_at = now
        record.save(update_fields=['late_alert_sent', 'late_alert_sent_at', 'updated_at'])
        event_service.teacher_checkin_missed(record)
        missed.append({
            'staff': record.staff.full_name if hasattr(record, 'staff') else '',
            'class': record.class_name,
            'subject': record.subject,
        })
    return missed


@transaction.atomic
def cancel_session(*, user=None, school: School, record: TeacherClassCheckIn,
                   note='') -> TeacherClassCheckIn:
    record.status = TeacherClassCheckIn.Status.CANCELLED
    record.decided_by = user
    record.decision_note = (note or '')[:280]
    record.decided_at = timezone.now()
    record.save(update_fields=[
        'status', 'decided_by', 'decision_note', 'decided_at', 'updated_at',
    ])
    return record


@transaction.atomic
def override_status(
    *, user=None, school: School, record: TeacherClassCheckIn, status: str, note='',
) -> TeacherClassCheckIn:
    allowed = {
        TeacherClassCheckIn.Status.PRESENT_VERIFIED,
        TeacherClassCheckIn.Status.LATE_VERIFIED,
        TeacherClassCheckIn.Status.UNVERIFIED,
        TeacherClassCheckIn.Status.CANCELLED,
    }
    if status not in allowed:
        raise ValidationError({'status': 'That status cannot be set by override.'})
    if not (note or '').strip():
        raise ValidationError({'note': 'A reason is required for an override.'})
    record.status = status
    record.decided_by = user
    record.decision_note = note[:280]
    record.decided_at = timezone.now()
    record.save(update_fields=[
        'status', 'decided_by', 'decision_note', 'decided_at', 'updated_at',
    ])
    return record


def monitor_queryset(school: School, *, day=None, staff=None, class_name='',
                     subject='', statuses=(), search=''):
    """Admin board rows for a school, newest first, with filters applied."""
    queryset = (
        TeacherClassCheckIn.objects.filter(school=school)
        .select_related('staff', 'entry', 'decided_by')
        .order_by('-date', 'scheduled_start', 'staff__full_name')
    )
    if day is not None:
        queryset = queryset.filter(date=day)
    if staff is not None:
        queryset = queryset.filter(staff=staff)
    if class_name:
        queryset = queryset.filter(class_name__iexact=class_name.strip())
    if subject:
        queryset = queryset.filter(subject__icontains=subject.strip())
    if statuses:
        queryset = queryset.filter(status__in=list(statuses))
    if search:
        queryset = queryset.filter(staff__full_name__icontains=search.strip())
    return queryset
