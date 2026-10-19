"""Single source of truth for every attendance percentage in the product.

Before this module existed the same student could show four different rates:
the students list counted an excused day against the child, the parent portal
and report card did not, the promotion engine used a third window, and the
dashboard average used a rolling 30-day window. One formula now serves them all.

The formula
-----------
    rate = (present + late) / (recorded - excused) * 100

Status rules (the application's own, applied consistently):
  * ``present`` and ``late`` count as **attending**.
  * ``absent`` stays in the denominator: it is a day the child was expected to
    attend and did not.
  * ``excused`` is **removed from the denominator**. A day the school excused is
    a day the child was not expected to attend, so it can neither help nor hurt
    the figure. This is the rule the parent portal, the report card and the
    promotion engine already used; the students list was the outlier.

What counts as a "session held"
-------------------------------
Only a day that has a persisted ``AttendanceRecord`` counts. A school day the
register was never taken is **not** a session that was held, so it appears in
neither the numerator nor the denominator. An unrecorded session is therefore
never silently treated as attended. Weekends and declared closures never receive
a register at all (``attendance.is_school_day`` gates submission), so a holiday
cannot leak into the figure.

Because the denominator is the student's *own* register lines, a pupil who
joined mid-term is not charged for sessions held before they were enrolled.

Scoping
-------
Every helper takes a ``school_id`` (or a student already bound to one) so one
tenant's rows can never reach another's arithmetic. ``session_window`` bounds a
query to an academic session's calendar years -- ``AttendanceRecord`` has no
session foreign key, so the window is what stops a later session from inflating
this year's figure.

An empty denominator returns ``None`` (never a flattering ``100``), so callers
can render "no register yet" instead of inventing a perfect record.
"""
from __future__ import annotations

from datetime import date

from django.db.models import Count, Q

from ..models import AttendanceRecord

# A pupil is considered present for the day if they turned up at all; a late
# arrival still attended. An excused absence is approved and is not counted
# against them.
ATTENDED_STATUSES = (AttendanceRecord.Status.PRESENT, AttendanceRecord.Status.LATE)


def session_window(session) -> tuple[date, date]:
    """The calendar bounds of an academic session (Aug 1 start -> Jul 31 end).

    ``AttendanceRecord`` carries no session foreign key, so every term-scoped
    query is bounded by the session's calendar years. These are the same bounds
    the promotion engine has always used.
    """
    return date(session.start_year, 8, 1), date(session.end_year, 7, 31)


def rate_from_counts(counts: dict) -> float | None:
    """Turn a ``recorded``/``present``/``late``/``excused`` mapping into a rate.

    Returns ``None`` when no eligible session was held, which every caller must
    render as "no register yet" rather than as a percentage.
    """
    attended = (counts.get('present') or 0) + (counts.get('late') or 0)
    expected = (counts.get('recorded') or 0) - (counts.get('excused') or 0)
    if expected <= 0:
        return None
    return round(attended * 100 / expected, 1)


def _scoped(school_id: int, *, window=None, date_from=None, date_to=None):
    """A tenant-scoped ``AttendanceRecord`` queryset, optionally windowed."""
    queryset = AttendanceRecord.objects.filter(school_id=school_id)
    if window is not None:
        queryset = queryset.filter(date__range=window)
    if date_from is not None:
        queryset = queryset.filter(date__gte=date_from)
    if date_to is not None:
        queryset = queryset.filter(date__lte=date_to)
    return queryset


def counts_for_students(
    school_id: int,
    student_ids=None,
    *,
    window=None,
    date_from=None,
    date_to=None,
) -> dict[int, dict]:
    """Per-student counts in a single grouped query.

    Returns ``{student_id: {'recorded', 'present', 'late', 'absent', 'excused'}}``
    for every student in ``student_ids`` (or all of the school's students when
    ``student_ids`` is ``None``). Students with no register lines are absent from
    the mapping, so a caller can tell "no data" from "zero percent".
    """
    queryset = _scoped(school_id, window=window, date_from=date_from, date_to=date_to)
    if student_ids is not None:
        queryset = queryset.filter(student_id__in=list(student_ids))

    rows = queryset.values('student_id').annotate(
        recorded=Count('pk'),
        present=Count('pk', filter=Q(status=AttendanceRecord.Status.PRESENT)),
        late=Count('pk', filter=Q(status=AttendanceRecord.Status.LATE)),
        absent=Count('pk', filter=Q(status=AttendanceRecord.Status.ABSENT)),
        excused=Count('pk', filter=Q(status=AttendanceRecord.Status.EXCUSED)),
    )
    return {row['student_id']: row for row in rows}


def counts_for_student(student, *, session=None, window=None, date_from=None, date_to=None) -> dict:
    """Counts for one student, optionally bounded by an academic session."""
    if window is None and session is not None:
        window = session_window(session)
    per_student = counts_for_students(
        student.school_id, [student.pk],
        window=window, date_from=date_from, date_to=date_to,
    )
    return per_student.get(
        student.pk,
        {'recorded': 0, 'present': 0, 'late': 0, 'absent': 0, 'excused': 0},
    )


def rate_for_student(student, **kwargs) -> float | None:
    """The attendance rate for one student, or ``None`` when nothing is held."""
    return rate_from_counts(counts_for_student(student, **kwargs))


def counts_for_school(
    school_id: int, *, session=None, window=None, date_from=None, date_to=None,
) -> dict:
    """School-wide counts over every register line in scope.

    Accepts ``session`` exactly as :func:`counts_for_student` does, so a caller
    holding an academic session (the student-stats headline) can scope the whole
    school's figure to one term without assembling the window itself.
    """
    if window is None and session is not None:
        window = session_window(session)
    totals = _scoped(
        school_id, window=window, date_from=date_from, date_to=date_to,
    ).aggregate(
        recorded=Count('pk'),
        present=Count('pk', filter=Q(status=AttendanceRecord.Status.PRESENT)),
        late=Count('pk', filter=Q(status=AttendanceRecord.Status.LATE)),
        absent=Count('pk', filter=Q(status=AttendanceRecord.Status.ABSENT)),
        excused=Count('pk', filter=Q(status=AttendanceRecord.Status.EXCUSED)),
    )
    return totals


def rate_for_school(school_id: int, **kwargs) -> float | None:
    """The school-wide attendance rate, or ``None`` when no register is held."""
    return rate_from_counts(counts_for_school(school_id, **kwargs))


def aggregate_rate(counts_list) -> float | None:
    """A rate from an iterable of per-student count dicts.

    This is how a class or school average must be built: sum the counts first,
    then divide. Averaging already-computed percentages over-weights a pupil
    with one recorded day as heavily as one with forty.
    """
    summed = {'recorded': 0, 'present': 0, 'late': 0, 'absent': 0, 'excused': 0}
    seen = False
    for counts in counts_list:
        seen = True
        for key in summed:
            summed[key] += counts.get(key) or 0
    if not seen:
        return None
    return rate_from_counts(summed)
