"""Parent self-service: linked children, their attendance and their promotion.

The authorisation rule this module exists to enforce (spec 62, 65)::

    A parent reaches a child ONLY through `User.linked_students`.

Never through a name, a phone number or an id the caller supplies. The school
filter is applied on top of the link even though the link is explicit, so a
misconfigured cross-school link still cannot leak, and every lookup here
answers ``None`` rather than raising so the view can return 404 without
confirming that some other family's student id exists.
"""
from __future__ import annotations

from datetime import date

from django.db.models import Count, Q, QuerySet

from ..models import (
    AttendanceRecord,
    Enrollment,
    Student,
)
from . import academic as academic_service
from . import attendance_rate
from . import promotion as promotion_service
from . import public_refs


def linked_child(user, student_id) -> Student | None:
    """One child of this parent, or None when the id is not theirs.

    An unlinked id and an id from another school are indistinguishable here -
    both come back as None, so the endpoint answers 404 for each and a parent
    can never enumerate another family's children.
    """
    public_id = public_refs.parse_public_id(student_id)
    if public_id is None:
        return None
    return (
        Student.objects
        .filter(school_id=user.school_id, guardian_accounts=user, public_id=public_id)
        .first()
    )


# The calendar bounds of an academic session live in the attendance-rate
# service now; they are re-exported here because `parent_portal.session_window`
# is the name the report card and other callers already import.
session_window = attendance_rate.session_window


def attendance_for(student, *, session=None, date_from=None, date_to=None) -> dict:
    """Attendance summary plus the most recent register lines for one child.

    The rate comes from the shared `attendance_rate` service so a parent sees
    exactly the same number as the admin students list and the report card.
    """
    counts = attendance_rate.counts_for_student(
        student, session=session, date_from=date_from, date_to=date_to,
    )

    recent = (
        AttendanceRecord.objects
        .filter(student=student, school_id=student.school_id)
        .select_related('class_obj')
        .order_by('-date')[:60]
    )

    return {
        'summary': {
            'recorded': counts['recorded'],
            'present': counts['present'],
            'late': counts['late'],
            'absent': counts['absent'],
            'excused': counts['excused'],
            'attendanceRate': attendance_rate.rate_from_counts(counts),
        },
        'records': [
            {
                'date': record.date.isoformat(),
                'status': record.status,
                'className': record.class_name,
            }
            for record in recent
        ],
    }


def enrollment_history(student) -> list[dict]:
    """Every enrollment row for the child, newest first.

    The history is never rewritten: a class the child moved out of still shows
    its own row and its own status, so the parent sees the record rather than
    only the current state.
    """
    rows = (
        Enrollment.objects
        .filter(student=student)
        .select_related('academic_session', 'class_obj', 'section')
        .order_by('-academic_session__start_year', '-created_at')
    )
    return [
        {
            'sessionId': str(row.academic_session_id),
            'session': row.academic_session.name,
            'className': row.class_obj.name,
            'arm': row.section.name if row.section_id else '',
            'status': row.status,
            'flaggedForReview': row.flagged_for_review,
            'reviewNote': row.review_note,
        }
        for row in rows
    ]


def promotion_for(student) -> dict:
    """The promotion suggestion for one child, with the rule that produced it.

    A suggestion is derived, never stored: it comes from the same
    `promotion.candidates_for` calculation the administrator's promotion screen
    runs, so a parent and the head teacher cannot see two different answers for
    the same child.
    """
    school = student.school
    enrollment = (
        Enrollment.objects
        .filter(student=student, status=Enrollment.Status.ACTIVE)
        .select_related('academic_session', 'class_obj', 'section')
        .order_by('-academic_session__start_year')
        .first()
    )
    session = (
        enrollment.academic_session if enrollment is not None
        else academic_service.current_session(school)
    )
    payload = {
        'enrolled': enrollment is not None,
        'session': session.name if session is not None else '',
        'className': enrollment.class_obj.name if enrollment is not None else student.class_name,
        'arm': enrollment.section.name if enrollment is not None and enrollment.section_id else student.arm,
        'suggested': None,
        'reason': '',
        'average': None,
        'attendanceRate': None,
        'failedSubjects': 0,
        'subjectsAssessed': 0,
        'isFinalClass': False,
        'nextClass': None,
        'policy': None,
        'history': enrollment_history(student),
    }
    if enrollment is None or session is None:
        payload['reason'] = 'No active enrollment yet, so no promotion can be suggested.'
        return payload

    policy = promotion_service.policy_for(school)
    payload['policy'] = {
        'promoteMinAverage': float(policy.promote_min_average),
        'promoteMinAttendance': float(policy.promote_min_attendance),
        'conditionalMinAverage': float(policy.conditional_min_average),
        'conditionalMinAttendance': float(policy.conditional_min_attendance),
        'conditionalMaxFailedSubjects': policy.conditional_max_failed_subjects,
    }
    destination = promotion_service.next_class_for(enrollment.class_obj)
    payload['nextClass'] = destination.name if destination is not None else None
    payload['isFinalClass'] = destination is None

    for candidate in promotion_service.candidates_for(school, session, enrollment.class_obj, policy):
        if candidate['studentId'] != str(student.public_id):
            continue
        payload.update({
            'suggested': candidate['suggested'],
            'reason': candidate['reason'],
            'average': candidate['average'],
            'attendanceRate': candidate['attendanceRate'],
            'failedSubjects': candidate['failedSubjects'],
            'subjectsAssessed': candidate['subjectsAssessed'],
            'isFinalClass': candidate['isFinalClass'],
        })
        break
    else:
        payload['reason'] = 'This child is not on an active class roster for the session.'
    return payload


def current_session_for(student):
    """The session a child's class belongs to: their enrollment's, else today's."""
    enrollment = (
        Enrollment.objects
        .filter(student=student, status=Enrollment.Status.ACTIVE)
        .select_related('academic_session')
        .order_by('-academic_session__start_year')
        .first()
    )
    if enrollment is not None:
        return enrollment.academic_session
    return academic_service.current_session(student.school)
