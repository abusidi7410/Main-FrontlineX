"""Promotion recommendations derived from published results and attendance."""
from __future__ import annotations

from collections import defaultdict
from datetime import date
from decimal import Decimal

from ..models import (
    AcademicSession,
    AttendanceRecord,
    Enrollment,
    PromotionPolicy,
    ResultEntry,
    ResultSheet,
    SchoolClass,
    Student,
)


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

    attendance: dict[int, list[int]] = defaultdict(lambda: [0, 0])
    # AttendanceRecord has no session FK. Bound the query to the session's
    # calendar years so later sessions cannot affect this year's decision.
    start_date = date(session.start_year, 8, 1)
    end_date = date(session.end_year, 7, 31)
    for row in AttendanceRecord.objects.filter(
        school=school,
        student_id__in=student_ids,
        date__range=(start_date, end_date),
    ).values('student_id', 'status'):
        if row['status'] == AttendanceRecord.Status.EXCUSED:
            continue
        attendance[row['student_id']][1] += 1
        if row['status'] in (AttendanceRecord.Status.PRESENT, AttendanceRecord.Status.LATE):
            attendance[row['student_id']][0] += 1

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
        present, recorded = attendance[student.pk]
        attendance_rate = (
            Decimal(present * 100) / Decimal(recorded) if recorded else None
        )
        missing_sheet = bool(expected_sheet_ids - seen_sheets[student.pk])
        incomplete = (
            not sheets
            or missing_sheet
            or student.pk in incomplete_students
            or not percentages
            or recorded == 0
        )
        suggested = _decision(average, attendance_rate, failed, incomplete, policy)
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
            'studentId': str(student.pk),
            'studentName': f'{student.first_name} {student.last_name}'.strip(),
            'admissionNumber': student.admission_number,
            'className': school_class.name,
            'average': round(float(average), 1) if average is not None else None,
            'attendanceRate': round(float(attendance_rate), 1) if attendance_rate is not None else None,
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
