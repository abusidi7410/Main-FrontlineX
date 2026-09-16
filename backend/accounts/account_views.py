"""School-scoped account management API.

Lets a school provision login accounts for its own students, teachers,
admins and finance staff. Every query is hard-scoped to the caller's
school (``request.user.school_id``) and every write is audited.

Scaling notes (thousands of schools on one database):
  * Composite indexes on (school, role, is_active) serve list/count hot paths.
  * ``select_related`` avoids N+1 on linked student/staff records.
  * Offset pagination is clamped to a 200-row page size.
"""
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import User
from .permissions import require_roles
from .serializers import (
    AccountCreateSerializer,
    AccountSerializer,
    AccountUpdateSerializer,
)
from .utils import audit, generate_temp_password, now, paginate

# Roles that may manage school accounts.
MANAGE_ACCOUNTS = require_roles('school_admin', 'principal', 'secretary')

# Which roles each manager may create/edit (and therefore see in lists).
ROLE_MANAGEMENT_MATRIX = {
    'school_admin': {
        'school_admin', 'principal', 'teacher', 'accountant', 'secretary',
        'student', 'parent',
    },
    'principal': {'teacher', 'accountant', 'secretary', 'student', 'parent'},
    'secretary': {'student', 'parent'},
}


def _allowed_roles(user):
    return ROLE_MANAGEMENT_MATRIX.get(user.role, set())


def _account_queryset(school_id):
    """Accounts belonging to one school, eager-loaded for serialization."""
    return User.objects.filter(school_id=school_id).select_related(
        'student_profile', 'staff_profile',
    )


def _get_scoped_account(school_id, pk):
    return get_object_or_404(User, id=pk, school_id=school_id)


class AccountListView(APIView):
    """GET/POST /api/v1/accounts/users/"""

    permission_classes = [IsAuthenticated, MANAGE_ACCOUNTS]

    def get(self, request):
        qs = _account_queryset(request.user.school_id)

        search = request.query_params.get('search', '').strip()
        if search:
            qs = qs.filter(
                Q(first_name__icontains=search)
                | Q(last_name__icontains=search)
                | Q(email__icontains=search)
            )

        role = request.query_params.get('role', '').strip()
        if role:
            qs = qs.filter(role=role)
        elif request.user.role != 'school_admin':
            # Non-super-managers only see roles inside their matrix.
            qs = qs.filter(role__in=_allowed_roles(request.user))

        account_status = request.query_params.get('status', '').strip()
        if account_status == 'active':
            qs = qs.filter(is_active=True)
        elif account_status == 'inactive':
            qs = qs.filter(is_active=False)

        data = paginate(qs, request, AccountSerializer)
        return Response(data)

    def post(self, request):
        serializer = AccountCreateSerializer(
            data=request.data,
            context={
                'request': request,
                'allowed_roles': _allowed_roles(request.user),
                'school_id': request.user.school_id,
            },
        )
        serializer.is_valid(raise_exception=True)
        data = serializer.create(serializer.validated_data)
        return Response(data, status=status.HTTP_201_CREATED)


class AccountStatsView(APIView):
    """GET /api/v1/accounts/users/stats/ — grouped active counts.

    A single grouped query serves the whole card row, so latency stays flat
    no matter how many accounts a school holds.
    """

    permission_classes = [IsAuthenticated, MANAGE_ACCOUNTS]

    def get(self, request):
        school_id = request.user.school_id
        counts = dict(
            User.objects.filter(school_id=school_id)
            .values('role')
            .annotate(total=Count('id'))
            .values_list('role', 'total'),
        )
        active_counts = dict(
            User.objects.filter(school_id=school_id, is_active=True)
            .values('role')
            .annotate(total=Count('id'))
            .values_list('role', 'total'),
        )
        roles = [
            'school_admin', 'principal', 'teacher',
            'accountant', 'secretary', 'student', 'parent',
        ]
        return Response({
            'total': sum(counts.values()),
            'active': sum(active_counts.values()),
            'byRole': {
                role: {
                    'total': counts.get(role, 0),
                    'active': active_counts.get(role, 0),
                }
                for role in roles
            },
        })


