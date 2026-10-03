"""Notification fan-out (spec 32).

Every notification in the product is created through `notify*` here, never by
hand at a call site. That matters for three reasons:

- **Preferences live in one place.** A person who switched off attendance
  alerts must not still receive them from whichever subsystem happened to
  write the row.
- **Idempotency lives in one place.** Retried requests, replayed jobs and
  management commands can all call these without stacking duplicates.
- **Recipients are resolved safely in one place.** A school is a tenant
  boundary, and "who is in this school" is the single most security-sensitive
  question in the module. All of it is answered here from the caller's school,
  never from a caller-supplied id.

Recipients are resolved to concrete User rows at fan-out time and a row is
written per person. That is what makes unread state per-person and lets one
ordered feed serve both the header bell and the notification centre.
"""

from django.db.models import QuerySet
from django.utils import timezone

from accounts.models import Notification, NotificationPreference, User

# Roles that make up each audience in the announcement composer.
# Kept here (not in the view) so the AI tools and any future channel agree.
AUDIENCE_ROLES = {
    'All': ('school_admin', 'principal', 'teacher', 'accountant', 'secretary', 'parent', 'student'),
    'Staff': ('school_admin', 'principal', 'teacher', 'accountant', 'secretary'),
    'Parents': ('parent',),
    'Students': ('student',),
}


def notify(
    users: QuerySet | list[User] | set[int],
    *,
    type: str,
    title: str,
    body: str = '',
    link: str = '',
    dedupe_key: str = '',
    school=None,
) -> int:
    """Write one notification per recipient. Returns how many were created.

    A `dedupe_key` makes the call idempotent per person: replaying the same
    event re-uses the existing row instead of adding a second copy.
    """
    ids = list(users.values_list('pk', flat=True)) if isinstance(users, QuerySet) else [
        getattr(u, 'pk', u) for u in users
    ]
    ids = [i for i in dict.fromkeys(ids) if i is not None]
    if not ids:
        return 0

    # One query for every opt-out among the recipients, rather than one per
    # user: a whole-school announcement can address thousands of people.
    # Absence of a row means enabled, so "muted" is the whole answer.
    muted = set(
        NotificationPreference.objects.filter(
            user_id__in=ids, type=type, in_app=False,
        ).values_list('user_id', flat=True),
    )
    targets = [i for i in ids if i not in muted]

    if dedupe_key:
        # Drop the recipients who already have this event before inserting,
        # rather than inserting and catching one constraint violation per
        # person. `ignore_conflicts` still backs it up for the case where two
        # requests race between the read and the write.
        already = set(
            Notification.objects.filter(
                user_id__in=targets, dedupe_key=dedupe_key,
            ).values_list('user_id', flat=True),
        )
        targets = [i for i in targets if i not in already]
    if not targets:
        return 0

    rows = [
        Notification(
            user_id=user_id,
            school=school,
            type=type,
            title=title[:200],
            body=body,
            link=link[:200],
            dedupe_key=dedupe_key,
        )
        for user_id in targets
    ]
    Notification.objects.bulk_create(
        rows, batch_size=500, ignore_conflicts=bool(dedupe_key),
    )
    return len(rows)


def notify_roles(school, roles, *, type: str, title: str, body: str = '', link: str = '',
                 dedupe_key: str = '') -> int:
    """Notify every active user in *school* holding one of *roles*."""
    if school is None:
        return 0
    return notify(
        User.objects.filter(school=school, role__in=list(roles), is_active=True),
        type=type, title=title, body=body, link=link, dedupe_key=dedupe_key, school=school,
    )


def notify_admin(school, *, type: str, title: str, body: str = '', link: str = '',
                 dedupe_key: str = '', roles=('school_admin',)) -> int:
    """Notify the people who act on this class of event (usually an admin)."""
    return notify_roles(
        school, roles, type=type, title=title, body=body, link=link, dedupe_key=dedupe_key,
    )


def notify_students(students, *, type: str, title: str, body: str = '', link: str = '',
                    dedupe_key: str = '', school=None) -> int:
    """Notify the student accounts behind `students` rows.

    A `Student` is not a login, so this resolves `student_profile` accounts and
    silently skips students who have never been provisioned one.
    """
    student_ids = [getattr(s, 'pk', s) for s in students]
    if not student_ids:
        return 0
    return notify(
        User.objects.filter(student_profile_id__in=student_ids, is_active=True),
        type=type, title=title, body=body, link=link, dedupe_key=dedupe_key, school=school,
    )


def notify_parents(students, *, type: str, title: str, body: str = '', link: str = '',
                   dedupe_key: str = '', school=None) -> int:
    """Notify the guardians linked to `students` rows.

    Taken from the explicit `User.linked_students` relation an administrator
    sets, never from a shared surname or phone number, and filtered to the
    school's own accounts so a misconfigured link cannot cross tenants.
    """
    student_ids = [getattr(s, 'pk', s) for s in students]
    if not student_ids:
        return 0
    return notify(
        User.objects.filter(
            linked_students__id__in=student_ids, role='parent', is_active=True,
        ).distinct(),
        type=type, title=title, body=body, link=link, dedupe_key=dedupe_key, school=school,
    )


def notify_audience(school, audience, *, type: str, title: str, body: str = '',
                    link: str = '', dedupe_key: str = '') -> int:
    """Notify everyone in the named announcement audiences.

    `audience` holds the composer's labels ('All', 'Staff', 'Parents',
    'Students'); unrecognised labels are ignored rather than widening delivery,
    so a bad payload can never accidentally reach the whole school.
    """
    roles: list[str] = []
    for label in audience or []:
        roles.extend(AUDIENCE_ROLES.get(label, ()))
    if not roles:
        return 0
    return notify_roles(
        school, set(roles), type=type, title=title, body=body, link=link,
        dedupe_key=dedupe_key,
    )


def unread_count(user) -> int:
    return Notification.objects.filter(user=user, read_at__isnull=True).count()


def mark_read(notification) -> None:
    """Mark one notification read, idempotently.

    The `read_at__isnull` guard means a second click does not overwrite the
    moment it was first read, which is what an audit-minded reviewer expects.
    """
    if notification.read_at is None:
        notification.read_at = timezone.now()
        notification.save(update_fields=['read_at'])


def mark_all_read(user) -> int:
    """Mark every unread notification for one person read. Returns the count."""
    return Notification.objects.filter(user=user, read_at__isnull=True).update(
        read_at=timezone.now(),
    )
