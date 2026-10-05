import secrets
from datetime import datetime, timedelta

from django.core.cache import cache
from django.db import IntegrityError, connection
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import User
from accounts.permissions import IsSuperAdmin
from records.models import Student
from records.services import announcements as announcement_service
from .models import Announcement, AuditLog, School, SchoolSubscription, SubscriptionPlan, SupportTicket
from .status import school_status

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
        'status': school_status(school, subscription),
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


_OVERVIEW_RANGES = {'7d': 7, '30d': 30, '90d': 90}
_OVERVIEW_CACHE_TTL = 5 * 60


def _overview_range_days(request):
    requested = str(request.query_params.get('range', '30d')).lower()
    return _OVERVIEW_RANGES.get(requested, _OVERVIEW_RANGES['30d'])


def _overview_month_buckets(now):
    local_now = timezone.localtime(now)
    current_index = local_now.year * 12 + local_now.month - 1
    buckets = []
    for offset in range(5, -1, -1):
        index = current_index - offset
        year, month_zero_based = divmod(index, 12)
        month = month_zero_based + 1
        start = datetime(year, month, 1, tzinfo=local_now.tzinfo)
        next_index = index + 1
        next_year, next_month_zero_based = divmod(next_index, 12)
        end = datetime(
            next_year,
            next_month_zero_based + 1,
            1,
            tzinfo=local_now.tzinfo,
        )
        buckets.append((start, end))
    return buckets


def _overview_datetime(value):
    if value is None:
        return None
    if timezone.is_naive(value):
        value = timezone.make_aware(value, timezone.get_current_timezone())
    return value


def _overview_rows(now, range_days, auth_school_id):
    month_buckets = _overview_month_buckets(now)
    login_cutoff = now - timedelta(hours=24)
    payment_cutoff = now - timedelta(days=range_days)
    login_columns = [
        'MAX(u.last_login) AS last_active',
        'COUNT(DISTINCT CASE WHEN u.is_active = TRUE AND u.last_login >= %s THEN u.id END) AS active_logins_24h',
    ]
    login_params = [login_cutoff]
    for index, (start, end) in enumerate(month_buckets):
        login_columns.append(
            'COUNT(DISTINCT CASE WHEN u.is_active = TRUE AND u.last_login >= %s '
            'AND u.last_login < %s THEN u.id END) AS active_school_{}'.format(index)
        )
        login_params.extend([start, end])

    payment_columns = [
        "COUNT(DISTINCT CASE WHEN p.status = 'failed' AND p.created_at >= %s THEN p.id END) AS failed_payments",
    ]
    payment_params = [payment_cutoff]
    for index, (start, end) in enumerate(month_buckets):
        payment_columns.append(
            "COALESCE(SUM(CASE WHEN p.status = 'verified' AND p.created_at >= %s "
            "AND p.created_at < %s THEN p.amount ELSE 0 END), 0) AS revenue_{}".format(index)
        )
        payment_params.extend([start, end])

    active_school_columns = ', '.join(
        'COALESCE(lr.active_school_{}, 0) AS active_school_{}'.format(index, index)
        for index in range(len(month_buckets))
    )
    revenue_columns = ', '.join(
        'COALESCE(pr.revenue_{}, 0) AS revenue_{}'.format(index, index)
        for index in range(len(month_buckets))
    )
    active_school_output_columns = ', '.join(
        'active_school_{}'.format(index) for index in range(len(month_buckets))
    )
    revenue_output_columns = ', '.join(
        'revenue_{}'.format(index) for index in range(len(month_buckets))
    )
    scope_clause = ''
    scope_params = []
    if auth_school_id is not None:
        scope_clause = 'WHERE s.id = %s'
        scope_params.append(auth_school_id)

    sql = """
WITH student_counts AS (
    SELECT school_id, COUNT(*) AS students
    FROM records_student
    WHERE status = 'active'
    GROUP BY school_id
),
login_rollup AS (
    SELECT school_id, {login_columns}
    FROM accounts_user u
    WHERE u.school_id IS NOT NULL
    GROUP BY school_id
),
payment_rollup AS (
    SELECT school_id, {payment_columns}
    FROM records_payment p
    GROUP BY school_id
),
school_rollup AS (
    SELECT
        s.id AS school_id,
        s.name,
        s.state,
        s.is_active,
        ss.status AS subscription_status,
        ss.expires_at AS renewal_date,
        COALESCE(plan.name, 't100') AS plan,
        CASE
            WHEN s.is_active = TRUE THEN 'active'
            WHEN ss.status = 'suspended' THEN 'suspended'
            WHEN ss.status = 'grace' THEN 'grace'
            WHEN ss.status IN ('pending', 'expired') THEN 'pending_payment'
            ELSE 'trial'
        END AS status,
        CASE
            WHEN s.is_active = TRUE AND ss.status = 'active' THEN COALESCE(plan.monthly_price, 0)
            ELSE 0
        END AS mrr,
        COALESCE(sc.students, 0) AS students,
        lr.last_active,
        COALESCE(lr.active_logins_24h, 0) AS active_logins_24h,
        COALESCE(pr.failed_payments, 0) AS failed_payments,
        {active_school_columns},
        {revenue_columns}
    FROM schools_school s
    LEFT JOIN schools_schoolsubscription ss ON ss.school_id = s.id
    LEFT JOIN schools_subscriptionplan plan ON plan.id = ss.plan_id
    LEFT JOIN student_counts sc ON sc.school_id = s.id
    LEFT JOIN login_rollup lr ON lr.school_id = s.id
    LEFT JOIN payment_rollup pr ON pr.school_id = s.id
    {scope_clause}
)
SELECT
    school_id,
    name,
    state,
    plan,
    students,
    mrr,
    status,
    last_active,
    renewal_date,
    failed_payments,
    active_logins_24h,
    {active_school_output_columns},
    {revenue_output_columns}
FROM school_rollup
ORDER BY
    CASE status
        WHEN 'suspended' THEN 0
        WHEN 'pending_payment' THEN 1
        WHEN 'grace' THEN 2
        WHEN 'trial' THEN 3
        ELSE 4
    END,
    name
""".format(
        login_columns=', '.join(login_columns),
        payment_columns=', '.join(payment_columns),
        active_school_columns=active_school_columns,
        revenue_columns=revenue_columns,
        active_school_output_columns=active_school_output_columns,
        revenue_output_columns=revenue_output_columns,
        scope_clause=scope_clause,
    )
    params = login_params + payment_params + scope_params
    with connection.cursor() as cursor:
        cursor.execute(sql, params)
        columns = [column[0] for column in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]


