"""Timetable assembly, conflict detection and role scoping (spec §22).

The module is deliberately one table of lessons (`TimetableEntry`) hung off the
school's bell schedule (`TimetablePeriod`). Everything here is about turning that
table into what a screen needs -- a week grid, a teacher's day, the reference
lists the editor offers -- and about refusing the three conflicts the spec calls
out (teacher, class, room).

Conflict policy: the three uniqueness constraints live on the model, so a
conflicting write can never be committed. This module's job is to catch the
attempt *first*, with a message a bursar can act on ("Amoah is already teaching
SSS 1 in P3"), and to translate the database error if two requests race past the
pre-check.
"""
from __future__ import annotations

import datetime

from django.db import IntegrityError, transaction
from django.db.models import Q

from rest_framework.exceptions import ValidationError

from records.constants import DEFAULT_PERIODS, DEFAULT_ROOMS, DEFAULT_SUBJECTS
from records.models import (
    Enrollment,
    SchoolClass,
    StaffMember,
    TimetableEntry,
    TimetablePeriod,
)

WEEKDAY_NAMES = TimetableEntry.WEEKDAY_NAMES
WEEKDAY_SHORT = TimetableEntry.WEEKDAY_SHORT


# --- bell schedule ---------------------------------------------------------

def ensure_periods(school) -> list[TimetablePeriod]:
    """Return the school's periods, seeding a default bell schedule if it has none.

    A school that has never touched the timetable still gets a usable day
    instead of an empty grid that looks broken. `get_or_create` keyed on
    (school, name) makes this idempotent and safe when two administrators open
    the timetable at once: the loser of the race re-reads the winner's row.
    """
    existing = list(school.timetable_periods.all())
    if existing:
        return existing
    for order, (name, start, end, is_break) in enumerate(DEFAULT_PERIODS, start=1):
        TimetablePeriod.objects.get_or_create(
            school=school,
            name=name,
            defaults={
                'start_time': start,
                'end_time': end,
                'sort_order': order,
                'is_break': is_break,
            },
        )
    return list(school.timetable_periods.all())


def teaching_days(school) -> list[int]:
    """Weekday numbers that are teaching days, derived from the school calendar.

    The timetable reuses `School.attendance_weekend_days` rather than adding its
    own weekend setting: a school that moved Saturday back into the teaching week
    for attendance must not keep a timetable that silently omits it.
    """
    weekend = {int(day) for day in (school.attendance_weekend_days or [5, 6])}
    return [day for day in range(7) if day not in weekend]


def period_payload(period: TimetablePeriod) -> dict:
    return {
        'id': str(period.pk),
        'name': period.name,
        'startTime': period.start_time.strftime('%H:%M'),
        'endTime': period.end_time.strftime('%H:%M'),
        'sortOrder': period.sort_order,
        'isBreak': period.is_break,
    }


# --- reference data for the editor ----------------------------------------

def known_rooms(school) -> list[str]:
    """Rooms already in use, plus the suggestions, deduplicated and sorted.

    Rooms are free text on the lesson row, so the list of rooms a school can pick
    is derived from what it has already booked rather than a separate table.
    """
    in_use = school.timetable_entries.exclude(room='').values_list('room', flat=True)
    return sorted(set(in_use) | set(DEFAULT_ROOMS))


def reference_payload(school) -> dict:
    classes = list(
        school.school_classes.filter(is_active=True)
        .order_by('sort_order', 'name')
        .select_related('level')
        .values('id', 'name', 'level__code')
    )
    return {
        'classes': [
            {'id': str(row['id']), 'name': row['name'], 'level': row['level__code']}
            for row in classes
        ],
        # Mirrors the academics module: `SchoolClass` is authoritative and the
        # JSON mirror on the school is kept in step with it.
        'classIds': {row['name']: str(row['id']) for row in classes},
        'subjects': list(school.subjects or DEFAULT_SUBJECTS),
        'teachers': [
            {'id': str(row['id']), 'name': row['full_name']}
            for row in school.staff.filter(
                status=StaffMember.Status.ACTIVE,
            ).order_by('full_name').values('id', 'full_name')
        ],
        'rooms': known_rooms(school),
    }


# --- scoping ---------------------------------------------------------------

def student_class_ids(user) -> list[str]:
    """Classes a pupil belongs to, from their ACTIVE enrollment.

    `Enrollment` is the source of truth for rosters (spec §35), so the timetable
    is scoped from it rather than from the `Student.class_name` mirror.
    """
    student_id = getattr(user, 'student_profile_id', None)
    if not student_id:
        return []
    return list(
        Enrollment.objects.filter(
            school_id=user.school_id,
            student_id=student_id,
            status=Enrollment.Status.ACTIVE,
        ).values_list('class_obj_id', flat=True).distinct()
    )


