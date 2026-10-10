"""Daily attendance: school calendar, class teachers, rosters and submission.

Attendance is taken **once per school day** for a whole class, in a single
transaction. The roster is always resolved from ACTIVE `Enrollment` rows
(spec §35) — `Student.class_name` is a denormalised mirror and is never used to
decide who may be marked.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field

from django.db import transaction
from django.db.models import Count, QuerySet, Q
from django.shortcuts import get_object_or_404
from rest_framework.exceptions import PermissionDenied, ValidationError

from schools.models import School

from ..models import (
    AcademicSession,
    AttendanceRecord,
    ClassTeacherAssignment,
    Enrollment,
    SchoolClass,
    Section,
    StaffMember,
    Student,
)
from . import academic as academic_service


class DuplicateRegister(Exception):
    """A register already exists for this class and day.

    Carries the existing marks so the caller can return them with a 409 and the
    client can show the taken register instead of starting a fresh one.
    """

    def __init__(self, existing: dict[str, str]):
        super().__init__('Attendance has already been recorded for this class today.')
        self.existing = existing


@dataclass
class RegisterResult:
    saved: int = 0
    skipped: int = 0
    record_ids: list[int] = field(default_factory=list)
    by_status: dict[str, int] = field(default_factory=dict)


# ── School calendar ─────────────────────────────────────────────────────────

def is_school_day(school: School, day: dt.date) -> bool:
    """Whether attendance is expected on `day` for this school.

    Weekend days come from `School.attendance_weekend_days` (Saturday/Sunday by
    default) and explicit closures from `School.non_school_days` (ISO strings).
    """
    weekend = school.attendance_weekend_days
    if not isinstance(weekend, list):
        weekend = [5, 6]
    if day.weekday() in weekend:
        return False
    closed = school.non_school_days
    if isinstance(closed, list) and day.isoformat() in closed:
        return False
    return True


# ── Class teachers ──────────────────────────────────────────────────────────

def class_teacher_for(
    school: School, class_obj: SchoolClass, session: AcademicSession | None,
) -> ClassTeacherAssignment | None:
    assignments = ClassTeacherAssignment.objects.filter(school=school, class_obj=class_obj)
    if session is not None:
        assignments = assignments.filter(academic_session=session)
    return assignments.select_related('staff').first()


def can_submit_for(user, school: School, class_obj: SchoolClass) -> bool:
    """Whether `user` may submit `class_obj`'s register.

    School admins always may (they are the override/emergency path). A teacher
    may only submit for classes they are the designated class teacher of — being
    a subject teacher for the class is not enough (spec §attendance).

    This issues its own query. Screens that already hold the `ClassTeacherAssignment`
    should compare against that row instead, rather than paying twice.
    """
    if user.role == 'school_admin':
        return True
    if user.role != 'teacher':
        return False
    staff = getattr(user, 'staff_profile', None)
    if staff is None or staff.status != 'active':
        return False
    return ClassTeacherAssignment.objects.filter(
        school=school,
        class_obj=class_obj,
        staff=staff,
        academic_session=academic_service.current_session(school),
    ).exists()


def require_can_submit(user, school: School, class_obj: SchoolClass) -> None:
    if not can_submit_for(user, school, class_obj):
        raise PermissionDenied(
            'Only this class\'s designated class teacher can submit its attendance register.'
        )


# ── Class resolution ────────────────────────────────────────────────────────

def resolve_class(school: School, name: str) -> SchoolClass | None:
    """The school's `SchoolClass` with this name, or None.

    A class the school has configured but never provisioned as a `SchoolClass`
    row resolves to None rather than raising: it belongs to this school, so the
    caller returns an empty roster instead of a misleading 404. Cross-school and
    wholly unknown names are rejected by the caller's school scoping.
    """
    return school.school_classes.filter(name=(name or '').strip()).first()


def is_configured_class(school: School, name: str) -> bool:
    """Whether `name` is a class this school has configured at all."""
    name = (name or '').strip()
    return bool(name) and name in (school.classes or [])


def resolve_section(school: School, class_obj: SchoolClass, name: str) -> Section | None:
    return school.sections.filter(class_obj=class_obj, name=(name or '').strip()).first()


# ── Roster ──────────────────────────────────────────────────────────────────

def _active_enrollments(
    school: School,
    class_obj: SchoolClass,
    section: Section | None,
    session: AcademicSession | None,
):
    """Enrollments that make up a class register, with student/section joined.

    The single source of both the roster and the public-id -> primary-key
    mapping used when a register is submitted, so the two can never disagree on
    who is allowed to be marked.
    """
    queryset = Enrollment.objects.filter(
        school=school, status=Enrollment.Status.ACTIVE, class_obj=class_obj,
    ).select_related('student', 'section')
    if session is not None:
        queryset = queryset.filter(academic_session=session)
    if section is not None:
        queryset = queryset.filter(section=section)
    return queryset.filter(student__status=Student.Status.ACTIVE)


def roster_for(
    school: School,
    class_obj: SchoolClass | None,
    section: Section | None,
    session: AcademicSession | None,
) -> list[dict]:
    """Students who may be marked in this class/section, from active enrollments.

    Two queries total: the enrollments (with `select_related`) and nothing else.
    `Student.class_name` is never consulted, so a stale mirror cannot put a
    student in the wrong register.

    An unprovisioned class name resolves to `class_obj=None`, which is an EMPTY
    register — never "every student in the school". Leaving the filters off in
    that case would hand one class the whole school's roster.
    """
    if class_obj is None:
        return []
    queryset = _active_enrollments(school, class_obj, section, session)

    return [
        {
            'id': str(item.student.public_id),
            'firstName': item.student.first_name,
            'lastName': item.student.last_name,
            'admissionNumber': item.student.admission_number,
            'gender': item.student.gender,
            'status': item.student.status,
            'className': class_obj.name if class_obj else '',
            'arm': item.section.name if item.section_id else '',
        }
        for item in queryset
    ]


def existing_marks(
    school: School, class_obj: SchoolClass | None, day: dt.date,
) -> dict[str, str]:
    """`{student_id: status}` for a class on a day. Empty when not taken.

    Rows written before `class_obj` existed carry a NULL FK and are matched on
    the `class_name` mirror instead, so a day's register stays visible across the
    migration rather than appearing "not taken".
    """
    if class_obj is None:
        return {}
    queryset = AttendanceRecord.objects.filter(
        school=school, date=day,
    ).filter(
        Q(class_obj=class_obj) | Q(class_obj__isnull=True, class_name=class_obj.name)
    ).select_related('student')
    return {str(record.student.public_id): record.status for record in queryset}


# ── Submission ──────────────────────────────────────────────────────────────

@transaction.atomic
def submit_register(
    *,
    user,
    school: School,
    class_obj: SchoolClass,
    day: dt.date,
    records: list[dict],
    section: Section | None = None,
) -> RegisterResult:
    """Write a whole-class register for one school day, atomically.

    Validates the school, class, section and enrollment membership before writing
    anything, so a crafted student id cannot mark someone who is not in the
    class. A register that already exists raises `DuplicateRegister` rather than
    creating a second one.
    """
    require_can_submit(user, school, class_obj)
    if not is_school_day(school, day):
        raise ValidationError({
            'date': f'{day.isoformat()} is not a school day for this school.',
        })

    # Lock the school row so two concurrent submissions for the same class/day
    # cannot both pass the existence check below.
    School.objects.select_for_update().get(id=school.id)

    already = existing_marks(school, class_obj, day)
    if already:
        raise DuplicateRegister(already)

    # Public id -> primary key, so a submitted `studentId` is mapped back to the
    # real student and a crafted id for a pupil outside this class is skipped.
    roster = {
        str(enrollment.student.public_id): enrollment.student_id
        for enrollment in _active_enrollments(
            school, class_obj, section, academic_service.current_session(school),
        )
    }
    if not roster:
        raise ValidationError({
            'className': 'This class has no students with an active enrollment, '
                         'so attendance cannot be recorded for it.',
        })

    result = RegisterResult()
    valid_statuses = set(AttendanceRecord.Status.values)
    to_create = []

    for item in records:
        raw_id = item.get('studentId')
        student_id = roster.get(str(raw_id)) if raw_id is not None else None
        if student_id is None:
            result.skipped += 1
            continue
        mark = (item.get('status') or AttendanceRecord.Status.PRESENT).strip()
        if mark not in valid_statuses:
            raise ValidationError({'records': f'"{mark}" is not a valid attendance status.'})
        to_create.append(AttendanceRecord(
            school=school,
            student_id=student_id,
            class_obj=class_obj,
            class_name=class_obj.name,
            date=day,
            status=mark,
            submitted_by=user,
        ))

    AttendanceRecord.objects.bulk_create(to_create)
    result.saved = len(to_create)
    result.record_ids = [record.id for record in to_create]
    result.by_status = _count_by_status(school, class_obj, day)
    return result


def _count_by_status(school: School, class_obj: SchoolClass, day: dt.date) -> dict[str, int]:
    return {
        row['status']: row['n']
        for row in AttendanceRecord.objects.filter(
            school=school, class_obj=class_obj, date=day,
        ).values('status').annotate(n=Count('id'))
    }


@transaction.atomic
def correct_record(*, user, school: School, record_id: int, new_status: str, reason: str) -> dict:
    """Amend a taken attendance line, returning the audit before/after payload.

    Corrections never mutate silently: the caller writes an AuditLog row from the
    returned dict, so who changed what and why is always recoverable.
    """
    if new_status not in AttendanceRecord.Status.values:
        raise ValidationError({'status': f'"{new_status}" is not a valid attendance status.'})
    reason = (reason or '').strip()
    if not reason:
        raise ValidationError({'reason': 'A reason is required to correct attendance.'})

    record = get_object_or_404(
        AttendanceRecord.objects.select_related('student'), id=record_id, school=school,
    )
    previous = record.status
    if previous == new_status:
        return {'changed': False, 'previousStatus': previous, 'status': new_status}

    record.status = new_status
    record.save(update_fields=['status', 'updated_at'])
    return {'changed': True, 'previousStatus': previous, 'status': new_status, 'reason': reason}


# ── Reporting ───────────────────────────────────────────────────────────────

def overview_for(school: School, day: dt.date, *, class_objs=None) -> list[dict]:
    """Per-class submitted / not-submitted summary for one day.

    Two aggregate queries total regardless of how many classes there are, so the
    admin board scales with the school rather than with the timetable.
    """
    classes = class_objs if class_objs is not None else school.school_classes.filter(is_active=True)
    class_list = list(classes.order_by('sort_order', 'name'))

    result = {
        class_obj.id: {
            'classId': class_obj.id,
            'className': class_obj.name,
            'submitted': 0,
            'present': 0, 'absent': 0, 'late': 0, 'excused': 0,
        }
        for class_obj in class_list
    }

    day_records = AttendanceRecord.objects.filter(school=school, date=day)
    for row in day_records.values('class_obj', 'status').annotate(n=Count('id')):
        target = result.get(row['class_obj'])
        if target is not None:
            target['submitted'] += row['n']
            target[row['status']] = target.get(row['status'], 0) + row['n']

    return [result[class_obj.id] for class_obj in class_list]


def assign_class_teacher(
    school: School, *, class_obj: SchoolClass, staff: StaffMember | None = None,
    session: AcademicSession | None = None, assign: bool = True,
) -> ClassTeacherAssignment | None:
    """Designate (or clear) the class teacher responsible for a register.

    This is the only way a teacher can become able to submit, so it has to be a
    deliberate act by an administrator rather than a side effect of adding a
    subject to a staff record: being a subject teacher is not being responsible
    for the register.

    Replaces any existing designation for the same class and session rather than
    raising, because moving a class teacher at the start of a term is routine
    administration. Returns the assignment, or None when clearing.
    """
    session = session or academic_service.current_session(school)
    if session is None:
        raise ValidationError({
            'session': 'This school has no academic session, so a class teacher '
                       'cannot be designated.',
        })

    if not assign:
        ClassTeacherAssignment.objects.filter(
            school=school, class_obj=class_obj, academic_session=session,
        ).delete()
        return None

    if staff is None:
        raise ValidationError({'staff': 'Choose the teacher responsible for this class.'})
    if staff.school_id != school.id:
        raise ValidationError({'staff': 'That staff member belongs to another school.'})

    assignment, _ = ClassTeacherAssignment.objects.update_or_create(
        school=school,
        class_obj=class_obj,
        academic_session=session,
        defaults={'staff': staff},
    )
    # A class teacher takes the register, so mirror the class onto the staff
    # record's class list. Without this the teacher's own "my classes" list -
    # which is what the register screen and the assistant scope both read - would
    # not include the class they are now responsible for.
    names = set(staff.classes or [])
    if class_obj.name not in names:
        staff.classes = sorted(names | {class_obj.name})
        staff.save(update_fields=['classes'])
    return assignment


def teacher_visible_class_ids(
    school: School, user, session: AcademicSession | None = None,
) -> set[int] | None:
    """The class ids `user` may read attendance for, or None for "the whole school".

    `attendance.read` is granted to every teacher in the school, which is right for
    the register screen (where the class is chosen from their own classes) but is
    wrong for a free-text history search: without this, "show me this student's
    attendance" would read any student in the school.

    Read access is wider than submit access - a subject teacher may READ the class
    they teach. It is narrower than "everyone": a teacher sees the classes on their
    staff record plus the classes they are the designated class teacher of.
    """
    if user.role != 'teacher':
        return None

    staff = getattr(user, 'staff_profile', None)
    if staff is None or staff.status != StaffMember.Status.ACTIVE:
        return set()

    ids = set(
        school.school_classes.filter(
            name__in=staff.classes or [],
        ).values_list('id', flat=True)
    )
    assignments = ClassTeacherAssignment.objects.filter(school=school, staff=staff)
    if session is not None:
        assignments = assignments.filter(academic_session=session)
    ids.update(assignments.values_list('class_obj_id', flat=True))
    return ids


def history_class_ids_for_student(
    school: School, student: Student, allowed_class_ids: set[int],
) -> set[int]:
    """The visible classes for one student's history, or empty if they see none.

    Derived from the student's ACTIVE enrollments, which is the same roster truth
    the register uses. A student who is not enrolled anywhere the caller can see
    resolves to an empty set, so the caller answers 404 rather than leaking an
    empty-but-confirmed record. Returns the allowed ids unchanged when the caller
    is allowed to see the whole school.
    """
    enrolled = set(
        Enrollment.objects.filter(
            school=school, student=student, status=Enrollment.Status.ACTIVE,
        ).values_list('class_obj_id', flat=True)
    ) & allowed_class_ids
    if enrolled:
        return enrolled

    # Not currently enrolled (left, graduated, mid-transfer): fall back to the
    # classes their own attendance history names, still intersected with what
    # the caller may read.
    historic = set(
        AttendanceRecord.objects.filter(school=school, student=student)
        .exclude(class_obj__isnull=True)
        .values_list('class_obj_id', flat=True)
    )
    return historic & allowed_class_ids


def history_for(
    school: School, *, student=None, class_obj=None, date_from=None, date_to=None,
    allowed_class_ids: set[int] | None = None,
) -> QuerySet[AttendanceRecord]:
    queryset = AttendanceRecord.objects.filter(school=school).select_related(
        'student', 'class_obj', 'submitted_by',
    )
    if student is not None:
        queryset = queryset.filter(student=student)
    if class_obj is not None:
        queryset = queryset.filter(class_obj=class_obj)
    if date_from is not None:
        queryset = queryset.filter(date__gte=date_from)
    if date_to is not None:
        queryset = queryset.filter(date__lte=date_to)
    if allowed_class_ids is not None:
        # `class_obj` IS NULL on legacy rows predating the FK, so class-name
        # matching is used for those; otherwise a teacher would be unable to
        # read their own school's pre-migration history.
        if not allowed_class_ids:
            return queryset.none()
        visible_names = list(
            school.school_classes.filter(id__in=allowed_class_ids)
            .values_list('name', flat=True)
        )
        queryset = queryset.filter(
            Q(class_obj_id__in=allowed_class_ids)
            | Q(class_obj__isnull=True, class_name__in=visible_names)
        )
    return queryset.order_by('-date', 'student__first_name', '-id')