def _overview_payload(rows, range_days):
    status_counts = {value: 0 for value in PLATFORM_STATUSES}
    mrr = 0.0
    active_logins = 0
    failed_payments = 0
    at_risk = []
    month_count = 6
    active_school_totals = [0] * month_count
    revenue_trend = [0.0] * month_count
    now = timezone.now()
    renewal_cutoff = now + timedelta(days=range_days)

    for row in rows:
        status = row['status']
        if status in status_counts:
            status_counts[status] += 1
        mrr += float(row['mrr'] or 0)
        active_logins += int(row['active_logins_24h'] or 0)
        failed_payments += int(row['failed_payments'] or 0)
        for index in range(month_count):
            if int(row[f'active_school_{index}'] or 0) > 0:
                active_school_totals[index] += 1
            revenue_trend[index] += float(row[f'revenue_{index}'] or 0)
        if status in {'grace', 'suspended', 'pending_payment'}:
            renewal_date = _overview_datetime(row['renewal_date'])
            last_active = _overview_datetime(row['last_active'])
            at_risk.append({
                'id': str(row['school_id']),
                'name': row['name'],
                'state': row['state'],
                'plan': row['plan'],
                'students': int(row['students'] or 0),
                'lastActive': last_active.isoformat() if last_active else None,
                'renewalDate': renewal_date.isoformat() if renewal_date else None,
                'status': status,
                'mrr': float(row['mrr'] or 0),
                'failedPayments': int(row['failed_payments'] or 0),
            })

    return {
        'mrr': round(mrr, 2),
        'mrrTrend': [round(value, 2) for value in revenue_trend],
        'schoolsByStatus': status_counts,
        'activeSchools': status_counts['active'],
        'activeSchoolsTrend': active_school_totals,
        'activeSchoolsGrowth': (
            active_school_totals[-1] - active_school_totals[-2]
            if len(active_school_totals) > 1
            else 0
        ),
        'activeLogins24h': active_logins,
        'failedPayments': failed_payments,
        'upcomingRenewals': sum(
            1
            for row in rows
            if _overview_datetime(row['renewal_date']) is not None
            and now <= _overview_datetime(row['renewal_date']) <= renewal_cutoff
        ),
        'atRiskSchools': at_risk,
        'rangeDays': range_days,
    }


