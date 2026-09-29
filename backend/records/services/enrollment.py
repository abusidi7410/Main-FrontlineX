"""Enrollment activation and roster resolution (spec §32–§35, §47–§49).

The invariant this module protects (spec §35, §97)::

    NO ACTIVE ENROLLMENT  →  NO CLASS ROSTER VISIBILITY

A student reaches a class roster only through an ``Enrollment`` row in the
``ACTIVE`` state. ``Student.class_name`` is a denormalised mirror kept for the
existing academics/attendance/reports modules and is never used to build a
roster.
"""
from __future__ import annotations

from django.db import IntegrityError, transaction
from django.db.models import QuerySet
from rest_framework.exceptions import ValidationError

from ..models import Enrollment, Registration, Student


def active_enrollments(
    school,
    academic_session=None,
    class_obj=None,
    section=None,
) -> QuerySet[Enrollment]:
    """Base queryset for any roster: school-scoped and ACTIVE only.

    `select_related('student')` keeps roster rendering at one query per page
    rather than one per student (spec §72).
    """
    queryset = Enrollment.objects.filter(
        school=school, status=Enrollment.Status.ACTIVE,
    ).select_related('student', 'class_obj', 'section')
    if academic_session is not None:
        queryset = queryset.filter(academic_session=academic_session)
    if class_obj is not None:
        queryset = queryset.filter(class_obj=class_obj)
    if section is not None:
        queryset = queryset.filter(section=section)
    return queryset


def class_roster(
    school,
    academic_session,
    class_obj,
    section=None,
) -> QuerySet[Enrollment]:
    """The students actually in a class/section, from enrollments only."""
    return active_enrollments(
        school,
        academic_session=academic_session,
        class_obj=class_obj,
        section=section,
    )


def get_active_enrollment(student: Student, academic_session) -> Enrollment | None:
    return (
        Enrollment.objects
        .filter(
            student=student,
            academic_session=academic_session,
            status=Enrollment.Status.ACTIVE,
        )
        .select_related('class_obj', 'section', 'school')
        .first()
    )


def _ensure_one_active_enrollment(student, session, class_obj, section, source, actor):
    """Create the single active enrollment, tolerating a concurrent creator.

    The partial unique index on (student, academic_session) WHERE status=active
    is the real guard (§49, §86); catching IntegrityError turns a racing
    duplicate into a no-op instead of a 500.
    """
    try:
        with transaction.atomic():
            return Enrollment.objects.create(
                school=student.school,
                student=student,
                academic_session=session,
                class_obj=class_obj,
                section=section,
                status=Enrollment.Status.ACTIVE,
                activation_source=source,
                activated_at=_now(),
                activated_by=actor if getattr(actor, 'school_id', None) else None,
            )
    except IntegrityError:
        existing = get_active_enrollment(student, session)
        if existing is None:
            raise
        return existing


def _now():
    from django.utils import timezone
    return timezone.now()


def activate_enrollment(
    *,
    student: Student,
    academic_session,
    class_obj,
    section=None,
    source: str = Enrollment.ActivationSource.ADMIN_APPROVAL,
    actor=None,
) -> Enrollment:
    """Make the student's class assignment effective.

    Idempotent: if an active enrollment already exists for this session it is
    returned unchanged, so a repeated approval or webhook cannot create a
    second one (spec §48).
    """
    existing = get_active_enrollment(student, academic_session)
    if existing is not None:
        return existing
    return _ensure_one_active_enrollment(
        student, academic_session, class_obj, section, source, actor,
    )


def move_active_enrollment(
    student: Student,
    academic_session,
    class_obj,
    section=None,
    *,
    actor=None,
) -> Enrollment:
    """Re-point a student's ACTIVE enrollment at a different class/section.

    Distinct from :func:`activate_enrollment`, which is idempotent and
    deliberately does *not* touch an enrollment that already exists. A transfer
    between classes is a real move, so the existing active row is updated in
    place (history stays in `Student.class_name` mirrors and audit logs rather
    than by faking a second active enrollment, which the partial unique index
    forbids).
    """
    with transaction.atomic():
        enrollment = (
            Enrollment.objects
            .select_for_update()
            .filter(
                student=student,
                academic_session=academic_session,
                status=Enrollment.Status.ACTIVE,
            )
            .first()
        )
        if enrollment is None:
            return activate_enrollment(
                student=student,
                academic_session=academic_session,
                class_obj=class_obj,
                section=section,
                actor=actor,
            )
        enrollment.class_obj = class_obj
        enrollment.section = section
        enrollment.activated_at = _now()
        enrollment.activated_by = actor if getattr(actor, 'school_id', None) else None
        enrollment.save(update_fields=[
            'class_obj', 'section', 'activated_at', 'activated_by', 'updated_at',
        ])
        return enrollment


def sync_student_class_mirror(student: Student, enrollment: Enrollment) -> None:
    """Keep Student.class_name/arm in step with the active enrollment.

    Existing academics, attendance and reports read these denormalised columns;
    Enrollment stays the source of truth for rosters.
    """
    class_name = enrollment.class_obj.name
    arm = enrollment.section.name if enrollment.section_id else ''
    if student.class_name != class_name or student.arm != arm:
        student.class_name = class_name
        student.arm = arm
        student.save(update_fields=['class_name', 'arm'])


def approve_registration(
    registration: Registration,
    *,
    actor=None,
    reason: str = '',
) -> Registration:
    """Approve a pending registration and activate its enrollment (spec §32).

    Partial payment still requires this explicit administrator step; only a
    full verified payment auto-approves (see :mod:`.finance`).
    """
    if registration.status in (Registration.Status.REJECTED, Registration.Status.CANCELLED):
        raise ValidationError({
            'registration': (
                f'This registration was already {registration.get_status_display().lower()}.'
            ),
        })
    if registration.status == Registration.Status.APPROVED:
        return registration

    with transaction.atomic():
        registration.status = Registration.Status.APPROVED
        registration.approved_by = actor if getattr(actor, 'school_id', None) else None
        registration.approved_at = _now()
        registration.decision_reason = reason or registration.decision_reason
        registration.save(update_fields=[
            'status', 'approved_by', 'approved_at', 'decision_reason', 'updated_at',
        ])

        enrollment = _ensure_one_active_enrollment(
            registration.student,
            registration.academic_session,
            registration.intended_class,
            registration.intended_section,
            Enrollment.ActivationSource.ADMIN_APPROVAL,
            actor,
        )
        sync_student_class_mirror(registration.student, enrollment)
    return registration


def flag_enrollment_for_review(enrollment: Enrollment, note: str) -> None:
    """Mark an enrollment for administrative review without ending it (§44).

    A payment reversal leaves the financial state wrong, not the student's
    attendance: the enrollment stays active and is flagged so an administrator
    decides what to do. Enrollment history is never fabricated or rewritten.
    """
    enrollment.flagged_for_review = True
    enrollment.review_note = note[:255]
    enrollment.save(update_fields=['flagged_for_review', 'review_note', 'updated_at'])