def linked_child_class_ids(user) -> list[str]:
    """Classes of a parent's children, from the accounts they are linked to.

    Parents see their own children only (spec §62, §65), so the timetable is
    scoped to the classes those children are actively enrolled in.
    """
    return list(
        Enrollment.objects.filter(
            school_id=user.school_id,
            student_id__in=user.linked_students.values_list('pk', flat=True),
            status=Enrollment.Status.ACTIVE,
        ).values_list('class_obj_id', flat=True).distinct()
    )


def staff_for_user(user) -> StaffMember | None:
    """The `StaffMember` row that belongs to a logged-in staff user, if any."""
    if not getattr(user, 'email', None):
        return None
    return StaffMember.objects.filter(
        school_id=user.school_id,
        email__iexact=user.email,
        status=StaffMember.Status.ACTIVE,
    ).first()


def teacher_id_for_user(user) -> str | None:
    staff = staff_for_user(user)
    return str(staff.pk) if staff else None


def resolve_scope(user, params) -> dict:
    """Work out which lessons this request may see.

    Roles without timetable.write (teachers, principals, pupils, parents) get a
    narrower default than an administrator, but an explicit `classId` still wins
    for the read-only roles: a teacher legitimately needs to see the timetable of
    a class they teach, and a parent needs to see their child's class. What no
    role may do is widen beyond their own school, and a pupil may never leave
    their own classes at all.
    """
    requested_class = (params.get('classId') or '').strip()
    requested_teacher = (params.get('teacherId') or '').strip()
    scope: dict = {'role': getattr(user, 'role', '')}

    if scope['role'] in ('student', 'parent'):
        allowed = (
            student_class_ids(user) if scope['role'] == 'student'
            else linked_child_class_ids(user)
        )
        allowed = [str(pk) for pk in allowed]
        if requested_class:
            if requested_class not in allowed:
                raise ValidationError({
                    'classId': 'You can only view the timetable of your own class.',
                })
            scope['classId'] = requested_class
        else:
            scope['classIds'] = allowed
        return scope

    if requested_class:
        scope['classId'] = requested_class
    elif requested_teacher:
        scope['teacherId'] = requested_teacher
    elif scope['role'] == 'teacher':
        own = teacher_id_for_user(user)
        if own:
            scope['teacherId'] = own
    return scope


def scoped_entries(school, scope: dict) -> list[TimetableEntry]:
    """Load the lessons in scope with their related rows prefetched.

    `select_related` on the three foreign keys keeps this at a fixed query count
    regardless of how many lessons come back -- the grid renders every slot's
    teacher and class name, so without it this would be the module's N+1.
    """
    queryset = school.timetable_entries.select_related(
        'period', 'class_obj', 'teacher',
    )
    if scope.get('classId'):
        queryset = queryset.filter(class_obj_id=scope['classId'])
    if scope.get('classIds') is not None:
        queryset = queryset.filter(class_obj_id__in=scope['classIds'])
    if scope.get('teacherId'):
        queryset = queryset.filter(teacher_id=scope['teacherId'])
    if scope.get('weekday') is not None:
        queryset = queryset.filter(weekday=scope['weekday'])
    return list(queryset.order_by('weekday', 'period__sort_order', 'class_obj__sort_order'))


# --- serialising ------------------------------------------------------------

def entry_payload(entry: TimetableEntry) -> dict:
    """One lesson, in the shape the frontend grid and the AI tools both use.

    `day`, `period`, `className`, `subject`, `teacher` and `room` are the
    original flat `TimetableSlot` keys and are kept so existing consumers keep
    working; `weekday`, `periodId` and `teacherId` are what the editor needs to
    address the row.
    """
    return {
        'id': str(entry.pk),
        'day': entry.weekday,
        'weekday': entry.weekday,
        'dayName': WEEKDAY_NAMES[entry.weekday],
        'dayShort': WEEKDAY_SHORT[entry.weekday],
        'period': entry.period.name,
        'periodId': str(entry.period_id),
        'classId': str(entry.class_obj_id),
        'className': entry.class_obj.name,
        'subject': entry.subject,
        # A lesson can exist with no teacher yet, which is why this is text.
        'teacher': entry.teacher.full_name if entry.teacher else '',
        'teacherId': str(entry.teacher_id) if entry.teacher_id else '',
        'room': entry.room,
    }