class PlatformOverviewView(APIView):
    permission_classes = [IsAuthenticated, IsSuperAdmin]

    def get(self, request):
        range_days = _overview_range_days(request)
        auth_school_id = request.user.school_id
        cache_key = f"platform:overview:{range_days}:{auth_school_id or 'all'}"
        cached = cache.get(cache_key)
        if cached is not None:
            return Response(cached)

        rows = _overview_rows(timezone.now(), range_days, auth_school_id)
        payload = _overview_payload(rows, range_days)
        cache.set(cache_key, payload, _OVERVIEW_CACHE_TTL)
        return Response(payload)


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
            school=school,
        )
        AuditLog.objects.create(
            actor=f'{request.user.get_full_name()} ({request.user.email})' if request.user.get_full_name() else request.user.email,
            role=request.user.role,
            action='school.admin.provisioned',
            target=f'{school.name} ({admin.email})',
            detail='Default admin credentials generated; must be changed after first login.',
            ip=_client_ip(request),
            severity='info',
            school=school,
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

        current = school_status(school, SchoolSubscription.objects.filter(school=school).first())

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
            school=school,
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
            school=school,
        )
        return Response(_platform_school_detail(school))

    def delete(self, request, pk):
        """Permanently remove a school and every record tied to it.

        Requires ``confirm`` set to the school's exact name, so an accidental
        tap can never perform the deletion. The action is audited before the
        school is destroyed; audit log entries are global and survive the
        cascade.
        """
        school = self.get_school(pk)
        if school is None:
            return Response({'detail': 'School not found.'}, status=status.HTTP_404_NOT_FOUND)

        confirm = (request.data.get('confirm') or '').strip()
        if confirm != school.name:
            return Response(
                {'detail': 'Type the school name to confirm deletion.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        label = school.name
        AuditLog.objects.create(
            actor=f'{request.user.get_full_name()} ({request.user.email})' if request.user.get_full_name() else request.user.email,
            role=request.user.role,
            action='school.deleted',
            target=label,
            detail='School and all associated records permanently deleted.',
            ip=_client_ip(request),
            severity='critical',
            school=school,
        )

        school.delete()
        return Response(
            {'detail': f'{label} deleted.', 'deleted': label, 'remaining': School.objects.count()},
            status=status.HTTP_200_OK,
        )


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
            school=school,
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
            school=ticket.school,
        )
        return Response(_ticket_json(ticket))


class PlatformAnnouncementListView(APIView):
    permission_classes = [IsAuthenticated, IsSuperAdmin]

    def get(self, request):
        items = Announcement.objects.filter(scope=Announcement.Scope.PLATFORM)[:100]
        # Same serialiser the school board uses, so a broadcast and a school
        # notice are the same shape everywhere in the app.
        return Response([announcement_service.serialise(a) for a in items])

    def post(self, request):
        title = (request.data.get('title') or '').strip()
        body = (request.data.get('body') or '').strip()
        if not title or not body:
            return Response({'detail': 'Title and body are required.'}, status=status.HTTP_400_BAD_REQUEST)
        # Goes through the announcements service rather than a raw create so the
        # scope, audience normalisation and pin/expiry rules live in one place.
        # The service documents why a broadcast is not fanned out per recipient.
        item = announcement_service.create_platform(
            author=request.user,
            title=title,
            body=body,
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
        return Response(announcement_service.serialise(item), status=status.HTTP_201_CREATED)


def _ticket_json(ticket):
    return {
        'id': str(ticket.id),
        'school': ticket.school.name if ticket.school_id else '',
        'subject': ticket.subject,
        'requester': ticket.requester,
        'status': ticket.status,
        'createdAt': ticket.created_at.isoformat(),
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