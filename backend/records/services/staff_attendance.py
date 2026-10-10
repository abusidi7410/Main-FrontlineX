"""Staff (teacher) check-ins, verified against the school's GPS location.

Distinct from the student register in ``services.attendance``: this records
whether a member of staff turned up, and where they were when they did. The
school's own coordinates and an attendance radius live on ``School``; each
check-in computes the straight-line distance to them and stores a derived
status, so history stays stable even if the campus location is later refined.

One row per staff member per school day. A second check-in the same day updates
the existing row (with fresh coordinates and a cleared review) instead of
creating a duplicate.
"""
from __future__ import annotations

import datetime as dt
import math

from django.db import transaction
from django.utils import timezone

from ..models import StaffAttendance, StaffMember

EARTH_RADIUS_M = 6_371_000.0

# A reading whose uncertainty could still place the person on site is not
# rejected outright; it is flagged for a human to decide.
STATUS_AT_SCHOOL = StaffAttendance.Status.AT_SCHOOL
STATUS_OUTSIDE = StaffAttendance.Status.OUTSIDE
STATUS_UNVERIFIED = StaffAttendance.Status.UNVERIFIED
STATUS_PENDING_REVIEW = StaffAttendance.Status.PENDING_REVIEW


def haversine_meters(lat1, lon1, lat2, lon2) -> float:
    """Great-circle distance between two points, in metres."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lon2 - lon1)
    a = (
        math.sin(d_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    )
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(a))


def local_day(school, at=None) -> dt.date:
    """The calendar day (in the school's own time zone) for ``at``.

    Falls back to the platform's local date if the school's zone is unknown or
    the time zone database is unavailable, so a missing tzdata package on a
    host never turns a check-in into a 500.
    """
    at = at or timezone.now()
    tz_name = getattr(school, 'timezone', '') or ''
    if tz_name:
        try:
            from zoneinfo import ZoneInfo

            return timezone.localtime(at, ZoneInfo(tz_name)).date()
        except Exception:
            pass
    return timezone.localdate(at)


def classify(school, latitude, longitude, accuracy):
    """Derive a status (and distance) from a reading against the school.

    Returns ``(status, distance_meters)``. ``UNVERIFIED`` when either the school
    has no coordinates or the check-in did not carry a usable pair — a check-in
    with no location is still recorded, just not trusted.
    """
    if latitude is None or longitude is None:
        return STATUS_UNVERIFIED, None
    if school.latitude is None or school.longitude is None:
        return STATUS_UNVERIFIED, None

    distance = haversine_meters(
        float(latitude), float(longitude),
        float(school.latitude), float(school.longitude),
    )
    radius = school.attendance_radius if school.attendance_radius is not None else 150
    margin = max(float(accuracy or 0.0), 0.0)

    if distance <= radius:
        return STATUS_AT_SCHOOL, distance
    # Within the fence once the reading's own slack is allowed for: too close to
    # call either way, so a person decides.
    if distance - margin <= radius:
        return STATUS_PENDING_REVIEW, distance
    return STATUS_OUTSIDE, distance


def require_staff(user) -> StaffMember:
    """The staff record linked to this account, or raise if there is none."""
    from rest_framework.exceptions import ValidationError

    staff = getattr(user, 'staff_profile', None)
    if staff is None:
        raise ValidationError({
            'detail': 'Your account is not linked to a staff record, so it cannot check in.',
        })
    return staff


@transaction.atomic
def check_in(
    *, user, school, staff: StaffMember,
    latitude=None, longitude=None, accuracy=None, notes='',
    day: dt.date | None = None, at=None,
):
    """Record (or refresh) this staff member's check-in for a school day."""
    at = at or timezone.now()
    day = day or local_day(school, at)
    status, distance = classify(school, latitude, longitude, accuracy)

    record, created = StaffAttendance.objects.get_or_create(
        staff=staff,
        date=day,
        defaults={
            'school': school,
            'check_in_at': at,
            'latitude': latitude,
            'longitude': longitude,
            'accuracy_meters': accuracy,
            'distance_meters': distance,
            'status': status,
            'notes': (notes or '')[:280],
        },
    )
    if not created:
        record.school = school
        record.check_in_at = at
        record.latitude = latitude
        record.longitude = longitude
        record.accuracy_meters = accuracy
        record.distance_meters = distance
        record.status = status
        record.notes = (notes or '')[:280]
        # A fresh reading clears any earlier manual review: it is new evidence.
        record.reviewed_by = None
        record.reviewed_at = None
        record.review_note = ''
        record.save()
    return record, created


@transaction.atomic
def review(*, user, school, record: StaffAttendance, decision: str, note=''):
    """An administrator upholds or overrides an uncertain check-in.

    ``decision`` is ``approve`` (count as on site) or ``reject`` (count as
    outside). Only records that already belong to this school reach here.
    """
    from rest_framework.exceptions import ValidationError

    if decision == 'approve':
        record.status = STATUS_AT_SCHOOL
    elif decision == 'reject':
        record.status = STATUS_OUTSIDE
    else:
        raise ValidationError({'decision': 'Choose approve or reject.'})

    record.reviewed_by = user
    record.reviewed_at = timezone.now()
    record.review_note = (note or '')[:280]
    record.save(update_fields=[
        'status', 'reviewed_by', 'reviewed_at', 'review_note', 'updated_at',
    ])
    return record


def records_for(
    school, *, staff=None, day=None, day_from=None, day_to=None,
    statuses=None, search='',
):
    """Check-ins for a school, newest first, with the caller's filters applied."""
    queryset = (
        StaffAttendance.objects.filter(school=school)
        .select_related('staff', 'reviewed_by')
    )
    if staff is not None:
        queryset = queryset.filter(staff=staff)
    if day is not None:
        queryset = queryset.filter(date=day)
    if day_from is not None:
        queryset = queryset.filter(date__gte=day_from)
    if day_to is not None:
        queryset = queryset.filter(date__lte=day_to)
    if statuses:
        queryset = queryset.filter(status__in=statuses)
    if search:
        queryset = queryset.filter(staff__full_name__icontains=search)
    return queryset


def summary_for(school, day, *, staff=None) -> dict:
    """Counts for one day, for the admin board."""
    queryset = records_for(school, staff=staff, day=day)
    counts = {choice: 0 for choice, _ in StaffAttendance.Status.choices}
    for row in queryset.values('status'):
        counts[row['status']] = counts.get(row['status'], 0) + 1
    return {
        'date': day.isoformat(),
        'total': sum(counts.values()),
        'counts': counts,
    }