def grid_payload(user, school, params) -> dict:
    """Everything the timetable screen needs in a single round trip.

    The reference lists are included because the editor cannot offer a class,
    subject, teacher or room it has not been told about, and a second endpoint
    would only add a request waterfall on a screen that must feel immediate.
    """
    scope = resolve_scope(user, params)
    periods = ensure_periods(school)
    entries = scoped_entries(school, scope)
    return {
        'session': school.current_session,
        'term': school.current_term,
        'days': teaching_days(school),
        'dayNames': [WEEKDAY_NAMES[day] for day in teaching_days(school)],
        'dayShortNames': [WEEKDAY_SHORT[day] for day in teaching_days(school)],
        'periods': [period_payload(period) for period in periods],
        'entries': [entry_payload(entry) for entry in entries],
        'scope': {
            'classId': scope.get('classId') or '',
            'teacherId': scope.get('teacherId') or '',
        },
        **reference_payload(school),
    }


# --- writes ----------------------------------------------------------------

def _resolve_period(school, period_id) -> TimetablePeriod:
    period = TimetablePeriod.objects.filter(school=school, pk=period_id).first()
    if period is None:
        raise ValidationError({'periodId': 'That period is not part of this school\'s day.'})
    return period


def _resolve_class(school, class_id) -> SchoolClass:
    school_class = SchoolClass.objects.filter(school=school, pk=class_id).first()
    if school_class is None:
        raise ValidationError({'classId': 'That class does not exist in this school.'})
    return school_class


def _resolve_teacher(school, teacher_id):
    teacher_id = (str(teacher_id or '')).strip()
    if not teacher_id:
        return None
    teacher = StaffMember.objects.filter(school=school, pk=teacher_id).first()
    if teacher is None:
        raise ValidationError({'teacherId': 'That teacher does not exist in this school.'})
    return teacher


def _conflict_message(entry: TimetableEntry, *, class_obj, teacher, room, period, weekday) -> None:
    """Raise the first conflict the candidate lesson would create.

    Checked against other rows rather than caught from the database so the
    message can name the class and period already booked, which is what makes the
    timetable buildable by hand without guessing.
    """
    day = WEEKDAY_NAMES[weekday]
    same_slot = TimetableEntry.objects.filter(
        school=entry.school,
        weekday=weekday,
        period=period,
    )
    # A brand new entry has no pk yet, and `exclude(pk=None)` would compile to a
    # NOT NULL test rather than "skip nothing", so the clause is conditional.
    if entry.pk:
        same_slot = same_slot.exclude(pk=entry.pk)

    clash = same_slot.filter(class_obj=class_obj).first()
    if clash is not None:
        raise ValidationError({
            'classId': f'{class_obj.name} already has a lesson in {period.name} on {day}.',
        })

    if teacher is not None:
        clash = same_slot.filter(teacher=teacher).first()
        if clash is not None:
            raise ValidationError({
                'teacherId': f'{teacher.full_name} is already teaching '
                             f'{clash.class_obj.name} in {period.name} on {day}.',
            })

    if room:
        clash = same_slot.filter(room=room).first()
        if clash is not None:
            raise ValidationError({
                'room': f'{room} is already taken by {clash.class_obj.name} '
                        f'in {period.name} on {day}.',
            })


