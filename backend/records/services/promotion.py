"""Promotion recommendations derived from published results and attendance."""
from __future__ import annotations

from collections import defaultdict
from decimal import Decimal

from ..models import (
    AcademicSession,
    Enrollment,
    PromotionPolicy,
    ResultEntry,
    ResultSheet,
    SchoolClass,
    Student,
)
from . import attendance_rate


DECISIONS = {'promote', 'conditional', 'repeat', 'review'}


def policy_for(school) -> PromotionPolicy:
    policy, _ = PromotionPolicy.objects.get_or_create(school=school)
    return policy


def next_session_name(session: AcademicSession) -> str:
    return f'{session.end_year}/{session.end_year + 1}'


def next_class_for(school_class: SchoolClass) -> SchoolClass | None:
    """Use the school's configured level/class order, not class-name guesses."""
    classes = list(
        SchoolClass.objects.filter(school=school_class.school, is_active=True)
        .select_related('level')
        .order_by('level__sort_order', 'sort_order', 'name')
    )
    current_index = next(
        (index for index, item in enumerate(classes) if item.pk == school_class.pk),
        None,
    )
    if current_index is None or current_index + 1 >= len(classes):
        return None
    return classes[current_index + 1]


def _decision(average: Decimal | None, attendance_rate: Decimal | None,
              failed_subjects: int, incomplete: bool, policy: PromotionPolicy) -> str:
    if incomplete or average is None or attendance_rate is None:
        return 'review'
    if (
        average >= policy.promote_min_average
        and attendance_rate >= policy.promote_min_attendance
        and failed_subjects == 0
    ):
        return 'promote'
    if (
        average >= policy.conditional_min_average
        and attendance_rate >= policy.conditional_min_attendance
        and failed_subjects <= policy.conditional_max_failed_subjects
    ):
        return 'conditional'
    return 'repeat'


def candidates_for(school, session: AcademicSession, school_class: SchoolClass,
                   policy: PromotionPolicy) -> list[dict]:
    enrollments = list(
        Enrollment.objects.filter(
            school=school,
            academic_session=session,
            class_obj=school_class,
            status=Enrollment.Status.ACTIVE,
            student__status=Student.Status.ACTIVE,
        ).select_related('student', 'section')
    )
    if not enrollments:
        return []

    student_ids = [row.student_id for row in enrollments]
    sheets = list(
        ResultSheet.objects.filter(
            school=school,
            academic_session=session,
            class_obj=school_class,
            status__in=[ResultSheet.Status.PUBLISHED, ResultSheet.Status.LOCKED],
        ).values('id', 'subject', 'assessment_max')
    )
    entries = list(
        ResultEntry.objects.filter(
            sheet_id__in=[row['id'] for row in sheets],
            student_id__in=student_ids,
        ).values('student_id', 'sheet_id', 'sheet__subject', 'score')
    ) if sheets else []

    scores_by_student: dict[int, dict[str, list[Decimal]]] = defaultdict(
        lambda: defaultdict(lambda: [Decimal('0'), Decimal('0')])
    )
    seen_sheets: dict[int, set[int]] = defaultdict(set)
    incomplete_students: set[int] = set()
    max_by_sheet = {row['id']: row['assessment_max'] for row in sheets}
    for entry in entries:
        student_id = entry['student_id']
        seen_sheets[student_id].add(entry['sheet_id'])
        if entry['score'] is None:
            incomplete_students.add(student_id)
            continue
        subject = entry['sheet__subject'].strip().casefold()
        values = scores_by_student[student_id][subject]
        values[0] += entry['score']
        values[1] += max_by_sheet[entry['sheet_id']]

    # One grouped query for the whole class, bounded to the session's calendar
    # window and scored by the shared rate service, so a promotion decision uses
    # the same figure the parent portal and report card print. AttendanceRecord
    # has no session FK, so the window is what keeps later sessions out.
    per_student = attendance_rate.counts_for_students(
        school.id, student_ids, window=attendance_rate.session_window(session),
    )

    expected_sheet_ids = {row['id'] for row in sheets}
    final_class = next_class_for(school_class) is None
    candidates = []
    for enrollment in enrollments:
        student = enrollment.student
        per_subject = scores_by_student[student.pk]
        percentages = [
            (total * Decimal('100') / maximum)
            for total, maximum in per_subject.values()
            if maximum > 0
        ]
        average = (
            sum(percentages, Decimal('0')) / len(percentages)
            if percentages else None
        )
        failed = (
            sum(score < policy.promote_min_average for score in percentages)
            if percentages else 0
        )
        counts = per_student.get(student.pk)
        # `None` counts means the pupil has no register line in this session,
        # and a `None` rate means no session was held; the policy reads either
        # as "not enough data" rather than as a zero percent.
        pct = attendance_rate.rate_from_counts(counts) if counts is not None else None
        attendance_rate_value = Decimal(str(pct)) if pct is not None else None
        missing_sheet = bool(expected_sheet_ids - seen_sheets[student.pk])
        recorded = counts['recorded'] if counts is not None else 0
        incomplete = (
            not sheets
            or missing_sheet
            or student.pk in incomplete_students
            or not percentages
            or recorded == 0
        )
        suggested = _decision(average, attendance_rate_value, failed, incomplete, policy)
        if final_class and suggested == 'conditional':
            suggested = 'review'
        if incomplete:
            reason = 'Published results or attendance are incomplete.'
        elif suggested == 'promote':
            reason = 'Meets the average and attendance thresholds with no failed subjects.'
        elif suggested == 'conditional':
            reason = 'Meets the conditional thresholds and failed-subject limit.'
        else:
            reason = 'Below the minimum average or attendance, or above the failed-subject limit.'
        candidates.append({
            'studentId': str(student.public_id),
            'studentName': f'{student.first_name} {student.last_name}'.strip(),
            'admissionNumber': student.admission_number,
            'className': school_class.name,
            'average': round(float(average), 1) if average is not None else None,
            'attendanceRate': (
                round(float(attendance_rate_value), 1)
                if attendance_rate_value is not None else None
            ),
            'attendanceRecords': recorded,
            'subjectsAssessed': len(percentages),
            'failedSubjects': failed,
            'incomplete': incomplete,
            'reason': reason,
            'isFinalClass': final_class,
            'suggested': suggested,
        })
    return candidates


def class_summaries(school, session: AcademicSession, policy: PromotionPolicy) -> list[dict]:
    summaries = []
    classes = (
        SchoolClass.objects.filter(school=school, is_active=True)
        .select_related('level')
        .order_by('level__sort_order', 'sort_order', 'name')
    )
    for school_class in classes:
        candidates = candidates_for(school, session, school_class, policy)
        counts = {decision: 0 for decision in DECISIONS}
        for candidate in candidates:
            counts[candidate['suggested']] += 1
        destination = next_class_for(school_class)
        summaries.append({
            'className': school_class.name,
            'nextClass': destination.name if destination else None,
            'total': len(candidates),
            'promote': counts['promote'],
            'conditional': counts['conditional'],
            'repeat': counts['repeat'],
            'review': counts['review'],
            'graduated': counts['promote'] if destination is None else 0,
        })
    return summaries