class AccountDetailView(APIView):
    """GET/PATCH/DELETE /api/v1/accounts/users/<pk>/"""

    permission_classes = [IsAuthenticated, MANAGE_ACCOUNTS]

    def get(self, request, pk):
        account = _get_scoped_account(request.user.school_id, pk)
        return Response(AccountSerializer(account).data)

    def patch(self, request, pk):
        account = _get_scoped_account(request.user.school_id, pk)
        if account.pk == request.user.pk:
            return Response(
                {'detail': 'Edit your own details from your profile instead.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if account.role not in _allowed_roles(request.user):
            return Response(
                {'detail': 'You cannot manage accounts with that role.'},
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = AccountUpdateSerializer(
            data=request.data,
            partial=True,
            context={
                'request': request,
                'allowed_roles': _allowed_roles(request.user),
                'school_id': request.user.school_id,
                'target': account,
            },
        )
        serializer.is_valid(raise_exception=True)
        attrs = serializer.validated_data

        if attrs.get('fullName'):
            first, _, last = attrs['fullName'].strip().partition(' ')
            account.first_name = first.strip()
            account.last_name = last.strip()
        if attrs.get('phone') is not None:
            account.phone = attrs['phone'] or None
        if attrs.get('role'):
            account.role = attrs['role']
        account.save(update_fields=['first_name', 'last_name', 'phone', 'role', 'updated_at'])

        audit(
            request,
            'account.updated',
            f'{account.get_full_name()} ({account.email})',
            f'Role {account.role} account updated.',
        )
        return Response(AccountSerializer(account).data)

    def delete(self, request, pk):
        account = _get_scoped_account(request.user.school_id, pk)
        if account.pk == request.user.pk:
            return Response(
                {'detail': 'You cannot delete your own account.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if account.role not in _allowed_roles(request.user):
            return Response(
                {'detail': 'You cannot manage accounts with that role.'},
                status=status.HTTP_403_FORBIDDEN,
            )
        if account.role == User.Role.SCHOOL_ADMIN and not _has_other_active_admin(
            request.user.school_id, account.pk,
        ):
            return Response(
                {'detail': 'A school must keep at least one active admin.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        label = f'{account.get_full_name()} ({account.email})'
        role = account.role
        account.delete()
        audit(request, 'account.deleted', label, f'Role {role} account deleted.')
        return Response(status=status.HTTP_204_NO_CONTENT)


class AccountPasswordResetView(APIView):
    """POST /api/v1/accounts/users/<pk>/reset-password/

    Generates a temporary password and returns it once as
    ``defaultCredentials``. The account must change it on next login.
    """

    permission_classes = [IsAuthenticated, MANAGE_ACCOUNTS]

    def post(self, request, pk):
        account = _get_scoped_account(request.user.school_id, pk)
        if account.role not in _allowed_roles(request.user):
            return Response(
                {'detail': 'You cannot manage accounts with that role.'},
                status=status.HTTP_403_FORBIDDEN,
            )

        password = generate_temp_password()
        account.set_password(password)
        account.must_change_password = True
        account.last_password_reset_at = now()
        account.save(update_fields=['password', 'must_change_password', 'last_password_reset_at'])

        audit(
            request,
            'account.password.reset',
            f'{account.get_full_name()} ({account.email})',
            'Temporary password issued; must be changed on next login.',
            severity='warning',
        )
        return Response({
            'id': str(account.pk),
            'defaultCredentials': {
                'email': account.email,
                'password': password,
                'mustChangePassword': True,
            },
        })


class AccountStatusView(APIView):
    """POST /api/v1/accounts/users/<pk>/activate/|deactivate/"""

    permission_classes = [IsAuthenticated, MANAGE_ACCOUNTS]

    def post(self, request, pk, action):
        if action not in ('activate', 'deactivate'):
            return Response(
                {'detail': 'Unknown action.'},
                status=status.HTTP_404_NOT_FOUND,
            )
        account = _get_scoped_account(request.user.school_id, pk)
        if account.pk == request.user.pk:
            return Response(
                {'detail': 'You cannot change your own account status.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if account.role not in _allowed_roles(request.user):
            return Response(
                {'detail': 'You cannot manage accounts with that role.'},
                status=status.HTTP_403_FORBIDDEN,
            )

        if action == 'deactivate':
            if account.role == User.Role.SCHOOL_ADMIN and not _has_other_active_admin(
                request.user.school_id, account.pk,
            ):
                return Response(
                    {'detail': 'A school must keep at least one active admin.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            account.is_active = False
            event = 'account.deactivated'
            severity = 'warning'
        else:
            account.is_active = True
            event = 'account.activated'
            severity = 'info'
        account.save(update_fields=['is_active'])

        audit(
            request,
            event,
            f'{account.get_full_name()} ({account.email})',
            f'Role {account.role} account now {"active" if account.is_active else "inactive"}.',
            severity=severity,
        )
        return Response(AccountSerializer(account).data)


def _has_other_active_admin(school_id, exclude_pk):
    return User.objects.filter(
        school_id=school_id,
        role=User.Role.SCHOOL_ADMIN,
        is_active=True,
    ).exclude(pk=exclude_pk).exists()