def _write(data: dict, *, school, instance: TimetableEntry | None):
    """Validate and save one lesson.

    A PATCH is partial: any field the caller omits keeps the value it already
    has on `instance`. The editor moves one lesson at a time ("change this to
    Basic Science") and should not have to resend the whole row to do it, and
    resending it would race with anybody else editing the same lesson.
    """
    weekday = data.get('weekday', data.get('day'))
    if weekday is None and instance is not None:
        weekday = instance.weekday
    if weekday is None:
        raise ValidationError({'weekday': 'Pick a day for this lesson.'})
    try:
        weekday = int(weekday)
    except (TypeError, ValueError):
        raise ValidationError({'weekday': 'Weekday numbers run from 0 (Monday) to 6 (Sunday).'})
    if weekday < 0 or weekday > 6:
        raise ValidationError({'weekday': 'Weekday numbers run from 0 (Monday) to 6 (Sunday).'})

    period_id = data.get('periodId')
    if period_id is None and instance is not None:
        period_id = instance.period_id
    period = _resolve_period(school, period_id)
    if period.is_break:
        raise ValidationError({'periodId': f'{period.name} is a break and cannot hold a lesson.'})

    class_id = data.get('classId')
    if class_id is None and instance is not None:
        class_id = instance.class_obj_id
    class_obj = _resolve_class(school, class_id)

    # `teacherId` is checked for presence rather than truthiness so an explicit
    # empty string unassigns the teacher, which is how the editor clears it.
    if 'teacherId' in data:
        teacher = _resolve_teacher(school, data.get('teacherId'))
    else:
        teacher = instance.teacher if instance is not None else None

    if 'subject' in data:
        subject = (data.get('subject') or '').strip()
    else:
        subject = (instance.subject if instance is not None else '').strip()
    if not subject:
        raise ValidationError({'subject': 'A subject is required.'})

    if 'room' in data:
        room = (data.get('room') or '').strip()
    else:
        room = (instance.room if instance is not None else '').strip()

    entry = instance or TimetableEntry(school=school)
    entry.period = period
    entry.class_obj = class_obj
    entry.teacher = teacher
    entry.subject = subject
    entry.room = room
    entry.weekday = weekday

    # Conflict check runs BEFORE full_clean on purpose. `full_clean` validates
    # the model's unique constraints too, and would report a double-booking as
    # "the fields school, weekday, period, class_obj must make a unique set",
    # which tells a bursar nothing. Doing the friendly check first means the
    # actionable message is the one the caller actually sees.
    _conflict_message(
        entry, class_obj=class_obj, teacher=teacher, room=room,
        period=period, weekday=weekday,
    )
    # `validate_constraints=False` for the same reason: uniqueness is already
    # covered above with a better message, and the DB still enforces it. The
    # cross-school and break rules in `Model.clean` do still run here.
    entry.full_clean(exclude=['school'], validate_constraints=False)

    try:
        with transaction.atomic():
            entry.save()
    except IntegrityError as exc:
        # Two administrators saved the same slot at the same moment: the
        # pre-check both passed, the constraint caught it.
        raise ValidationError({
            'weekday': 'That slot was just taken by someone else. '
                       'Reload the timetable and try again.',
        }) from exc
    return entry


def create_entry(school, data: dict) -> TimetableEntry:
    return _write(data, school=school, instance=None)


def update_entry(school, entry: TimetableEntry, data: dict) -> TimetableEntry:
    return _write(data, school=school, instance=entry)


def delete_entry(school, entry: TimetableEntry) -> None:
    if entry.school_id != school.id:
        raise ValidationError({'id': 'That lesson belongs to another school.'})
    entry.delete()


def create_period(school, data: dict) -> TimetablePeriod:
    """Add a bell to the school's day.

    `sort_order` defaults to one past the current last period so a newly added
    period lands at the end of the day, which is what "add a period" means to an
    administrator.
    """
    name = (data.get('name') or '').strip()
    if not name:
        raise ValidationError({'name': 'Give the period a name, e.g. "P1" or "Break".'})
    if school.timetable_periods.filter(name=name).exists():
        raise ValidationError({'name': f'{name} is already part of this school\'s day.'})

    start, end = _parse_period_times(data)
    period = TimetablePeriod(
        school=school,
        name=name,
        start_time=start,
        end_time=end,
        sort_order=_int_or_default(data.get('sortOrder'), _next_sort_order(school)),
        is_break=bool(data.get('isBreak')),
    )
    period.full_clean(exclude=['school'], validate_constraints=False)
    _assert_no_overlap(school, period)
    period.save()
    return period


def update_period(school, period: TimetablePeriod, data: dict) -> TimetablePeriod:
    """Change one bell. Times must keep the whole school inside them.

    Overlapping periods are refused: two periods that overlap make "which lesson
    is in P3 at 10:15?" ambiguous, and the teacher's day is derived from these
    times. A school that genuinely runs parallel sessions at the same hour can
    still do so, because `isBreak` rows are exempt -- a break is a divider, not a
    competing lesson slot.
    """
    if 'name' in data:
        name = (data.get('name') or '').strip()
        if not name:
            raise ValidationError({'name': 'Give the period a name, e.g. "P1" or "Break".'})
        clash = school.timetable_periods.filter(name=name).exclude(pk=period.pk)
        if clash.exists():
            raise ValidationError({'name': f'{name} is already part of this school\'s day.'})
        period.name = name

    if 'startTime' in data or 'endTime' in data:
        start, end = _parse_period_times(
            {
                'startTime': data.get('startTime', period.start_time.strftime('%H:%M')),
                'endTime': data.get('endTime', period.end_time.strftime('%H:%M')),
            },
        )
        period.start_time = start
        period.end_time = end

    if 'sortOrder' in data:
        period.sort_order = _int_or_default(data.get('sortOrder'), period.sort_order)
    if 'isBreak' in data:
        period.is_break = bool(data.get('isBreak'))

    period.full_clean(exclude=['school'], validate_constraints=False)
    _assert_no_overlap(school, period)
    period.save()
    return period


