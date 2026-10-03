"""Announcements (spec 30/32) — school notices and their audience rules.

An announcement is one message addressed to an audience. Two things make this
more than a plain list:

* **Audience is a delivery boundary, not decoration.** A parent reading
  `/announcements/` must not be able to see a notice addressed to staff only,
  and a teacher must not be handed a parent-only notice as if it were theirs.
  So visibility is resolved from the reader's own role, never from a
  client-supplied filter.
* **Publishing is a fan-out.** A notice has to reach the notification centre of
  everyone it was addressed to, not just the Announcements page, or the header
  bell stays silent for the people the message was actually written for.

The labels in `audience` are the composer's own strings ('All', 'Staff',
'Parents', 'Students'). They are compared case-insensitively because the
platform broadcast endpoint has always written a lowercase 'all', and matching
exactly would silently hide those from every reader.
"""

from django.db.models import Q, QuerySet
from django.utils import timezone

from accounts.permissions import has_permission
from accounts.services import notifications as notify_svc
from schools.models import Announcement

# Which composer label a role belongs to. A role can sit in more than one
# group ('All' is not a group, it is handled separately as a wildcard).
ROLE_AUDIENCES = {
    'school_admin': {'staff'},
    'principal': {'staff'},
    'teacher': {'staff'},
    'accountant': {'staff'},
    'secretary': {'staff'},
    'parent': {'parents'},
    'student': {'students'},
}

ALL = 'all'


def normalise_audience(audience) -> list[str]:
    """Lower-cased, de-duplicated, known-only audience labels.

    Unrecognised labels are dropped rather than treated as 'All'. A payload
    that arrives with a typo must fail closed — a wider audience than intended
    is the one mistake here that cannot be undone once sent.
    """
    known = {ALL, 'staff', 'parents', 'students'}
    out: list[str] = []
    for label in audience or []:
        value = str(label).strip().lower()
        if value in known and value not in out:
            out.append(value)
    return out


def audience_roles(audience) -> list[str]:
    """Roles addressed by *audience*, expanded for fan-out."""
    labels = normalise_audience(audience)
    if ALL in labels:
        return list(notify_svc.AUDIENCE_ROLES['All'])
    roles: list[str] = []
    for role, groups in ROLE_AUDIENCES.items():
        if groups & set(labels):
            roles.append(role)
    return roles


def _matches(user, item) -> bool:
    """Whether *user* is in *item*'s audience.

    Used by the queryset builder for the roles whose audience cannot be
    expressed as a plain database filter.
    """
    labels = normalise_audience(item.audience)
    # An announcement with no audience recorded is treated as school-wide, so a
    # row imported or written by an older code path stays visible instead of
    # becoming invisible to everyone.
    if not labels or ALL in labels:
        return True
    return bool(ROLE_AUDIENCES.get(user.role, set()) & set(labels))


def visible_to(user) -> QuerySet:
    """Every announcement *user* is allowed to read.

    Staff holding `communication.read` see the whole school board, because
    running the school means seeing what has gone out. Parents and students see
    only their own audience — they hold no management permission, and the
    spec gives them announcements as a service rather than a right of access.
    """
    live = Q(expires_at__isnull=True) | Q(expires_at__gt=timezone.now())

    if user.role == 'platform_manager':
        return Announcement.objects.filter(live, scope=Announcement.Scope.PLATFORM)

    if user.school_id is None:
        return Announcement.objects.none()

    board = Q(school_id=user.school_id) | Q(school__isnull=True)

    if has_permission(user.role, 'communication.read'):
        return Announcement.objects.filter(board, live).select_related('author', 'school')

    # Audience-filtered self-service. Matching happens in Python because the
    # audience is a JSON list of free-text labels, not a column. The set is
    # bounded by the live notices in one school (tens of rows), not by the
    # number of users, so this stays cheap. `.only()` keeps the wide text
    # columns off the query, since only the audience is needed to decide.
    candidates = Announcement.objects.filter(board, live).only('pk', 'audience')
    allowed = [i.pk for i in candidates if _matches(user, i)]
    return Announcement.objects.filter(pk__in=allowed).select_related('author', 'school')


def publish(item, *, author=None) -> int:
    """Fan a published announcement out to its audience's notification centres.

    Idempotent per announcement: the dedupe key is derived from the row id, so
    re-running a publish (an edit, a retry, a management command) updates who
    it reaches without giving anyone the same notice twice.
    """
    author = author or item.author
    name = (author.get_full_name() or author.email) if author is not None else 'The school'
    return notify_svc.notify_roles(
        item.school,
        audience_roles(item.audience),
        type='announcement',
        title=item.title,
        body=item.body[:280],
        link='/communication',
        dedupe_key=f'announcement:{item.pk}',
    )


def create(*, school, author, title, body, audience, is_pinned=False, expires_at=None) -> Announcement:
    """Create a school announcement and fan it out."""
    item = Announcement.objects.create(
        school=school,
        author=author,
        title=title,
        body=body,
        audience=normalise_audience(audience),
        scope=Announcement.Scope.SCHOOL,
        is_pinned=is_pinned,
        expires_at=expires_at,
    )
    publish(item)
    return item


def create_platform(*, author, title, body, is_pinned=False, expires_at=None) -> Announcement:
    """Create a broadcast visible to every school.

    Deliberately **not** fanned out, unlike `create`. Two reasons:

    * A platform broadcast already appears on every school's announcement board
      (`visible_to` includes rows with no school), so the message is delivered.
      Fan-out would be a second copy of the same text in a different place.
    * Fan-out here would write one row per user *across every tenant* on a
      single POST. `Notification.school` is a single-school foreign key, so a
      cross-tenant row could not honestly record which school it belonged to,
      and the write cost would scale with total user count rather than with the
      audience that was chosen.

    A school that wants this in its bell has to publish it as a school
    announcement, which is the addressed path.
    """
    return Announcement.objects.create(
        school=None,
        author=author,
        title=title,
        body=body,
        audience=[ALL],
        scope=Announcement.Scope.PLATFORM,
        is_pinned=is_pinned,
        expires_at=expires_at,
    )


def serialise(item) -> dict:
    """The wire shape the frontend `Announcement` type expects."""
    author = item.author
    name = (author.get_full_name() or author.email) if author is not None else 'Platform'
    return {
        'id': str(item.pk),
        'title': item.title,
        'body': item.body,
        # Returned in the composer's own capitalisation so the UI can render
        # the label it sent without a lookup table.
        'audience': [
            {'all': 'All', 'staff': 'Staff', 'parents': 'Parents', 'students': 'Students'}[label]
            for label in normalise_audience(item.audience)
        ] or ['All'],
        'author': name,
        'createdAt': item.created_at.isoformat(),
        'isPinned': item.is_pinned,
        'expiresAt': item.expires_at.isoformat() if item.expires_at else None,
        'scope': item.scope,
    }
