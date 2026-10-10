"""Building a child's report card from the school's published results.

A report card is a *read model*: nothing is stored for it, it is assembled on
demand from result sheets that have already been approved and published, so
the card can never disagree with the results screen. The rules:

* only PUBLISHED or LOCKED sheets are ever read - a draft score the school has
  not approved is not a result a parent may see;
* grading comes from `results.grade_for`, the same scale the teachers' scores
  were graded with, so the card cannot invent a grade the backend disagrees
  with;
* class position and the promotion suggestion come from
  `promotion.candidates_for`, the calculation the promotion screen itself runs.
"""
from __future__ import annotations

from collections import OrderedDict
from decimal import Decimal

from django.db.models import Count, Q

from ..models import (
    AcademicSession,
    AttendanceRecord,
    Enrollment,
    ResultEntry,
    ResultSheet,
    Student,
)
from . import parent_portal
from . import promotion as promotion_service
from . import results as results_service

PUBLISHED_STATES = (ResultSheet.Status.PUBLISHED, ResultSheet.Status.LOCKED)

REMARKS = (
    (70, 'Outstanding. Keep up the excellent work and continue to help your classmates.'),
    (60, 'Very good. Consistent effort this term; watch out for careless mistakes in exams.'),
    (50, 'Good, but there is room for improvement. Revise regularly and attempt more class work.'),
    (40, 'Fair. More attention is needed in some subjects; cover past questions before exams.'),
)
DEFAULT_REMARK = 'Unsatisfactory. Please see your class teacher for a study plan for the next term.'


def remark_for(average: Decimal) -> str:
    for threshold, text in REMARKS:
        if average >= threshold:
            return text
    return DEFAULT_REMARK


def _resolve_session(student: Student, session: AcademicSession | None) -> AcademicSession | None:
    if session is not None:
        return session
    return parent_portal.current_session_for(student)


def _sheet_term(sheets) -> str:
    """The term the card speaks for, from the sheets themselves.

    Mixed terms would be ambiguous, so only an unambiguous set is reported -
    the school's own current term is the fallback.
    """
    terms = {(sheet.term or '').strip() for sheet in sheets}
    terms.discard('')
    return terms.pop() if len(terms) == 1 else ''


def _session_sheets(student: Student, session: AcademicSession, term: str):
    """Published sheets for the child's class, narrowed to one term if asked."""
    enrollment = (
        Enrollment.objects
        .filter(student=student, academic_session=session)
        .select_related('class_obj', 'section')
        .order_by('-created_at')
        .first()
    )
    if enrollment is None:
        return None, None

    sheets = list(
        ResultSheet.objects.filter(
            school_id=student.school_id,
            academic_session=session,
            class_obj=enrollment.class_obj,
            status__in=PUBLISHED_STATES,
        )
    )
    if term:
        sheets = [sheet for sheet in sheets if (sheet.term or '').strip() == term]
    else:
        # No explicit term: prefer the school's current term so a card never
        # mixes two terms, but fall back to everything published when the
        # sheets were filed without a term at all.
        current = (student.school.current_term or '').strip()
        if current:
            matching = [sheet for sheet in sheets if (sheet.term or '').strip() == current]
            if matching:
                sheets = matching
    return enrollment, sheets


def _subject_rows(student: Student, sheets) -> list[dict]:
    """Group the child's entries into one row per subject.

    Component columns (CA 1/CA 2/assignment/exam) are only shown when the
    subject rests on a single sheet carrying all four: two sheets for one
    subject would otherwise be added together and print a CA 1 out of 20 under
    a column the school reads as out of 10.
    """
    if not sheets:
        return []

    entries = list(
        ResultEntry.objects.filter(sheet__in=sheets, student=student).select_related('sheet')
    )
    grouped: OrderedDict[str, dict] = OrderedDict()
    for entry in entries:
        if entry.score is None:
            continue
        key = entry.sheet.subject.strip().casefold()
        bucket = grouped.setdefault(key, {
            'subject': entry.sheet.subject.strip(),
            'entries': [],
        })
        bucket['entries'].append(entry)

    rows = []
    for bucket in grouped.values():
        entries = bucket['entries']
        total = sum((entry.score for entry in entries), Decimal('0'))
        maximum = sum((entry.sheet.assessment_max for entry in entries), Decimal('0'))
        if maximum <= 0:
            continue
        percentage = (total * Decimal('100') / maximum).quantize(Decimal('0.1'))
        single = entries[0] if len(entries) == 1 else None
        rows.append({
            'subject': bucket['subject'],
            'ca1': float(single.ca1) if single is not None and single.ca1 is not None else None,
            'ca2': float(single.ca2) if single is not None and single.ca2 is not None else None,
            'assignment': (
                float(single.assignment)
                if single is not None and single.assignment is not None else None
            ),
            'exam': float(single.exam) if single is not None and single.exam is not None else None,
            'total': float(total),
            'max': float(maximum),
            'percentage': float(percentage),
            'grade': results_service.grade_for(percentage),
        })
    rows.sort(key=lambda row: row['subject'].casefold())
    return rows