def delete_period(school, period: TimetablePeriod) -> None:
    if period.school_id != school.id:
        raise ValidationError({'id': 'That period belongs to another school.'})
    period.delete()


def _next_sort_order(school) -> int:
    last = school.timetable_periods.order_by('-sort_order').values_list(
        'sort_order', flat=True,
    ).first()
    return (last or 0) + 1


def _int_or_default(raw, fallback: int) -> int:
    try:
        return int(raw)
    except (TypeError, ValueError):
        return fallback


def _parse_period_times(data: dict):
    """Parse `HH:MM` start/end, rejecting anything that is not a real time."""

    def parse(raw, field):
        text = str(raw or '').strip()
        try:
            return datetime.time.fromisoformat(text)
        except (TypeError, ValueError):
            raise ValidationError({
                field: f'"{text}" is not a time. Use 24-hour HH:MM, e.g. 08:30.',
            })

    start = parse(data.get('startTime'), 'startTime')
    end = parse(data.get('endTime'), 'endTime')
    if end <= start:
        raise ValidationError({'endTime': 'The period must end after it starts.'})
    return start, end


def _assert_no_overlap(school, period: TimetablePeriod) -> None:
    """Refuse a bell that overlaps another lesson period in the same school."""
    overlapping = school.timetable_periods.exclude(pk=period.pk).filter(
        start_time__lt=period.end_time,
        end_time__gt=period.start_time,
    )
    for other in overlapping:
        # A break may sit inside a lesson window on purpose (it is a divider),
        # so only two lesson periods are a real contradiction.
        if other.is_break or period.is_break:
            continue
        raise ValidationError({
            'startTime': f'{period.name} ({period.start_time:%H:%M}-{period.end_time:%H:%M}) '
                         f'overlaps {other.name} '
                         f'({other.start_time:%H:%M}-{other.end_time:%H:%M}).',
        })


# --- AI tool backing -------------------------------------------------------

def teacher_week(user) -> dict:
    """A teacher's week, for the AI assistant (spec §22).

    Returns every lesson the teacher is timetabled for, grouped by day so the
    assistant can answer "what do I teach on Wednesday?" without the model
    having to reshape a flat list.
    """
    school_id = user.school_id
    staff = staff_for_user(user)
    if staff is None:
        return {'teacher': user.get_full_name() or user.email, 'days': [], 'lessonCount': 0}

    entries = list(
        TimetableEntry.objects.filter(school_id=school_id, teacher=staff)
        .select_related('period', 'class_obj')
        .order_by('weekday', 'period__sort_order')
    )
    by_day: dict[int, list[dict]] = {}
    for entry in entries:
        by_day.setdefault(entry.weekday, []).append({
            'period': entry.period.name,
            'startTime': entry.period.start_time.strftime('%H:%M'),
            'endTime': entry.period.end_time.strftime('%H:%M'),
            'className': entry.class_obj.name,
            'subject': entry.subject,
            'room': entry.room,
        })
    return {
        'teacher': staff.full_name,
        'days': [
            {'weekday': day, 'day': WEEKDAY_NAMES[day], 'lessons': by_day[day]}
            for day in sorted(by_day)
        ],
        'lessonCount': len(entries),
    }


def class_week(school_id, class_obj: SchoolClass) -> dict:
    """A class's week, for the AI assistant."""
    entries = list(
        TimetableEntry.objects.filter(school_id=school_id, class_obj=class_obj)
        .select_related('period', 'teacher')
        .order_by('weekday', 'period__sort_order')
    )
    by_day: dict[int, list[dict]] = {}
    for entry in entries:
        by_day.setdefault(entry.weekday, []).append({
            'period': entry.period.name,
            'startTime': entry.period.start_time.strftime('%H:%M'),
            'endTime': entry.period.end_time.strftime('%H:%M'),
            'subject': entry.subject,
            'teacher': entry.teacher.full_name if entry.teacher else '',
            'room': entry.room,
        })
    return {
        'className': class_obj.name,
        'days': [
            {'weekday': day, 'day': WEEKDAY_NAMES[day], 'lessons': by_day[day]}
            for day in sorted(by_day)
        ],
        'lessonCount': len(entries),
    }
