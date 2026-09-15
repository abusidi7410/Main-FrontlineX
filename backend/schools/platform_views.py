from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.permissions import IsSuperAdmin
from records.models import Student
from .models import AuditLog, School, SchoolSubscription

PLATFORM_STATUSES = {'active', 'trial', 'grace', 'pending_payment', 'suspended'}


def _school_status(school, subscription):
    if school.is_active:
        return 'active'
    if subscription:
        if subscription.status == SchoolSubscription.Status.SUSPENDED:
            return 'suspended'
        if subscription.status in (
            SchoolSubscription.Status.PENDING,
            SchoolSubscription.Status.EXPIRED,
        ):
            return 'pending_payment'
    return 'trial'


def _client_ip(request):
    forwarded = request.META.get('HTTP_X_FORWARDED_FOR')
    if forwarded:
        return forwarded.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR', '')


def _platform_school_data(school):
    subscription = SchoolSubscription.objects.filter(school=school).first()
    plan = subscription.plan if subscription and subscription.plan_id else None
    return {
        'id': str(school.id),
        'name': school.name,
        'state': school.state,
        'students': Student.objects.filter(school=school, status=Student.Status.ACTIVE).count(),
        'tierId': plan.name if plan else 't100',
        'status': _school_status(school, subscription),
        'mrr': float(plan.monthly_price) if plan else 0,
        'createdAt': school.created_at.isoformat(),
    }


class PlatformSchoolListView(APIView):
    permission_classes = [IsAuthenticated, IsSuperAdmin]

    def get(self, request):
        schools = School.objects.all()
        search = request.query_params.get('search', '').strip()
        if search:
            schools = schools.filter(name__icontains=search) | schools.filter(state__icontains=search)
        status_filter = request.query_params.get('status', '').strip()
        data = [
            s for s in (
                _platform_school_data(c) for c in schools
            ) if not status_filter or s['status'] == status_filter
        ]
        return Response(data)


class PlatformSchoolStatusView(APIView):
    permission_classes = [IsAuthenticated, IsSuperAdmin]

    def patch(self, request, pk):
        school = School.objects.filter(id=pk).first()
        if school is None:
            return Response({'detail': 'School not found.'}, status=status.HTTP_404_NOT_FOUND)
        next_status = request.data.get('status', '').strip()
        if next_status not in PLATFORM_STATUSES:
            return Response({'detail': 'Invalid status.'}, status=status.HTTP_400_BAD_REQUEST)

        current = _school_status(school, SchoolSubscription.objects.filter(school=school).first())

        active_statuses = {'active', 'trial', 'grace'}
        school.is_active = next_status in active_statuses
        school.save(update_fields=['is_active'])

        subscription = SchoolSubscription.objects.filter(school=school).first()
        if subscription:
            if next_status == 'suspended':
                subscription.status = SchoolSubscription.Status.SUSPENDED
            elif next_status == 'pending_payment':
                subscription.status = SchoolSubscription.Status.PENDING
            elif next_status in active_statuses:
                subscription.status = SchoolSubscription.Status.ACTIVE
            subscription.save(update_fields=['status'])

        AuditLog.objects.create(
            actor=f'{request.user.get_full_name()} ({request.user.email})' if request.user.get_full_name() else request.user.email,
            role=request.user.role,
            action='school.status.changed',
            target=school.name,
            detail=f'{current} → {next_status}',
            ip=_client_ip(request),
            severity='critical' if next_status == 'suspended' else 'info',
        )

        return Response(_platform_school_data(school))


class PlatformAuditListView(APIView):
    permission_classes = [IsAuthenticated, IsSuperAdmin]

    def get(self, request):
        events = AuditLog.objects.all()[:200]
        return Response([
            {
                'id': str(e.id),
                'actor': e.actor,
                'action': e.action,
                'target': e.target,
                'ip': e.ip,
                'createdAt': e.created_at.isoformat(),
                'severity': e.severity,
                'role': e.role,
            }
            for e in events
        ])