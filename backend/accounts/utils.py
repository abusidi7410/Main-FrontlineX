"""Shared helpers for school-scoped account management.

Kept small and dependency-free so both the auth views and the account
management views can rely on the same pagination and audit behaviour.
"""
import secrets

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


def generate_temp_password():
    """Random one-time password that satisfies the default validators.

    ``token_urlsafe`` output is base64url (letters + digits); 12 bytes yields
    a 16-character password, comfortably above the 8-char minimum.
    """
    return f'Fnx{secrets.token_urlsafe(9)}'


def audit(request, action, target, detail='', severity='info'):
    """Record an audit event with the actor resolved from the request."""
    actor = request.user.get_full_name() or request.user.email
    AuditLog.objects.create(
        actor=f'{actor} ({request.user.email})',
        role=request.user.role,
        action=action,
        target=str(target)[:255],
        detail=str(detail)[:2000],
        ip=_client_ip(request),
        severity=severity,
    )


def _client_ip(request):
    forwarded = request.META.get('HTTP_X_FORWARDED_FOR')
    if forwarded:
        return forwarded.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR', '')


def now():
    return timezone.now()