def _attendance(student: Student, session: AcademicSession) -> dict:
    """Counts for the session's calendar window.

    `excused` days are counted but kept out of the rate: a day the school
    excused is not a day the child was expected to attend (the promotion
    calculation treats them the same way).
    """
    start, end = parent_portal.session_window(session)
    counts = AttendanceRecord.objects.filter(
        school_id=student.school_id, student=student, date__range=(start, end),
    ).aggregate(
        recorded=Count('pk'),
        present=Count('pk', filter=Q(status=AttendanceRecord.Status.PRESENT)),
        late=Count('pk', filter=Q(status=AttendanceRecord.Status.LATE)),
        absent=Count('pk', filter=Q(status=AttendanceRecord.Status.ABSENT)),
        excused=Count('pk', filter=Q(status=AttendanceRecord.Status.EXCUSED)),
    )
    expected = counts['recorded'] - counts['excused']
    attended = counts['present'] + counts['late']
    counts['attendanceRate'] = round(attended * 100 / expected, 1) if expected else 0
    return counts


def build_report_card(student: Student, *, session=None, term: str = '') -> dict | None:
    """Assemble the report card, or None when there is nothing published yet.

    Returning None (a 404 at the view) rather than an empty card is what lets
    the screens say "no report card yet" for a child whose results are still
    being marked, without leaking whether the id belongs to another family.
    """
    school = student.school
    session = _resolve_session(student, session)
    if session is None:
        return None

    enrollment, sheets = _session_sheets(student, session, term)
    if enrollment is None:
        return None

    subjects = _subject_rows(student, sheets)
    if not subjects:
        return None

    attendance = _attendance(student, session)
    attendance_rate = attendance['attendanceRate']

    total = sum(Decimal(str(row['total'])) for row in subjects)
    max_total = sum(Decimal(str(row['max'])) for row in subjects)
    percentages = [Decimal(str(row['percentage'])) for row in subjects]
    average = (sum(percentages, Decimal('0')) / len(percentages)).quantize(Decimal('0.1'))

    # Position and the promotion suggestion are the class's own calculation, so
    # what a parent reads here matches what the head teacher's promotion screen
    # shows for the same child (session-wide, not term-filtered).
    policy = promotion_service.policy_for(school)
    standings = promotion_service.candidates_for(school, session, enrollment.class_obj, policy)
    ranked = sorted(
        (row for row in standings if row['average'] is not None),
        key=lambda row: row['average'],
        reverse=True,
    )
    position = None
    mine = None
    for index, row in enumerate(ranked):
        if row['studentId'] == str(student.public_id):
            # Ties share a rank: two children on 78.5% are both 1st.
            rank = index + 1
            while rank > 1 and ranked[rank - 2]['average'] == row['average']:
                rank -= 1
            position = {'rank': rank, 'outOf': len(ranked)}
            mine = row
            break
    if mine is None:
        mine = next(
            (row for row in standings if row['studentId'] == str(student.public_id)),
            None,
        )

    destination = promotion_service.next_class_for(enrollment.class_obj)
    promotion = None
    if mine is not None:
        promotion = {
            'suggested': mine['suggested'],
            'reason': mine['reason'],
            'average': mine['average'],
            'attendanceRate': mine['attendanceRate'],
            'failedSubjects': mine['failedSubjects'],
            'subjectsAssessed': mine['subjectsAssessed'],
            'isFinalClass': destination is None,
            'nextClass': destination.name if destination is not None else None,
            'policy': {
                'promoteMinAverage': float(policy.promote_min_average),
                'promoteMinAttendance': float(policy.promote_min_attendance),
                'conditionalMinAverage': float(policy.conditional_min_average),
                'conditionalMinAttendance': float(policy.conditional_min_attendance),
                'conditionalMaxFailedSubjects': policy.conditional_max_failed_subjects,
            },
        }

    return {
        'student': {
            'id': str(student.public_id),
            'name': f'{student.first_name} {student.last_name}'.strip(),
            'admissionNumber': student.admission_number,
            'className': enrollment.class_obj.name,
            'arm': enrollment.section.name if enrollment.section_id else student.arm,
            'gender': student.gender,
            'attendanceRate': attendance_rate,
        },
        'school': {'name': school.name, 'address': school.address},
        'session': session.name,
        'term': term or _sheet_term(sheets) or (school.current_term or ''),
        'subjects': subjects,
        'totalScore': float(total),
        'maxScore': float(max_total),
        'average': float(average),
        'remark': remark_for(average),
        'position': position,
        'promotion': promotion,
        'attendance': {
            'recorded': attendance['recorded'],
            'present': attendance['present'],
            'late': attendance['late'],
            'absent': attendance['absent'],
            'excused': attendance['excused'],
            'attendanceRate': attendance_rate,
        },
    }
