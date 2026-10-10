"""Shared helpers for school-scoped account management.

Kept small and dependency-free so both the auth views and the account
management views can rely on the same pagination and audit behaviour.
"""
from django.utils import timezone

from schools.models import AuditLog


def paginate(queryset, request, serializer_class, context=None):
    """Offset pagination with sane clamping (mirrors records._paginate).

    Bound pageSize so a single request can never select an unbounded number
    of rows — important when thousands of schools share a database.
    """
    try:
        page = max(int(request.query_params.get('page', 1)), 1)
        page_size = int(request.query_params.get('pageSize', 20))
    except ValueError:
        page, page_size = 1, 20
    page_size = min(max(page_size, 1), 200)
    count = queryset.count()
    start = (page - 1) * page_size
    items = queryset[start:start + page_size]
    serializer = serializer_class(items, many=True, context=context or {})
    return {
        'results': serializer.data,
        'count': count,
        'page': page,
        'pageSize': page_size,
    }


DEFAULT_TEMPORARY_PASSWORD = 'FRNX'


def audit(
    request, action, target, detail='', severity='info',
    *, entity='', entity_id='', before=None, after=None,
):
    """Record an audit event with the actor resolved from the request.

    `actor` stays a readable string for the platform screens. `user`, `entity`
    and `entity_id` are what a reviewer filters on when following one record's
    trail, and `before`/`after` hold the values an operation changed so the
    entry is reviewable without diffing every table.
    """
    user = getattr(request, 'user', None)
    if not getattr(user, 'is_authenticated', False):
        user = None
    actor = (user.get_full_name() or user.email) if user else 'system'
    AuditLog.objects.create(
        actor=f'{actor} ({user.email})' if user else actor,
        role=getattr(user, 'role', '') or '',
        action=action,
        target=str(target)[:255],
        detail=str(detail)[:2000],
        ip=_client_ip(request),
        severity=severity,
        school=getattr(user, 'school', None),
        user=user,
        entity=entity or '',
        entity_id=str(entity_id or '')[:40],
        before=before or {},
        after=after or {},
    )


def _client_ip(request):
    forwarded = request.META.get('HTTP_X_FORWARDED_FOR')
    if forwarded:
        return forwarded.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR', '')


def now():
    return timezone.now()