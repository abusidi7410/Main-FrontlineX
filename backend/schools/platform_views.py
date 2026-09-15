import secrets

from django.db import IntegrityError
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import User
from accounts.permissions import IsSuperAdmin
from records.models import Student
from .models import Announcement, AuditLog, School, SchoolSubscription, SubscriptionPlan, SupportTicket

PLATFORM_STATUSES = {'active', 'trial', 'grace', 'pending_payment', 'suspended'}
_SCHOOL_TYPE_CHOICES = {'nursery', 'primary', 'secondary', 'mixed'}
_SUPPORT_STATUSES = {'pending', 'under_review', 'verified'}


def _plan_for_tier(tier_id):
    if tier_id and str(tier_id).startswith('t'):
        index = str(tier_id)[1:]
        if index.isdigit():
            return SubscriptionPlan.objects.filter(
                min_students__lte=int(index)
            ).order_by('-min_students').first()
    return SubscriptionPlan.objects.first() or SubscriptionPlan(name='t100', min_students=1, max_students=100)


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


def _platform_school_detail(school):
    subscription = SchoolSubscription.objects.filter(school=school).first()
    plan = subscription.plan if subscription and subscription.plan_id else None
    return {
        **_platform_school_data(school),
        'slug': school.slug,
        'schoolType': school.school_type,
        'address': school.address,
        'lga': school.lga,
        'phone': school.phone,
        'email': school.email,
        'website': school.website,
        'primaryColor': school.primary_color,
        'secondaryColor': school.secondary_color,
        'currentSession': school.current_session,
        'currentTerm': school.current_term,
        'isActive': school.is_active,
        'studentCount': Student.objects.filter(school=school, status=Student.Status.ACTIVE).count(),
        'staffCount': school.staff.count(),
        'mrr': float(plan.monthly_price) if plan else 0,
        'tierId': plan.name if plan else 't100',
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

    def post(self, request):
        errors = {}
        name = (request.data.get('name') or '').strip()
        email = (request.data.get('email') or '').strip().lower()
        state = (request.data.get('state') or '').strip()
        lga = (request.data.get('lga') or '').strip()
        address = (request.data.get('address') or '').strip()
        phone = (request.data.get('phone') or '').strip()
        school_type = (request.data.get('schoolType') or 'mixed').strip()

        if not name:
            errors['name'] = 'School name is required.'
        if not email:
            errors['email'] = 'Contact email is required.'
        elif School.objects.filter(email=email).exists() or User.objects.filter(email=email).exists():
            errors['email'] = 'An account with this email already exists.'
        if not state:
            errors['state'] = 'State is required.'
        if not lga:
            errors['lga'] = 'LGA is required.'
        if not address:
            errors['address'] = 'Address is required.'
        if not phone:
            errors['phone'] = 'Phone is required.'
        if school_type not in _SCHOOL_TYPE_CHOICES:
            errors['schoolType'] = 'Unsupported school type.'
        if errors:
            return Response({'detail': 'Could not register school.', 'fieldErrors': errors},
                            status=status.HTTP_400_BAD_REQUEST)

        school = School.objects.create(
            name=name,
            school_type=school_type,
            address=address,
            state=state,
            lga=lga,
            phone=phone,
            email=email,
            website=(request.data.get('website') or '').strip(),
            primary_color=(request.data.get('primaryColor') or '#1e40af').strip(),
            secondary_color=(request.data.get('secondaryColor') or '#3b82f6').strip(),
            current_session=(request.data.get('currentSession') or '2025/2026').strip(),
            current_term=(request.data.get('currentTerm') or 'First Term').strip(),
            is_active=True,
        )
        plan = _plan_for_tier(request.data.get('tierId'))
        SchoolSubscription.objects.create(
            school=school,
            plan=plan,
            status=SchoolSubscription.Status.ACTIVE,
            starts_at=school.created_at,
        )
        default_password = f"Admin@{secrets.token_hex(4)}"
        try:
            admin = User.objects.create_user(
                email=email,
                password=default_password,
                first_name='School',
                last_name='Admin',
                role=User.Role.SCHOOL_ADMIN,
                school=school,
                is_active=True,
            )
        except IntegrityError:
            return Response(
                {
                    'detail': 'Could not register school.',
                    'fieldErrors': {'email': 'An account with this email already exists.'},
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        AuditLog.objects.create(
            actor=f'{request.user.get_full_name()} ({request.user.email})' if request.user.get_full_name() else request.user.email,
            role=request.user.role,
            action='school.register',
            target=school.name,
            detail='School registered by platform manager. Default admin account provisioned.',
            ip=_client_ip(request),
            severity='info',
        )
        AuditLog.objects.create(
            actor=f'{request.user.get_full_name()} ({request.user.email})' if request.user.get_full_name() else request.user.email,
            role=request.user.role,
            action='school.admin.provisioned',
            target=f'{school.name} ({admin.email})',
            detail='Default admin credentials generated; must be changed after first login.',
            ip=_client_ip(request),
            severity='info',
        )
        data = _platform_school_detail(school)
        data['defaultCredentials'] = {
            'email': admin.email,
            'password': default_password,
            'mustChangePassword': True,
        }
        return Response(data, status=status.HTTP_201_CREATED)


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


class PlatformSchoolDetailView(APIView):
    permission_classes = [IsAuthenticated, IsSuperAdmin]

    def get_school(self, pk):
        return School.objects.filter(id=pk).first()

    def get(self, request, pk):
        school = self.get_school(pk)
        if school is None:
            return Response({'detail': 'School not found.'}, status=status.HTTP_404_NOT_FOUND)
        return Response(_platform_school_detail(school))

    def patch(self, request, pk):
        school = self.get_school(pk)
        if school is None:
            return Response({'detail': 'School not found.'}, status=status.HTTP_404_NOT_FOUND)

        fields = {
            'name': 'name',
            'schoolType': 'school_type',
            'address': 'address',
            'state': 'state',
            'lga': 'lga',
            'phone': 'phone',
            'email': 'email',
            'website': 'website',
            'primaryColor': 'primary_color',
            'secondaryColor': 'secondary_color',
            'currentSession': 'current_session',
            'currentTerm': 'current_term',
        }
        updated = []
        for key, attr in fields.items():
            if key in request.data:
                value = (request.data.get(key) or '').strip() if isinstance(request.data.get(key), str) else request.data.get(key)
                setattr(school, attr, value)
                updated.append(attr.replace('_', ' '))

        school_type = request.data.get('schoolType')
        if school_type and school_type not in _SCHOOL_TYPE_CHOICES:
            return Response({'detail': 'Unsupported school type.'}, status=status.HTTP_400_BAD_REQUEST)
        new_email = (request.data.get('email') or '').strip().lower()
        if new_email and School.objects.filter(email=new_email).exclude(id=school.id).exists():
            return Response({'detail': 'A school with this email already exists.'}, status=status.HTTP_400_BAD_REQUEST)

        school.save()
        AuditLog.objects.create(
            actor=f'{request.user.get_full_name()} ({request.user.email})' if request.user.get_full_name() else request.user.email,
            role=request.user.role,
            action='school.updated',
            target=school.name,
            detail=', '.join(updated) or 'details updated',
            ip=_client_ip(request),
            severity='info',
        )
        return Response(_platform_school_detail(school))


class PlatformSupportTicketListView(APIView):
    permission_classes = [IsAuthenticated, IsSuperAdmin]

    def get(self, request):
        tickets = SupportTicket.objects.all()[:200]
        return Response([_ticket_json(t) for t in tickets])

    def post(self, request):
        subject = (request.data.get('subject') or '').strip()
        requester = (request.data.get('requester') or '').strip().lower()
        if not subject:
            return Response({'detail': 'Subject is required.'}, status=status.HTTP_400_BAD_REQUEST)
        if not requester:
            return Response({'detail': 'Requester email is required.'}, status=status.HTTP_400_BAD_REQUEST)
        school = None
        school_id = request.data.get('schoolId')
        if school_id:
            school = School.objects.filter(id=school_id).first()
        ticket = SupportTicket.objects.create(
            school=school,
            requester=requester,
            subject=subject,
            message=(request.data.get('message') or '').strip(),
            status=SupportTicket.Status.PENDING,
        )
        AuditLog.objects.create(
            actor=f'{request.user.get_full_name()} ({request.user.email})' if request.user.get_full_name() else request.user.email,
            role=request.user.role,
            action='support.ticket.created',
            target=school.name if school else requester,
            detail=subject,
            ip=_client_ip(request),
            severity='info',
        )
        return Response(_ticket_json(ticket), status=status.HTTP_201_CREATED)


class PlatformSupportTicketStatusView(APIView):
    permission_classes = [IsAuthenticated, IsSuperAdmin]

    def post(self, request, pk):
        ticket = SupportTicket.objects.filter(id=pk).first()
        if ticket is None:
            return Response({'detail': 'Ticket not found.'}, status=status.HTTP_404_NOT_FOUND)
        next_status = (request.data.get('status') or '').strip()
        if next_status not in _SUPPORT_STATUSES:
            return Response({'detail': 'Invalid status.'}, status=status.HTTP_400_BAD_REQUEST)
        previous = ticket.status
        ticket.status = next_status
        ticket.save(update_fields=['status', 'updated_at'])
        AuditLog.objects.create(
            actor=f'{request.user.get_full_name()} ({request.user.email})' if request.user.get_full_name() else request.user.email,
            role=request.user.role,
            action='support.ticket.status_changed',
            target=f'#{ticket.pk} {ticket.subject}',
            detail=f'{previous} → {ticket.status}',
            ip=_client_ip(request),
            severity='info',
        )
        return Response(_ticket_json(ticket))


class PlatformAnnouncementListView(APIView):
    permission_classes = [IsAuthenticated, IsSuperAdmin]

    def get(self, request):
        items = Announcement.objects.filter(scope=Announcement.Scope.PLATFORM)[:100]
        return Response([_announcement_json(a) for a in items])

    def post(self, request):
        title = (request.data.get('title') or '').strip()
        body = (request.data.get('body') or '').strip()
        if not title or not body:
            return Response({'detail': 'Title and body are required.'}, status=status.HTTP_400_BAD_REQUEST)
        item = Announcement.objects.create(
            author=request.user,
            title=title,
            body=body,
            audience=['all'],
            scope=Announcement.Scope.PLATFORM,
        )
        AuditLog.objects.create(
            actor=f'{request.user.get_full_name()} ({request.user.email})' if request.user.get_full_name() else request.user.email,
            role=request.user.role,
            action='announcement.broadcast',
            target='All schools',
            detail=title,
            ip=_client_ip(request),
            severity='warning',
        )
        return Response(_announcement_json(item), status=status.HTTP_201_CREATED)


def _ticket_json(ticket):
    return {
        'id': str(ticket.id),
        'school': ticket.school.name if ticket.school_id else '',
        'subject': ticket.subject,
        'requester': ticket.requester,
        'status': ticket.status,
        'createdAt': ticket.created_at.isoformat(),
    }


def _announcement_json(item):
    author = item.author.get_full_name() or item.author.email if item.author_id else 'Platform'
    return {
        'id': str(item.id),
        'title': item.title,
        'body': item.body,
        'audience': item.audience,
        'author': author,
        'createdAt': item.created_at.isoformat(),
    }


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