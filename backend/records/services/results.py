"""The results lifecycle: DRAFT -> ... -> LOCKED, and corrections.

The rules this module enforces:

* a sheet only ever moves **forward**, one step at a time
  (``ResultSheet.ALLOWED_TRANSITIONS``), so approval can never be skipped;
* scores are validated against the sheet's own ``assessment_max``, so grading
  stays configurable per school/assessment;
* a **LOCKED** sheet is immutable. Correcting a published result means asking
  for a correction, which records who asked and which authorised user released
  the lock - it is never a silent edit.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation

from django.db import transaction
from rest_framework.exceptions import ValidationError

from . import enrollment as enrollment_service
from ..models import Enrollment, ResultEntry, ResultSheet


def _now():
    from django.utils import timezone
    return timezone.now()


def grade_for(percentage: Decimal) -> str:
    """Grade band for a percentage. Grading scale stays configurable later."""
    if percentage >= 70:
        return ResultEntry.Grade.A
    if percentage >= 60:
        return ResultEntry.Grade.B
    if percentage >= 50:
        return ResultEntry.Grade.C
    if percentage >= 45:
        return ResultEntry.Grade.D
    if percentage >= 40:
        return ResultEntry.Grade.E
    return ResultEntry.Grade.F


def _validate_score(sheet: ResultSheet, raw) -> Decimal | None:
    if raw in (None, ''):
        return None
    try:
        score = Decimal(str(raw))
    except (TypeError, ValueError, InvalidOperation):
        raise ValidationError({'score': f'"{raw}" is not a valid score.'})
    if score < 0:
        raise ValidationError({'score': 'A score cannot be negative.'})
    if score > sheet.assessment_max:
        raise ValidationError({
            'score': (
                f'{score} is above the maximum for {sheet.assessment} '
                f'({sheet.assessment_max}).'
            ),
        })
    return score


def create_sheet(
    *, school, academic_session, class_obj, subject, assessment,
    assessment_max=Decimal('100.00'), term='',
) -> ResultSheet:
    """Create a DRAFT sheet and seed it from the class's active enrollments.

    Seeding from `Enrollment` is what stops a result being recorded for a
    student who is not in the class, and it means the roster and the result
    sheet can never disagree.
    """
    if class_obj.school_id != school.id:
        raise ValidationError({'classObj': 'That class belongs to another school.'})
    if academic_session.school_id != school.id:
        raise ValidationError({'session': 'That session belongs to another school.'})

    try:
        maximum = Decimal(str(assessment_max))
    except (TypeError, ValueError, InvalidOperation):
        raise ValidationError({'assessmentMax': 'The maximum must be a number.'})
    if maximum <= 0:
        raise ValidationError({'assessmentMax': 'The maximum must be greater than zero.'})

    with transaction.atomic():
        sheet, _created = ResultSheet.objects.get_or_create(
            school=school,
            academic_session=academic_session,
            class_obj=class_obj,
            subject=subject,
            assessment=assessment,
            term=term or '',
            defaults={'assessment_max': maximum},
        )
        entries = [
            ResultEntry(sheet=sheet, student=enrollment.student, enrollment=enrollment)
            for enrollment in enrollment_service.class_roster(
                school, academic_session, class_obj,
            )
        ]
        ResultEntry.objects.bulk_create(entries, ignore_conflicts=True)
        return sheet


def record_scores(sheet: ResultSheet, scores: dict) -> int:
    """Write the scores a teacher entered. Only valid while the sheet is editable.

    `scores` maps student id to score. The student must already have an entry on
    this sheet, which is only created from an active enrollment, so this cannot
    be used to attach a result to an arbitrary student.
    """
    if sheet.is_locked or sheet.status == ResultSheet.Status.LOCKED:
        raise ValidationError({
            'sheet': (
                'This result sheet is locked. Request a correction to change a score.'
            ),
        })
    if sheet.status != ResultSheet.Status.DRAFT:
        raise ValidationError({
            'sheet': (
                f'A {sheet.get_status_display().lower()} sheet cannot be edited. '
                'Scores are frozen once submitted.'
            ),
        })

    existing = {
        str(entry.student_id): entry for entry in sheet.entries.select_related('student')
    }
    updated = 0
    for student_id, raw_score in (scores or {}).items():
        entry = existing.get(str(student_id))
        if entry is None:
            raise ValidationError({
                'scores': (
                    f'Student {student_id} is not on this class roster, so no result '
                    'can be recorded for them.'
                ),
            })
        score = _validate_score(sheet, raw_score)
        entry.score = score
        if score is None:
            entry.grade = ''
        else:
            entry.grade = grade_for((score * 100 / sheet.assessment_max).quantize(Decimal('0.01')))
        entry.save(update_fields=['score', 'grade', 'updated_at'])
        updated += 1
    return updated


def advance(sheet: ResultSheet, to_status: str, *, actor=None) -> ResultSheet:
    """Move a sheet one step forward, refusing anything that skips or reverses."""
    expected = ResultSheet.ALLOWED_TRANSITIONS.get(sheet.status)
    if expected is None:
        raise ValidationError({
            'status': 'This result sheet is locked and cannot be moved.',
        })
    if to_status != expected:
        raise ValidationError({
            'status': (
                f'A {sheet.get_status_display().lower()} sheet must go to '
                f'"{dict(ResultSheet.Status.choices)[expected]}", not "{to_status}".'
            ),
        })

    with transaction.atomic():
        sheet = ResultSheet.objects.select_for_update().get(pk=sheet.pk)
        sheet.status = to_status
        fields = ['status', 'updated_at']
        if to_status == ResultSheet.Status.SUBMITTED and actor is not None:
            sheet.submitted_by = actor
            fields.append('submitted_by')
        if to_status == ResultSheet.Status.APPROVED and actor is not None:
            sheet.approved_by = actor
            fields.append('approved_by')
        if to_status == ResultSheet.Status.PUBLISHED:
            sheet.published_at = _now()
            fields.append('published_at')
        if to_status == ResultSheet.Status.LOCKED:
            sheet.is_locked = True
            sheet.locked_at = _now()
            sheet.locked_by = actor
            fields += ['is_locked', 'locked_at', 'locked_by']
        sheet.save(update_fields=fields)
    return sheet


def request_correction(sheet: ResultSheet, reason: str, *, actor=None) -> ResultSheet:
    """Record that a published/locked result is being challenged."""
    if not sheet.is_locked and sheet.status not in (
        ResultSheet.Status.PUBLISHED, ResultSheet.Status.LOCKED,
    ):
        raise ValidationError({
            'sheet': 'Only a published or locked result needs a correction request.',
        })
    if not reason.strip():
        raise ValidationError({'reason': 'A correction needs a reason.'})
    sheet.correction_requested_at = _now()
    sheet.correction_reason = reason[:255]
    sheet.save(update_fields=['correction_requested_at', 'correction_reason', 'updated_at'])
    return sheet


def release_for_correction(sheet: ResultSheet, *, actor) -> ResultSheet:
    """Authorise a correction: reopen the sheet as APPROVED and record who did it.

    This is the only way a locked score is ever changed, and the authorising
    user is stored on the sheet.
    """
    if not sheet.is_locked:
        raise ValidationError({'sheet': 'This result sheet is not locked.'})
    if not sheet.correction_requested_at:
        raise ValidationError({
            'sheet': 'Record a correction request before releasing the sheet.',
        })
    with transaction.atomic():
        sheet = ResultSheet.objects.select_for_update().get(pk=sheet.pk)
        sheet.is_locked = False
        sheet.locked_at = None
        sheet.locked_by = None
        sheet.status = ResultSheet.Status.APPROVED
        sheet.correction_authorised_by = actor
        sheet.correction_requested_at = None
        sheet.save(update_fields=[
            'is_locked', 'locked_at', 'locked_by', 'status',
            'correction_authorised_by', 'correction_requested_at', 'updated_at',
        ])
    return sheet


def sheet_detail(sheet: ResultSheet) -> dict:
    """A sheet with its scores, for the results screen and the AI tools."""
    entries = sheet.entries.select_related('student').order_by(
        'student__last_name', 'student__first_name',
    )
    return {
        'id': sheet.id,
        'sessionId': str(sheet.academic_session_id),
        'session': sheet.academic_session.name,
        'classId': str(sheet.class_obj_id),
        'className': sheet.class_obj.name,
        'subject': sheet.subject,
        'assessment': sheet.assessment,
        'assessmentMax': str(sheet.assessment_max),
        'term': sheet.term,
        'status': sheet.status,
        'isLocked': sheet.is_locked,
        'entries': [
            {
                'studentId': str(entry.student_id),
                'studentName': f'{entry.student.last_name}, {entry.student.first_name}',
                'score': str(entry.score) if entry.score is not None else '',
                'grade': entry.grade,
                'remark': entry.remark,
            }
            for entry in entries
        ],
    }
