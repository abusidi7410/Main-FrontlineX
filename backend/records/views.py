import uuid
from datetime import timedelta
from decimal import Decimal, InvalidOperation

from django.db import IntegrityError, transaction
from django.db.models import Count, F, Max, Prefetch, Q, Sum
from django.db.models.functions import Coalesce
from django.http import Http404
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime
from rest_framework import serializers, status
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.parsers import MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import Notification, NotificationPreference
from accounts.permissions import (
    HasSchool,
    has_permission,
    require_permissions,
    require_roles,
)
from accounts.services import notifications as notification_service
from accounts.utils import audit as log_audit
from schools.models import Announcement, School, SchoolSubscription
from .constants import DEFAULT_SUBJECTS
from .models import (
    EPOCH,
    AcademicSession,
    AttendanceRecord,
    ClassTeacherAssignment,
    Enrollment,
    FeeStructure,
    Invoice,
    LessonPlan,
    Payment,
    PromotionPolicy,
    ResultEntry,
    ResultSheet,
    SchoolClass,
    Section,
    StaffMember,
    Student,
    TimetableEntry,
    TimetablePeriod,
    invoice_item_amount,
)
from .services import academic as academic_service
from .services import admission as admission_service
from .services import ai_tools
from .services import announcements as announcement_service
from .services import attendance as attendance_service
from .services import billing as billing_service
from .services import enrollment as enrollment_service
from .services import events as event_service
from .services import results as result_service
from .services import promotion as promotion_service
from .services import timetable as timetable_service
from .student_import import (
    StudentImportError,
    analyse_import,
    parse_import_file,
)
from .serializers import (
    AttendanceCorrectionSerializer,
    AttendanceSubmitSerializer,
    InvoiceSerializer,
    PaymentSerializer,
    StaffMemberSerializer,
    StudentSerializer,
)

# Role guards for endpoints that predate the granular permission matrix.
CanWriteRecords = require_roles('school_admin', 'principal', 'secretary')
CanImportStudents = require_roles('school_admin')
CanReadFinance = require_roles('school_admin', 'principal', 'accountant', 'student')
CanWriteFinance = require_roles('school_admin', 'accountant')
FINANCE_WRITE_ROLES = ('school_admin', 'accountant')
SELF_SERVICE_METHODS = ('card', 'bank_transfer', 'online', 'ussd')

# Granular equivalents (spec §39). These are the guards used by the student
# create/update/transfer/roster endpoints: they name a business capability
# rather than a role, so a student's own role can never satisfy them.
CanCreateStudent = require_permissions('students.register')
CanWriteStudent = require_permissions('students.write')
CanReadAttendance = require_permissions('attendance.read')
# Submitting a register is a responsibility, not just a capability: `attendance.write`
# holds only for school admins and teachers, so a principal or secretary is read-only
# on attendance. Which *classes* a teacher may submit is enforced separately by the
# class-teacher assignment (see services.attendance.require_can_submit).
CanWriteAttendance = require_permissions('attendance.write')
# Amending an already-taken register is a supervisory act, distinct from taking it.
CanCorrectAttendance = require_permissions('attendance.correct')

# Staff records and the school's class/subject configuration are writable
# capabilities, not a consequence of merely being logged in. `HasSchool` alone
# let any pupil or parent login create and delete staff (see the regression
# tests in test_authorisation_regressions.py).
CanWriteStaff = require_permissions('staff.write')
CanWriteAcademics = require_permissions('academics.write')
# Configuring the Payment Structure is its own capability, separate from
# recording invoices and payments. A bursar who can bill a class but must not
# reprice the school would be blocked by a finance.write check, and a principal
# who should see prices but not change them is correctly excluded.
CanWriteFeeStructure = require_permissions('finance.structure')
# Building the timetable is a single capability covering both the bell schedule
# and the lessons on it, because they are meaningless apart: a lesson needs a
# period, and changing the period changes what every lesson means.
CanWriteTimetable = require_permissions('timetable.write')


def _paginate(queryset, request, serializer_class, context=None):
    """Offset pagination bounded to 25 rows a page, 100 at most.

    Both `pageSize` and the snake_case `page_size` are accepted so the frontend
    can use either convention. The ceiling is deliberate: a client must not be
    able to ask for the whole school in one response, because every list screen
    is paged and an unbounded page silently becomes a full-table scan.
    """
    items, count, page, page_size = _pagination_window(queryset, request)
    serializer = serializer_class(items, many=True, context=context or {})
    return {
        'results': serializer.data,
        'count': count,
        'page': page,
        'pageSize': page_size,
        'totalPages': max((count + page_size - 1) // page_size, 1),
    }


def _pagination_window(queryset, request):
    try:
        raw_page = request.query_params.get('page', 1)
        page = max(int(raw_page), 1)
    except (TypeError, ValueError):
        raise ValidationError({'page': 'Enter a valid page number.'})
    try:
        raw_size = request.query_params.get('page_size') or request.query_params.get('pageSize')
        page_size = int(raw_size) if raw_size not in (None, '') else 25
    except (TypeError, ValueError):
        raise ValidationError({'pageSize': 'Enter a valid page size.'})
    page_size = min(max(page_size, 1), 100)
    count = queryset.count()
    start = (page - 1) * page_size
    return queryset[start:start + page_size], count, page, page_size


def _student_queryset(school_id):
    """School-scoped student queryset, annotated for a constant query cost.

    Keeps the two hot list endpoints (student list, student detail) off the
    N+1 path: attendance counts, outstanding fees and the destination school
    are all resolved in the page query or a single prefetch (spec §72).
    """
    return (
        Student.objects
        .for_roster()
        .filter(school_id=school_id)
        .select_related('transferred_to')
        .prefetch_related(
            Prefetch(
                'enrollments',
                queryset=Enrollment.objects.select_related(
                    'academic_session', 'class_obj', 'section',
                ),
                to_attr='_enrollment_history_cache',
            ),
        )
    )


# ── Students ───────────────────────────────────────────────────────────────

# An admission invoice is due 30 days out, the same window the registration
# workflow uses, so OVERDUE means the same thing on both paths.
ADMISSION_INVOICE_DUE_DAYS = 30


def _filtered_students(request, *, search='', class_name='', class_id='', student_status='',
                       section='', session_id='', enrollment_status=''):
    """The student list, filtered in the database rather than in the client.

    The base queryset is already school-scoped, so a `class_id` belonging to
    another school matches nothing instead of leaking that school's class.
    Class, section and session membership all come from the *active enrollment*
    rather than the denormalised `Student.class_name` mirror, so a stale mirror
    cannot decide the list. Newest admissions come first.
    """
    qs = _student_queryset(request.user.school_id)
    if search:
        qs = qs.filter(
            Q(first_name__icontains=search)
            | Q(last_name__icontains=search)
            | Q(admission_number__icontains=search)
        )
    if class_id:
        # Membership comes from the active enrollment, not the denormalised
        # `Student.class_name` mirror, so a stale mirror cannot decide the list.
        qs = qs.filter(
            enrollments__class_obj_id=class_id,
            enrollments__status=Enrollment.Status.ACTIVE,
        ).distinct()
    elif class_name:
        qs = qs.filter(class_name=class_name)
    if section:
        membership = Q(enrollments__status=Enrollment.Status.ACTIVE)
        try:
            uuid.UUID(str(section))
        except ValueError:
            membership &= Q(enrollments__section__name=section)
        else:
            membership &= Q(enrollments__section_id=section)
        qs = qs.filter(membership).distinct()
    if session_id:
        qs = qs.filter(
            enrollments__academic_session_id=session_id,
            enrollments__status=Enrollment.Status.ACTIVE,
        ).distinct()
    if enrollment_status:
        if enrollment_status not in Enrollment.Status.values:
            raise ValidationError({
                'enrollmentStatus': f'"{enrollment_status}" is not an enrollment status.',
            })
        # A student who was never seated has no enrollment row at all, so
        # "not enrolled" has to mean that as well as the literal row state.
        if enrollment_status == Enrollment.Status.NOT_ENROLLED:
            qs = qs.filter(
                Q(enrollments__isnull=True)
                | Q(enrollments__status=Enrollment.Status.NOT_ENROLLED),
            ).distinct()
        else:
            qs = qs.filter(enrollments__status=enrollment_status).distinct()
    if student_status:
        if student_status not in Student.Status.values:
            raise ValidationError({'status': f'"{student_status}" is not a student status.'})
        qs = qs.filter(status=student_status)
    # Most recent enrollment first, taken from the enrollment's own timestamp —
    # never from the student id, which only records insert order. A student who
    # is not enrolled yet has no timestamp of their own to sort on, so it falls
    # back to when the record was created; `-id` keeps ties stable.
    return qs.annotate(
        latest_enrollment_at=Coalesce(Max('enrollments__activated_at'), F('created_at')),
    ).order_by('-latest_enrollment_at', '-id')


def _resolve_admission_level(school: School, class_name: str):
    """Find the Level that owns `class_name` in this school.

    The level segment of an admission number must come from the class's real
    Level FK, never from parsing the class name (spec §21). If the class has
    not been configured yet we fall back to the canonical levels so a first
    registration still works.
    """
    school_class = SchoolClass.objects.filter(
        school_id=school.id, name=class_name,
    ).select_related('level').first()
    if school_class is not None and school_class.level_id:
        return school_class.level
    levels = academic_service.ensure_levels(school)
    return levels.get(academic_service.guess_level_code(class_name) or '') or next(
        iter(levels.values()),
    )


def _admission_year(school: School) -> int:
    """The admission year: the current session's start year (spec §22).

    Never the calendar year - a session that opened in January must keep
    producing last year's admission numbers.
    """
    session = academic_service.current_session(school)
    if session is not None:
        return session.start_year
    return timezone.now().year


def _issue_admission_number(school: School, class_name: str) -> str:
    """Mint the next admission number for a new student.

    Uses the locked `AdmissionSequence` row rather than `max() + 1`, so two
    simultaneous registrations cannot collide.
    """
    code = academic_service.ensure_school_code(school)
    if not code:
        raise ValidationError({
            'admissionNumber': (
                'This school has no code yet, so admission numbers cannot be '
                'issued. Ask an administrator to set one in school settings.'
            ),
        })
    level = _resolve_admission_level(school, class_name)
    return admission_service.generate_admission_number(school, level, _admission_year(school))


class StudentPromotionView(APIView):
    """Carry a student into the next session at the top of their class.

    Promotion writes a *new* enrollment in the destination session and closes
    the source one as COMPLETED. The historical row is never overwritten, so a
    transcript can always show where the student was and when::

        2025/2026  JSS 1A  COMPLETED
        2026/2027  JSS 2A  ACTIVE
    """

    permission_classes = [IsAuthenticated, HasSchool, require_permissions('enrollment.manage')]

    def post(self, request, pk):
        school = request.user.school
        student = get_object_or_404(Student, id=pk, school_id=school.id)

        to_session = get_object_or_404(
            AcademicSession.objects.filter(school_id=school.id),
            id=request.data.get('toSessionId'),
        )
        to_class = get_object_or_404(
            SchoolClass.objects.filter(school_id=school.id),
            id=request.data.get('toClassId'),
        )
        to_section = None
        if request.data.get('toSectionId'):
            to_section = get_object_or_404(
                Section.objects.filter(school_id=school.id, class_obj=to_class),
                id=request.data.get('toSectionId'),
            )

        from_session = None
        if request.data.get('fromSessionId'):
            from_session = get_object_or_404(
                AcademicSession.objects.filter(school_id=school.id),
                id=request.data.get('fromSessionId'),
            )
        else:
            from_session = academic_service.current_session(school)

        with transaction.atomic():
            promoted = enrollment_service.promote_student(
                student,
                from_session=from_session,
                to_session=to_session,
                class_obj=to_class,
                section=to_section,
                actor=request.user,
            )
            log_audit(
                request, 'student.promoted', target='Student',
                detail=f'{from_session.name} {student.class_name} -> {to_session.name} {to_class.name}',
                entity='student', entity_id=str(student.pk),
                after={'session': to_session.name, 'class': to_class.name},
            )

        return Response({
            'studentId': str(student.pk),
            'enrollmentId': str(promoted.pk),
            'session': to_session.name,
            'className': to_class.name,
            'sectionName': to_section.name if to_section else '',
        })


class StudentListCreateView(APIView):
    """List the caller's school students, or create one.

    Read requires `students.read`; write requires `students.register`. The
    school is always derived from `request.user` — a client-supplied
    `schoolId`/`school` is ignored, never honoured (spec §6, §39).
    """

    permission_classes = [IsAuthenticated, HasSchool]

    def get_permissions(self):
        if self.request.method == 'POST':
            return [IsAuthenticated(), HasSchool(), CanCreateStudent()]
        return [IsAuthenticated(), HasSchool(), require_permissions('students.read')()]

    def get(self, request):
        search = request.query_params.get('search', '').strip()
        class_name = request.query_params.get('className', '').strip()
        class_id = request.query_params.get('class_id') or request.query_params.get('classId')
        student_status = request.query_params.get('status', '').strip()
        section = request.query_params.get('section', '').strip()
        session_id = (
            request.query_params.get('sessionId')
            or request.query_params.get('session_id')
            or ''
        ).strip()
        enrollment_status = request.query_params.get('enrollmentStatus', '').strip()
        data = _paginate(
            _filtered_students(request, search=search, class_name=class_name,
                               class_id=class_id, student_status=student_status,
                               section=section, session_id=session_id,
                               enrollment_status=enrollment_status),
            request, StudentSerializer, context={'request': request},
        )
        return Response(data)

    def post(self, request):
        school = request.user.school
        supplied = (request.data.get('admissionNumber') or '').strip()

        with transaction.atomic():
            # The school comes from the session, never the request body, so a
            # crafted `schoolId` cannot create a student in another tenant.
            if supplied:
                serializer = StudentSerializer(
                    data=request.data, context={'request': request},
                )
                serializer.is_valid(raise_exception=True)
                extra = {'school': school, 'status': Student.Status.PENDING_PAYMENT}
            else:
                # Default path: the server issues the number.
                number = _issue_admission_number(school, request.data.get('className', ''))
                serializer = StudentSerializer(
                    data={**request.data, 'admissionNumber': number},
                    context={'request': request},
                )
                serializer.is_valid(raise_exception=True)
                extra = {
                    'school': school,
                    'status': Student.Status.PENDING_PAYMENT,
                    'admission_number': number,
                    'admission_number_source': (
                        Student.AdmissionNumberSource.SYSTEM_GENERATED
                    ),
                    'admission_year': _admission_year(school),
                }
            try:
                student = serializer.save(**extra)
            except IntegrityError:
                # A concurrent request took this number between validation and
                # insert. Report it as a normal field error, not a 500.
                raise ValidationError({
                    'admissionNumber': 'That admission number has just been taken. Please try again.',
                })

            # Registration is billed separately from recurring school fees.
            invoice = billing_service.create_invoice_from_school_fees(
                school=school, student=student,
                due_date=billing_service.default_due_date(None, days=ADMISSION_INVOICE_DUE_DAYS),
            )
            # The registration row is what the payment flow approves later. Without
            # it a settled registration invoice would flip the status but never
            # seat the student in a class roster.
            billing_service.ensure_registration(
                school, student, invoice, created_by=request.user,
            )
            if invoice is None:
                student.status = Student.Status.ACTIVE
                student.save(update_fields=['status'])
                billing_service.activate_registration(student, actor=request.user)
        data = dict(serializer.data)
        data['invoiceId'] = str(invoice.id) if invoice else ''
        data['invoiceTotal'] = str(invoice.total) if invoice else ''
        data['registrationFeeConfigured'] = invoice is not None
        log_audit(
            request, 'student.register', target='Student',
            detail=f'{student.first_name} {student.last_name} ({student.admission_number}) - {student.class_name}',
            entity='student', entity_id=str(student.pk),
            after={
                'class': student.class_name,
                'status': student.status,
                'invoiceId': str(invoice.id) if invoice else '',
            },
        )
        if invoice is not None:
            log_audit(
                request, 'invoice.created', target='Invoice',
                detail=f'Registration invoice for {student.admission_number}',
                entity='invoice', entity_id=str(invoice.pk),
                after={'total': str(invoice.total), 'source': invoice.source},
            )
        return Response(data, status=status.HTTP_201_CREATED)


def _average_attendance(school_id, *, days: int = 30):
    """Mean attendance rate over the last `days` of marked registers.

    Computed in the database so a school with years of history does not load
    every record to produce one number. A school that has taken no register yet
    reports ``None`` rather than a flattering 100%, so the UI can show an empty
    state instead of inventing a figure.
    """
    since = timezone.now().date() - timedelta(days=days)
    counts = AttendanceRecord.objects.filter(
        school_id=school_id, date__gte=since,
    ).aggregate(
        present=Count('pk', filter=Q(
            status__in=[AttendanceRecord.Status.PRESENT, AttendanceRecord.Status.LATE],
        )),
        total=Count('pk'),
    )
    if not counts['total']:
        return None
    return round(counts['present'] * 100 / counts['total'], 1)


class StudentStatsView(APIView):
    permission_classes = [IsAuthenticated, HasSchool, require_permissions('students.read')]

    def get(self, request):
        school_id = request.user.school_id
        qs = Student.objects.filter(school_id=school_id)
        total = qs.count()
        active = qs.filter(status=Student.Status.ACTIVE).count()
        suspended = qs.filter(status=Student.Status.SUSPENDED).count()
        # Aggregate in the database rather than loading every invoice row into
        # Python (spec §72).
        outstanding = Invoice.objects.filter(
            school_id=school_id,
        ).aggregate(net=Sum('total') - Sum('paid'))['net'] or Decimal('0')
        return Response({
            'total': total,
            'active': active,
            'pendingPayment': qs.filter(status=Student.Status.PENDING_PAYMENT).count(),
            'suspended': suspended,
            'averageAttendance': _average_attendance(school_id),
            'outstandingFees': float(outstanding),
        })


class StudentDetailView(APIView):
    """Read/update a single student, always inside the caller's own school.

    `get_object` scopes the lookup by `request.user.school_id`, so a student
    belonging to another school is simply not found (404) — the endpoint never
    confirms that the ID exists elsewhere.
    """

    permission_classes = [IsAuthenticated, HasSchool]

    def get_permissions(self):
        if self.request.method in ('PATCH', 'PUT'):
            return [IsAuthenticated(), HasSchool(), CanWriteStudent()]
        return [IsAuthenticated(), HasSchool(), require_permissions('students.read')()]

    def get_object(self, request, pk):
        return get_object_or_404(_student_queryset(request.user.school_id), id=pk)

    def get(self, request, pk):
        student = self.get_object(request, pk)
        return Response(StudentSerializer(student, context={'request': request}).data)

    def patch(self, request, pk):
        student = self.get_object(request, pk)
        before_status = student.status
        requested = str(request.data.get('status') or '').strip()
        if requested and requested != before_status:
            self._assert_status_change_allowed(student, requested)
        serializer = StudentSerializer(
            student, data=request.data, partial=True, context={'request': request},
        )
        serializer.is_valid(raise_exception=True)
        # Ownership cannot move: `school` is not a serializer field, and passing
        # it explicitly is rejected here so a crafted payload fails loudly
        # instead of being silently dropped.
        updated = serializer.save()
        if updated.status != before_status:
            log_audit(
                request, 'student.updated', target='Student',
                detail=f'{updated.first_name} {updated.last_name} ({updated.admission_number})',
                entity='student', entity_id=str(updated.pk),
                before={'status': before_status},
                after={'status': updated.status},
            )
        return Response(serializer.data)

    def _assert_status_change_allowed(self, student, requested):
        """A client may suspend/restore, but never drive the state machine.

        The billing hold is raised by registration and cleared only by a
        verified registration payment (or by the school having no registration
        fee at all); a transfer and a graduation each have their own endpoint
        that moves the student and writes the audit trail. Letting a PATCH set
        any of these directly would let a student be activated without paying.
        """
        if requested not in Student.Status.values:
            return
        if requested in (
            Student.Status.PENDING_PAYMENT,
            Student.Status.TRANSFERRED,
            Student.Status.GRADUATED,
        ):
            raise ValidationError({
                'status': f'A student cannot be moved to "{requested}" from here. '
                          'That state is set by the school\'s own workflow.',
            })
        if student.status == Student.Status.PENDING_PAYMENT:
            raise ValidationError({
                'status': 'This student is waiting for the registration payment. '
                          'Verify the payment to activate them.',
            })


class StudentTransferView(APIView):
    """Move a student, validating every referenced object against the caller's school.

    Two distinct moves share this endpoint, because both appear as "transfer"
    in the product:

    * **Out of the school** (`toSchoolId`) — the student leaves for another
      school entirely. The destination is by definition a *different* school,
      so the rule here is that it must exist, be active, and not be the
      caller's own school.
    * **Within the school** (`toClassId` / `toSectionId` / `sessionId`) — the
      student changes class or section. Every one of these objects is looked up
      *scoped to the caller's school*, so a School B class or section can never
      be reached from a School A session (they 404).
    """

    permission_classes = [IsAuthenticated, HasSchool, CanWriteStudent]

    def post(self, request, pk):
        # Source: scoped to the caller's school, so "School A user → School B
        # student" is a 404, not a transfer.
        student = get_object_or_404(Student, id=pk, school_id=request.user.school_id)

        if student.status == Student.Status.TRANSFERRED:
            raise ValidationError({
                'student': 'This student has already been transferred out of the school.',
            })

        to_school_id = request.data.get('toSchoolId')
        to_class_id = request.data.get('toClassId')
        to_section_id = request.data.get('toSectionId')
        session_id = request.data.get('sessionId')

        if to_class_id or to_section_id:
            return self._transfer_within_school(
                request, student, to_class_id, to_section_id, session_id,
            )
        return self._transfer_to_school(request, student, to_school_id)

    def _transfer_to_school(self, request, student, to_school_id):
        if not to_school_id:
            raise ValidationError({
                'toSchoolId': 'A destination school or a destination class is required.',
            })
        # The destination is a *different* school by design, so ownership is not
        # the test here — validity is: it must exist, be active, and not be the
        # school the student is already leaving.
        target = get_object_or_404(
            School.objects.filter(is_active=True), id=to_school_id,
        )
        if target.id == request.user.school_id:
            raise ValidationError({
                'toSchoolId': 'The destination must be a different school.',
            })
        if target.id == student.school_id:
            raise ValidationError({
                'toSchoolId': 'The student already belongs to that school.',
            })
        student.transferred_to = target
        student.transferred_at = timezone.now()
        student.status = Student.Status.TRANSFERRED
        student.save(update_fields=['transferred_to', 'transferred_at', 'status'])
        return Response(StudentSerializer(student, context={'request': request}).data)

    def _transfer_within_school(
        self, request, student, to_class_id, to_section_id, session_id,
    ):
        """Move a student to another class/section in the caller's own school.

        Every lookup is filtered by `request.user.school_id`, so another
        school's class or section is indistinguishable from one that does not
        exist. This is the "School A user → School B class/section" rejection.
        """
        school_id = request.user.school_id
        if to_class_id:
            target_class = get_object_or_404(
                SchoolClass.objects.filter(school_id=school_id), id=to_class_id,
            )
        else:
            # No class given: fall back to the student's current class so only
            # the section changes.
            target_class = get_object_or_404(
                SchoolClass.objects.filter(
                    school_id=school_id, name=student.class_name,
                ),
            )

        if to_section_id:
            target_section = get_object_or_404(
                Section.objects.filter(school_id=school_id, class_obj=target_class),
                id=to_section_id,
            )
        else:
            target_section = None

        if session_id:
            session = get_object_or_404(
                AcademicSession.objects.filter(school_id=school_id), id=session_id,
            )
        else:
            session = academic_service.current_session(request.user.school)

        with transaction.atomic():
            previous, enrollment = enrollment_service.transfer_active_enrollment(
                student,
                session,
                target_class,
                target_section,
                actor=request.user,
            )
            student.status = Student.Status.ACTIVE
            student.save(update_fields=['status'])
            log_audit(
                request, 'student.transferred', target='Student',
                detail=f'{previous.class_obj.name if previous else student.class_name} -> {target_class.name}',
                entity='student', entity_id=str(student.pk),
                before={
                    'class': previous.class_obj.name if previous else student.class_name,
                    'section': previous.section.name if previous and previous.section_id else '',
                } if previous else {},
                after={
                    'class': target_class.name,
                    'section': target_section.name if target_section else '',
                },
            )

        payload = StudentSerializer(student, context={'request': request}).data
        payload['previousClass'] = previous.class_obj.name if previous else ''
        return Response(payload)


class StudentImportAnalysisView(APIView):
    permission_classes = [IsAuthenticated, HasSchool, CanImportStudents]
    parser_classes = [MultiPartParser]

    def post(self, request):
        try:
            parsed = parse_import_file(request.FILES.get('file'))
        except StudentImportError as exc:
            raise ValidationError({'file': str(exc)})
        analysis = analyse_import(parsed, request.user.school_id)
        return Response(analysis.as_dict())


class StudentImportView(APIView):
    permission_classes = [IsAuthenticated, HasSchool, CanImportStudents]
    parser_classes = [MultiPartParser]

    def post(self, request):
        try:
            parsed = parse_import_file(request.FILES.get('file'))
        except StudentImportError as exc:
            raise ValidationError({'file': str(exc)})

        try:
            with transaction.atomic():
                School.objects.select_for_update().get(pk=request.user.school_id)
                analysis = analyse_import(
                    parsed,
                    request.user.school_id,
                    lock_existing=True,
                )
                if analysis.capacity['exceeds']:
                    raise ValidationError({
                        'capacity': 'This import would exceed the school student limit.',
                    })
                if not analysis.valid_rows:
                    raise ValidationError({
                        'file': 'The CSV file does not contain any valid student rows.',
                    })
                students = [
                    Student(
                        school_id=request.user.school_id,
                        admission_number=row.admission_number,
                        first_name=row.first_name,
                        last_name=row.last_name,
                        gender=row.gender,
                        date_of_birth=row.date_of_birth,
                        class_name=row.class_name,
                        arm=row.arm,
                        guardian_name=row.guardian_name,
                        guardian_phone=row.guardian_phone,
                        status=Student.Status.ACTIVE,
                    )
                    for row in analysis.valid_rows
                ]
                Student.objects.bulk_create(students)
        except IntegrityError as exc:
            raise ValidationError({
                'file': 'An admission number was imported by another user. Please re-run the import.',
            }) from exc

        return Response({
            'imported': len(students),
            'skipped': analysis.rejected,
            'invalid': analysis.invalid,
            'duplicates': analysis.duplicate_count,
        })


# ── Staff ──────────────────────────────────────────────────────────────────

class StaffListView(APIView):
    permission_classes = [IsAuthenticated, HasSchool]

    def get(self, request):
        qs = StaffMember.objects.filter(school_id=request.user.school_id)
        return Response(StaffMemberSerializer(qs, many=True).data)

    def post(self, request):
        if not CanWriteStaff().has_permission(request, self):
            raise PermissionDenied('You do not have permission to manage staff.')
        serializer = StaffMemberSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save(school_id=request.user.school_id, status=StaffMember.Status.ACTIVE)
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class StaffDetailView(APIView):
    permission_classes = [IsAuthenticated, HasSchool]

    def get_object(self, request, pk):
        return get_object_or_404(StaffMember, id=pk, school_id=request.user.school_id)

    def get(self, request, pk):
        return Response(StaffMemberSerializer(self.get_object(request, pk)).data)

    def patch(self, request, pk):
        if not CanWriteStaff().has_permission(request, self):
            raise PermissionDenied('You do not have permission to manage staff.')
        member = self.get_object(request, pk)
        serializer = StaffMemberSerializer(member, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)

    def delete(self, request, pk):
        if not CanWriteStaff().has_permission(request, self):
            raise PermissionDenied('You do not have permission to manage staff.')
        member = self.get_object(request, pk)
        member.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class ClassTeacherAssignmentView(APIView):
    """Designate the teacher responsible for each class's register.

    The attendance rule is "only the designated class teacher submits", so this is
    what makes that rule usable: without it, no teacher can ever submit. Reads are
    open to anyone who can read attendance (the register screen needs to name the
    class teacher); writes need `staff.write`, because designating who is
    responsible for a class is staff administration.
    """

    permission_classes = [IsAuthenticated, HasSchool]

    def get(self, request):
        school = request.user.school
        session = academic_service.current_session(school)
        rows = ClassTeacherAssignment.objects.filter(school=school)
        if session is not None:
            rows = rows.filter(academic_session=session)
        return Response({
            'session': session.name if session else '',
            'assignments': [
                {
                    'className': row.class_obj.name,
                    'classId': row.class_obj_id,
                    'staffId': row.staff_id,
                    'staffName': row.staff.full_name,
                    'session': row.academic_session.name,
                }
                for row in rows.select_related('class_obj', 'staff', 'academic_session')
                .order_by('class_obj__sort_order', 'class_obj__name')
            ],
        })

    def post(self, request):
        if not CanWriteStaff().has_permission(request, self):
            raise PermissionDenied('You do not have permission to manage staff.')

        school = request.user.school
        class_obj = attendance_service.resolve_class(
            school, (request.data.get('className') or '').strip(),
        )
        if class_obj is None:
            raise ValidationError({
                'className': 'That class does not exist in this school.',
            })

        assign = bool(request.data.get('assign', True))
        if not assign:
            attendance_service.assign_class_teacher(
                school, class_obj=class_obj, assign=False,
            )
            return Response({'className': class_obj.name, 'classTeacher': ''})

        staff_id = (request.data.get('staffId') or '').strip()
        staff = get_object_or_404(
            StaffMember, id=staff_id, school_id=school.id,
        ) if staff_id else None
        if staff is None:
            raise ValidationError({'staffId': 'Choose the teacher responsible for this class.'})
        if staff.role != 'teacher':
            raise ValidationError({
                'staffId': f'{staff.full_name} is not a teacher.',
            })

        assignment = attendance_service.assign_class_teacher(
            school, class_obj=class_obj, staff=staff,
        )
        return Response({
            'className': class_obj.name,
            'classId': class_obj.id,
            'staffId': assignment.staff_id,
            'staffName': assignment.staff.full_name,
        })


class StaffInviteView(APIView):
    permission_classes = [IsAuthenticated, HasSchool, CanWriteRecords]

    def post(self, request, pk):
        member = get_object_or_404(StaffMember, id=pk, school_id=request.user.school_id)
        if member.status == StaffMember.Status.INVITED:
            return Response(StaffMemberSerializer(member).data)
        member.status = StaffMember.Status.INVITED
        member.save(update_fields=['status'])
        return Response(StaffMemberSerializer(member).data)


# ── Finance ────────────────────────────────────────────────────────────────

class InvoiceListView(APIView):
    permission_classes = [IsAuthenticated, HasSchool, CanReadFinance]

    def get(self, request):
        qs = Invoice.objects.filter(
            school_id=request.user.school_id,
        ).select_related('student').order_by('-created_at', '-id')
        if request.user.role != 'student':
            search = request.query_params.get('search', '').strip()
            if search:
                qs = qs.filter(
                    student__first_name__icontains=search,
                ) | qs.filter(student__last_name__icontains=search) | qs.filter(
                    student__admission_number__icontains=search,
                )
            student_id = request.query_params.get('studentId', '').strip()
            if student_id:
                qs = qs.filter(student_id=student_id)
        else:
            # Self-service: a student sees only their own invoices.
            qs = qs.filter(student_id=request.user.student_profile_id)
        qs = qs.annotate(
            verified_paid_total=Coalesce(
                Sum(
                    'payments__amount',
                    filter=Q(payments__status=Payment.Status.VERIFIED),
                ),
                Decimal('0'),
            ),
        )
        return Response(_paginate(qs, request, InvoiceSerializer, context={'request': request}))


class InvoiceGenerateView(APIView):
    permission_classes = [IsAuthenticated, HasSchool, CanWriteFinance]

    def post(self, request):
        class_name = (request.data.get('className') or '').strip()
        term = (request.data.get('term') or '').strip()
        overwrite = bool(request.data.get('overwrite'))
        errors = {}
        if not class_name:
            errors['className'] = 'Select a class to invoice.'
        if not term:
            errors['term'] = 'A term is required (e.g. First Term).'
        if errors:
            raise ValidationError(errors)

        school = get_object_or_404(School, id=request.user.school_id)
        # Regular term invoices exclude the one-time registration fee.
        items = billing_service.resolve_invoice_items(
            school=school,
            class_name=class_name,
            term=term,
            exclude_fee_types={FeeStructure.FeeType.REGISTRATION},
        )
        if not items:
            raise ValidationError({
                'className': f'No fee items are set up for {class_name}. Add a fee structure first.',
            })
        total = sum(
            (invoice_item_amount(item) for item in items), Decimal('0'),
        )
        students = Student.objects.filter(
            school_id=school.id, class_name=class_name, status=Student.Status.ACTIVE,
        )
        generated = updated = 0
        with transaction.atomic():
            for student in students.select_for_update():
                # A cancelled invoice is history, not a live charge. Looking it
                # up here meant the overwrite branch below would rewrite a
                # cancelled invoice's amounts and leave it cancelled, so the
                # student was silently never re-billed.
                invoice = Invoice.objects.filter(
                    school_id=school.id, student_id=student.id, term=term,
                    is_cancelled=False,
                ).first()
                if invoice:
                    if overwrite and total >= invoice.paid:
                        invoice.items = items
                        invoice.total = total
                        invoice.save(update_fields=['items', 'total'])
                        updated += 1
                    continue
                Invoice.objects.create(
                    school_id=school.id,
                    student_id=student.id,
                    term=term,
                    total=total,
                    paid=0,
                    items=items,
                )
                generated += 1
        return Response({
            'generated': generated,
            'updated': updated,
            'totalStudents': students.count(),
            'term': term,
        })


# Human names for the fee vocabulary, used to make validation messages legible.
FEE_TYPE_DISPLAY = {value: label for value, label in FeeStructure.FeeType.choices}


class FeeStructureView(APIView):
    """Read and write the school's Payment Structure.

    Two shapes, because the product grew in two steps:

    * `levels` (preferred) — the per-level Payment Structure from school
      settings. Each entry carries its own fee lines, including a registration
      fee, so a Primary student and a Senior Secondary student are priced
      independently. This is written to the relational `FeeStructure` table.
    * `items` (legacy) — the older flat school-wide list still on
      `School.fee_structure`. Kept working so schools that have not opened the
      new editor are unaffected.

    Reads always return both, and invoicing prefers `levels` and falls back to
    `items` (see `billing.resolve_invoice_items`).
    """

    def get_permissions(self):
        # `finance.structure` is the capability being exercised, not a role
        # name. `principal` deliberately does not hold it, so a principal can
        # read the structure but not reprice the school.
        if self.request.method in ('PUT', 'PATCH', 'POST'):
            return [IsAuthenticated(), HasSchool(), CanWriteFeeStructure()]
        return [IsAuthenticated(), HasSchool(), require_permissions('finance.read')()]

    def _school(self, request):
        return get_object_or_404(School, id=request.user.school_id)

    def _session(self, school):
        return academic_service.current_session(school)

    def _levels_payload(self, school):
        """Per-level fee lines for the current session, in catalogue order."""
        session = self._session(school)
        if session is None:
            return []
        # Only LEVEL-scope rows belong to the per-level editor. A CLASS- or
        # SCHOOL-scope row that merely carries a `level` (migration 0006 writes
        # class-scoped rows for legacy per-class fees) would otherwise be shown
        # here, and the next save would deactivate it while writing a duplicate.
        rows = (
            FeeStructure.objects
            .filter(
                school=school,
                academic_session=session,
                is_active=True,
                scope=FeeStructure.Scope.LEVEL,
            )
            .select_related('level')
        )
        by_level: dict[str | None, list[dict]] = {}
        for row in rows:
            if row.level_id is None:
                continue
            by_level.setdefault(row.level.code, []).append({
                'id': row.id,
                'feeType': row.fee_type,
                'label': row.label,
                'amount': float(row.amount),
                'term': row.term,
                'isRequired': row.is_required,
                'scope': row.scope,
            })
        levels = []
        for level in school.levels.filter(is_active=True).order_by('sort_order', 'name'):
            levels.append({
                'id': level.id,
                'code': level.code,
                'name': level.name,
                'fees': sorted(
                    by_level.get(level.code, []),
                    key=lambda f: (f['feeType'] != FeeStructure.FeeType.REGISTRATION, f['label']),
                ),
            })
        return levels

    def get(self, request):
        school = self._school(request)
        return Response({
            'items': school.fee_structure or [],
            'levels': self._levels_payload(school),
        })

    def _write_level_fees(self, school, session, level, fees, actor):
        """Replace one level's fee lines.

        Rows are matched on the same key the conflict constraint uses, so saving
        a level twice updates in place rather than raising IntegrityError. Fees
        the editor removed are deactivated rather than deleted: an invoice that
        already snapshotted them must keep resolving to the same figure.
        """
        if not isinstance(fees, list):
            raise ValidationError({'fees': 'Each level needs a list of fees.'})

        # The conflict constraint allows one row per fee type per scope, so a
        # payload with two "other" lines would fail on the second write with an
        # IntegrityError the client cannot interpret. Reject it up front with a
        # message naming the duplicate instead.
        seen: set[tuple[str, str]] = set()
        for index, fee in enumerate(fees):
            if not isinstance(fee, dict):
                raise ValidationError({'fees': f'Fee {index + 1} is not a valid fee line.'})
            key = (
                str(fee.get('feeType') or '').strip() or FeeStructure.FeeType.OTHER,
                str(fee.get('term') or '').strip(),
            )
            if key in seen:
                label = str(fee.get('label') or '').strip() or FEE_TYPE_DISPLAY.get(key[0], key[0])
                raise ValidationError({
                    'fees': (
                        f'"{label}" repeats the {FEE_TYPE_DISPLAY.get(key[0], key[0])} fee. '
                        'Each fee type can be set once per term - merge them into a single fee.'
                    ),
                })
            seen.add(key)

        kept = []
        for fee in fees:
            label = str(fee.get('label') or '').strip()
            fee_type = str(fee.get('feeType') or '').strip() or FeeStructure.FeeType.OTHER
            if fee_type not in FeeStructure.FeeType.values:
                raise ValidationError({'fees': f'"{fee_type}" is not a valid fee type.'})
            try:
                amount = Decimal(str(fee.get('amount')))
            except (TypeError, ValueError, InvalidOperation):
                raise ValidationError({'fees': f'"{label}" has an invalid amount.'})
            if not label:
                raise ValidationError({'fees': 'Every fee needs a label.'})
            if amount <= 0:
                raise ValidationError({'fees': f'Amount for "{label}" must be greater than zero.'})
            term = str(fee.get('term') or '').strip()
            row, _created = FeeStructure.objects.update_or_create(
                school=school,
                academic_session=session,
                term=term,
                scope=FeeStructure.Scope.LEVEL,
                scope_key=str(level.id),
                fee_type=fee_type,
                effective_from=EPOCH,
                defaults={
                    'level': level,
                    'label': label,
                    'amount': amount,
                    'is_required': bool(fee.get('isRequired', True)),
                    'is_active': True,
                    'created_by': actor,
                },
            )
            kept.append(row.id)

        FeeStructure.objects.filter(
            school=school, academic_session=session,
            scope=FeeStructure.Scope.LEVEL, scope_key=str(level.id),
        ).exclude(id__in=kept).update(is_active=False)
        return kept

    def put(self, request):
        school = self._school(request)
        session = self._session(school)
        if session is None:
            raise ValidationError({
                'levels': 'Set the school academic session before configuring fees.',
            })

        # ── per-level Payment Structure ──
        if 'levels' in request.data:
            levels = request.data.get('levels')
            if not isinstance(levels, list):
                raise ValidationError({'levels': 'Levels must be a list.'})
            school_levels = {
                level.id: level for level in school.levels.filter(is_active=True)
            }
            touched = []
            with transaction.atomic():
                for entry in levels:
                    level_id = entry.get('levelId')
                    level = school_levels.get(level_id)
                    if level is None:
                        raise ValidationError({
                            'levels': f'Level {level_id} does not belong to this school.',
                        })
                    self._write_level_fees(
                        school, session, level, entry.get('fees') or [], request.user,
                    )
                    touched.append(level)

            # Resolve pending registrations only against the levels just priced.
            # A configured registration charge is invoiced once; without one,
            # pending legacy registrations are activated for later term billing.
            invoiced = 0
            per_level = {}
            activated = 0
            activated_per_level = {}
            for level in touched:
                created, cleared = billing_service.invoice_pending_students(
                    school, level=level,
                )
                per_level[str(level.code)] = created
                activated_per_level[str(level.code)] = cleared
                invoiced += created
                activated += cleared

            return Response({
                'levels': self._levels_payload(school),
                'items': school.fee_structure or [],
                'invoicedPendingStudents': invoiced,
                'invoicedPendingStudentsByLevel': per_level,
                'activatedPendingStudents': activated,
                'activatedPendingStudentsByLevel': activated_per_level,
            })

        # ── legacy school-wide list ──
        items = request.data.get('items', [])
        if not isinstance(items, list):
            raise ValidationError({'items': 'Fee structure must be a list of items.'})
        normalized = []
        for item in items:
            label = str(item.get('label') or '').strip()
            class_name = str(item.get('className') or '*').strip() or '*'
            try:
                amount = Decimal(item.get('amount'))
            except (TypeError, ValueError, InvalidOperation):
                raise ValidationError({'items': f'"{label}" has an invalid amount.'})
            if not label:
                raise ValidationError({'items': 'Every fee item needs a label.'})
            if amount <= 0:
                raise ValidationError({'items': f'Amount for "{label}" must be greater than zero.'})
            normalized.append({'label': label, 'amount': float(amount), 'className': class_name})
        school.fee_structure = normalized
        school.save(update_fields=['fee_structure'])
        invoiced, activated = billing_service.invoice_pending_students(school)
        return Response({
            'items': school.fee_structure,
            'levels': self._levels_payload(school),
            'invoicedPendingStudents': invoiced,
            'activatedPendingStudents': activated,
        })


class PaymentListView(APIView):
    permission_classes = [IsAuthenticated, HasSchool, CanReadFinance]

    def get(self, request):
        qs = Payment.objects.filter(
            school_id=request.user.school_id,
        ).select_related('invoice__student', 'recorded_by').order_by('-created_at', '-id')
        if request.user.role == 'student':
            qs = qs.filter(invoice__student_id=request.user.student_profile_id)
        else:
            invoice_id = request.query_params.get('invoiceId', '').strip()
            student_id = request.query_params.get('studentId', '').strip()
            if invoice_id:
                qs = qs.filter(invoice_id=invoice_id)
            if student_id:
                qs = qs.filter(invoice__student_id=student_id)
        return Response(_paginate(qs, request, PaymentSerializer, context={'request': request}))

    def post(self, request):
        is_finance = request.user.role in FINANCE_WRITE_ROLES
        is_self_service = request.user.role == 'student' and request.user.student_profile_id is not None
        if not is_finance and not is_self_service:
            raise PermissionDenied('You do not have permission to record fee payments.')
        method = (request.data.get('method') or Payment.Method.CASH).strip()
        if method not in Payment.Method.values:
            raise ValidationError({'method': 'Invalid payment method.'})
        invoice = get_object_or_404(
            Invoice, id=request.data.get('invoiceId'), school_id=request.user.school_id,
        )
        if is_self_service:
            if invoice.student_id != request.user.student_profile_id:
                raise PermissionDenied('You can only pay your own invoices.')
            if method not in SELF_SERVICE_METHODS:
                raise ValidationError({
                    'method': 'Self-service payments must use card, bank transfer, online or USSD. '
                              'Cash and POS are recorded by the school bursar.',
                })
        try:
            amount = Decimal(request.data.get('amount'))
        except (TypeError, ValueError, InvalidOperation):
            raise ValidationError({'amount': 'Enter a valid amount.'})
        if amount <= 0:
            raise ValidationError({'amount': 'Amount must be greater than zero.'})
        reference = (request.data.get('reference') or '').strip()
        if reference and Payment.objects.filter(reference=reference).exists():
            raise ValidationError({'reference': 'A payment with this reference already exists.'})

        verified = is_finance and method in (Payment.Method.CASH, Payment.Method.POS)
        with transaction.atomic():
            invoice = Invoice.objects.select_for_update().get(pk=invoice.pk)
            outstanding = invoice.total - invoice.paid
            if amount > outstanding:
                raise ValidationError({
                    'amount': f'Amount exceeds the outstanding balance of {outstanding:.2f}.',
                })
            payment = Payment.objects.create(
                school_id=request.user.school_id,
                invoice_id=invoice.id,
                amount=amount,
                method=method,
                status=Payment.Status.VERIFIED if verified else Payment.Status.PENDING,
                reference=reference or f'FN-{uuid.uuid4().hex[:10].upper()}',
                note=request.data.get('note', ''),
                recorded_by=request.user if request.user.school_id else None,
            )
            if verified:
                invoice.paid += amount
                invoice.save(update_fields=['paid'])
            # Cash and POS are verified on the spot, so a family paying the
            # admission fee at the bursar's desk is fully settled right here.
            # Without this the student would sit in PENDING_PAYMENT until some
            # later verification endpoint happened to run.
            activated = billing_service.activate_student_if_fully_paid(
                invoice.student, actor=request.user,
            )
            log_audit(
                request, 'payment.created', target='Payment',
                detail=f'{payment.get_method_display()} {amount} from {invoice.student.admission_number}',
                entity='payment', entity_id=str(payment.pk),
                after={'amount': str(amount), 'status': payment.status},
            )
            if verified:
                log_audit(
                    request, 'payment.verified', target='Payment',
                    detail=f'Cash/POS payment verified for {invoice.student.admission_number}',
                    entity='payment', entity_id=str(payment.pk),
                    after={'amount': str(amount), 'invoiceId': str(invoice.pk)},
                )
            if activated:
                log_audit(
                    request, 'enrollment.activated', target='Student',
                    detail=f'{invoice.student.admission_number} seated after registration payment',
                    entity='student', entity_id=str(invoice.student_id),
                )
        return Response(
            {**PaymentSerializer(payment).data, 'studentActivated': activated},
            status=status.HTTP_201_CREATED,
        )


class FinanceSummaryView(APIView):
    permission_classes = [IsAuthenticated, HasSchool, CanReadFinance]

    def get(self, request):
        school = request.user.school
        invoices = Invoice.objects.filter(
            school_id=request.user.school_id,
        ).filter(
            Q(term=school.current_term)
            | Q(source=Invoice.Source.ADMISSION, term=''),
        ).select_related('student')
        payments = Payment.objects.filter(school_id=request.user.school_id)
        if request.user.role == 'student':
            student_id = request.user.student_profile_id
            invoices = invoices.filter(student_id=student_id)
            payments = payments.filter(invoice__student_id=student_id)

        invoice_totals = invoices.aggregate(total=Sum('total'), paid=Sum('paid'))
        today = timezone.localdate()
        payment_totals = payments.aggregate(
            collected_today=Sum(
                'amount',
                filter=Q(status=Payment.Status.VERIFIED, created_at__date=today),
            ),
            pending_count=Count('id', filter=Q(status=Payment.Status.PENDING)),
            cash_today=Sum(
                'amount',
                filter=Q(
                    status=Payment.Status.VERIFIED,
                    method=Payment.Method.CASH,
                    created_at__date=today,
                ),
            ),
        )
        recent_payments = payments.select_related(
            'invoice__student', 'recorded_by',
        ).order_by('-created_at', '-id')[:6]

        return Response({
            'term': school.current_term,
            'billed': float(invoice_totals['total'] or 0),
            'paid': float(invoice_totals['paid'] or 0),
            'outstanding': float(
                (invoice_totals['total'] or Decimal('0'))
                - (invoice_totals['paid'] or Decimal('0'))
            ),
            'collectedToday': float(payment_totals['collected_today'] or 0),
            'pendingPaymentCount': payment_totals['pending_count'],
            'cashToday': float(payment_totals['cash_today'] or 0),
            'recentInvoices': InvoiceSerializer(invoices.order_by('-id')[:3], many=True).data,
            'recentPayments': PaymentSerializer(
                recent_payments, many=True, context={'request': request},
            ).data,
        })


class PaymentVerifyView(APIView):
    permission_classes = [IsAuthenticated, HasSchool, CanWriteFinance]

    def post(self, request, pk):
        with transaction.atomic():
            payment = get_object_or_404(
                Payment.objects.select_for_update(), id=pk, school_id=request.user.school_id,
            )
            if payment.status in (Payment.Status.FAILED, Payment.Status.REFUNDED,
                                  Payment.Status.REVERSED, Payment.Status.CANCELLED):
                return Response(
                    {'detail': f'A {payment.status} payment cannot be verified.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            if payment.status == Payment.Status.VERIFIED:
                # Already verified: re-running is a no-op for the money, but the
                # student may still be held if the earlier run failed midway.
                activated = billing_service.activate_student_if_fully_paid(
                    payment.invoice.student, actor=request.user,
                )
                if activated:
                    log_audit(
                        request, 'enrollment.activated', target='Student',
                        detail=f'{payment.invoice.student.admission_number} seated after re-verification',
                        entity='student', entity_id=str(payment.invoice.student_id),
                    )
                return Response({**PaymentSerializer(payment).data, 'studentActivated': activated})
            invoice = Invoice.objects.select_for_update().get(pk=payment.invoice_id)
            outstanding = invoice.total - invoice.paid
            if payment.amount > outstanding:
                return Response(
                    {'detail': f'Amount exceeds the outstanding balance of {outstanding:.2f}.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            invoice.paid += payment.amount
            invoice.save(update_fields=['paid'])
            payment.status = Payment.Status.VERIFIED
            payment.save(update_fields=['status'])
            # Verifying the final instalment is what lets a new student start
            # classes. Only promotes PENDING_PAYMENT forward, so this can never
            # undo a suspension or a graduation.
            activated = billing_service.activate_student_if_fully_paid(
                invoice.student, actor=request.user,
            )
            event_service.payment_verified(payment)
            log_audit(
                request, 'payment.verified', target='Payment',
                detail=f'{payment.get_method_display()} {payment.amount} towards {invoice.student.admission_number}',
                entity='payment', entity_id=str(payment.pk),
                after={'amount': str(payment.amount), 'invoiceId': str(invoice.pk)},
            )
            if activated:
                log_audit(
                    request, 'enrollment.activated', target='Student',
                    detail=f'{invoice.student.admission_number} seated after registration payment',
                    entity='student', entity_id=str(invoice.student_id),
                )
        return Response({**PaymentSerializer(payment).data, 'studentActivated': activated})


class PaymentReverseView(APIView):
    permission_classes = [IsAuthenticated, HasSchool, CanWriteFinance]

    def post(self, request, pk):
        with transaction.atomic():
            payment = get_object_or_404(
                Payment.objects.select_for_update(), id=pk, school_id=request.user.school_id,
            )
            if payment.status != Payment.Status.VERIFIED:
                return Response(
                    {'detail': 'Only verified payments can be reversed.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            invoice = Invoice.objects.select_for_update().get(pk=payment.invoice_id)
            invoice.paid -= payment.amount
            invoice.paid = max(invoice.paid, 0)
            invoice.save(update_fields=['paid'])
            payment.status = Payment.Status.REVERSED
            payment.save(update_fields=['status'])
            event_service.payment_reversed(payment)
        return Response(PaymentSerializer(payment).data)


class PaymentCancelView(APIView):
    permission_classes = [IsAuthenticated, HasSchool, CanWriteFinance]

    def post(self, request, pk):
        with transaction.atomic():
            payment = get_object_or_404(
                Payment.objects.select_for_update(), id=pk, school_id=request.user.school_id,
            )
            if payment.status != Payment.Status.PENDING:
                return Response(
                    {'detail': 'Only pending payments can be cancelled.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            payment.status = Payment.Status.CANCELLED
            payment.save(update_fields=['status'])
        return Response(PaymentSerializer(payment).data)


# ── Subscription ───────────────────────────────────────────────────────────

class SubscriptionView(APIView):
    permission_classes = [IsAuthenticated, HasSchool]

    def get(self, request):
        school_id = request.user.school_id
        school = get_object_or_404(School, id=school_id)
        active_students = Student.objects.filter(school_id=school_id, status=Student.Status.ACTIVE).count()
        subscription = SchoolSubscription.objects.filter(school_id=school_id, status__in=['active', 'pending']).first()
        plan = subscription.plan if subscription and subscription.plan_id else None

        max_students = plan.max_students if plan else 100
        tier_id = plan.name if plan else 't100'
        growth = max((max_students - active_students) if max_students else 0, 0)

        return Response({
            'tierId': tier_id,
            'status': school.is_active and 'active' or 'pending_payment',
            'activeStudents': active_students,
            'growthAllowance': growth,
            'renewalDate': (subscription.expires_at.isoformat() if subscription and subscription.expires_at else ''),
            'aiCreditsUsed': 0,
            'aiCreditsTotal': plan.ai_credits if plan else 500,
            'storageUsedGb': 0,
            'paymentMethod': None,
        })


# ── Results ───────────────────────────────────────────────────────────────

class _ResultSheetListSerializer(serializers.Serializer):
    """Flat summary of a sheet for the paged results list."""

    def to_representation(self, instance):
        return {
            'id': str(instance.id),
            'session': instance.academic_session.name,
            'className': instance.class_obj.name,
            'subject': instance.subject,
            'assessment': instance.assessment,
            'assessmentMax': str(instance.assessment_max),
            'term': instance.term,
            'status': instance.status,
            'isLocked': instance.is_locked,
            'studentCount': instance.student_count,
            'correctionRequested': bool(instance.correction_requested_at),
        }


class _ResultEntryReportSerializer(serializers.Serializer):
    def to_representation(self, entry):
        return {
            'studentName': f'{entry.student.last_name}, {entry.student.first_name}',
            'className': entry.sheet.class_obj.name,
            'subject': entry.sheet.subject,
            'term': entry.sheet.term,
            'ca1': float(entry.ca1) if entry.ca1 is not None else None,
            'ca2': float(entry.ca2) if entry.ca2 is not None else None,
            'assignment': float(entry.assignment) if entry.assignment is not None else None,
            'exam': float(entry.exam) if entry.exam is not None else None,
            'score': float(entry.score) if entry.score is not None else None,
            'grade': entry.grade,
        }


class ResultEntryReportView(APIView):
    permission_classes = [IsAuthenticated, HasSchool, require_permissions('reports.read')]

    def get(self, request):
        school = request.user.school
        queryset = ResultEntry.objects.filter(
            sheet__school=school,
            sheet__status__in=[
                ResultSheet.Status.PUBLISHED,
                ResultSheet.Status.LOCKED,
            ],
        ).select_related(
            'student', 'sheet__class_obj',
        ).order_by(
            'sheet__class_obj__name',
            'sheet__subject',
            'student__last_name',
            'student__first_name',
        )
        session_id = request.query_params.get('sessionId')
        if session_id:
            session = get_object_or_404(
                AcademicSession.objects.filter(school=school), id=session_id,
            )
            queryset = queryset.filter(sheet__academic_session=session)
        return Response(_paginate(queryset, request, _ResultEntryReportSerializer))


class _MyPublishedResultSerializer(_ResultEntryReportSerializer):
    def to_representation(self, entry):
        return {
            **super().to_representation(entry),
            'studentId': str(entry.student_id),
            'session': entry.sheet.academic_session.name,
        }


class MyPublishedResultsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if request.user.role == 'parent':
            queryset = ResultEntry.objects.filter(
                student__guardian_accounts=request.user,
            )
        elif request.user.role == 'student' and request.user.student_profile_id:
            queryset = ResultEntry.objects.filter(
                student_id=request.user.student_profile_id,
            )
        else:
            raise PermissionDenied('Published self-service results are for students and linked parents.')

        queryset = queryset.filter(
            sheet__school_id=request.user.school_id,
            sheet__status__in=[
                ResultSheet.Status.PUBLISHED,
                ResultSheet.Status.LOCKED,
            ],
        ).select_related(
            'student', 'sheet__class_obj', 'sheet__academic_session',
        ).order_by(
            'student__last_name',
            'student__first_name',
            '-sheet__academic_session__start_year',
            'sheet__term',
            'sheet__subject',
        )
        return Response(_paginate(queryset, request, _MyPublishedResultSerializer))


class ResultSheetListView(APIView):
    """List a school's result sheets, or open one to read its scores.

    Always scoped to the caller's school, and the session/class filters are
    resolved against that school too, so a School A user cannot read a School B
    sheet by changing the id in the query string.
    """

    permission_classes = [IsAuthenticated, HasSchool, require_permissions('results.read')]

    def get(self, request):
        school = request.user.school
        queryset = (
            ResultSheet.objects
            .filter(school=school)
            .select_related('academic_session', 'class_obj')
            .annotate(student_count=Count('entries'))
            .order_by('-created_at', '-id')
        )
        session_id = request.query_params.get('sessionId')
        if session_id:
            session = get_object_or_404(
                AcademicSession.objects.filter(school=school), id=session_id,
            )
            queryset = queryset.filter(academic_session=session)
        else:
            session = academic_service.current_session(school)
            if session is not None:
                queryset = queryset.filter(academic_session=session)

        class_name = request.query_params.get('className', '').strip()
        if class_name:
            queryset = queryset.filter(class_obj__name=class_name)
        subject = request.query_params.get('subject', '').strip()
        if subject:
            queryset = queryset.filter(subject__iexact=subject)
        status_filter = request.query_params.get('status', '').strip()
        if status_filter:
            queryset = queryset.filter(status=status_filter)

        return Response(_paginate(queryset, request, _ResultSheetListSerializer))


class ResultSheetDetailView(APIView):
    """One sheet with its scores."""

    permission_classes = [IsAuthenticated, HasSchool, require_permissions('results.read')]

    def get(self, request, pk):
        sheet = get_object_or_404(
            ResultSheet.objects.select_related('academic_session', 'class_obj'),
            id=pk, school_id=request.user.school_id,
        )
        return Response(result_service.sheet_detail(sheet))


class ResultSheetActionView(APIView):
    """Drive a sheet through its lifecycle.

    One endpoint, many actions, so the state machine lives in
    `records.services.results` rather than being spread across routes. Each
    action requires the permission that owns that step, and the transition
    itself is validated server-side: a client cannot jump a sheet straight to
    PUBLISHED or unlock a LOCKED one without an authorised correction.
    """

    permission_classes = [IsAuthenticated, HasSchool]

    #: action -> permission required to perform it.
    ACTION_PERMISSIONS = {
        'scores': 'results.write',
        'submit': 'results.write',
        'review': 'results.approve',
        'approve': 'results.approve',
        'publish': 'results.publish',
        'lock': 'results.publish',
        'request-correction': 'results.write',
        'release-correction': 'results.publish',
    }

    def post(self, request, pk):
        action = request.data.get('action', '').strip()
        required = self.ACTION_PERMISSIONS.get(action)
        if required is None:
            raise ValidationError({
                'action': f'"{action}" is not a results action.',
            })
        if not has_permission(request.user.role, required):
            raise PermissionDenied(
                f'You do not have permission to {action.replace("-", " ")} a result sheet.',
            )

        sheet = get_object_or_404(
            ResultSheet.objects.select_related('academic_session', 'class_obj', 'school'),
            id=pk, school_id=request.user.school_id,
        )

        if action == 'scores':
            term_scores = request.data.get('termScores')
            if term_scores is not None:
                updated = result_service.record_term_scores(sheet, term_scores)
            else:
                updated = result_service.record_scores(sheet, request.data.get('scores') or {})
            return Response({'updated': updated, **result_service.sheet_detail(sheet)})
        if action == 'request-correction':
            result_service.request_correction(
                sheet, str(request.data.get('reason') or ''), actor=request.user,
            )
        elif action == 'release-correction':
            result_service.release_for_correction(sheet, actor=request.user)
        else:
            target = {
                'submit': ResultSheet.Status.SUBMITTED,
                'review': ResultSheet.Status.UNDER_REVIEW,
                'approve': ResultSheet.Status.APPROVED,
                'publish': ResultSheet.Status.PUBLISHED,
                'lock': ResultSheet.Status.LOCKED,
            }[action]
            result_service.advance(sheet, target, actor=request.user)

        sheet.refresh_from_db()
        event_service.result_sheet_advanced(sheet, action)
        log_audit(
            request, f'result.{action}', target=f'ResultSheet {sheet.id}',
            detail=f'{sheet.class_obj.name} {sheet.subject} {sheet.assessment} -> {sheet.status}',
            entity='result_sheet', entity_id=str(sheet.pk), after={'status': sheet.status},
        )
        return Response(result_service.sheet_detail(sheet))


class AssistantToolsView(APIView):
    """What the assistant is allowed to do, for this user, right now.

    The catalogue is computed from the same permission table the enforcement
    uses, so the UI cannot offer a capability the backend would refuse.
    """

    permission_classes = [IsAuthenticated, HasSchool]

    def get(self, request):
        granted = ai_tools.assistant_permissions(request.user)
        return Response({
            'assistantPermissions': granted,
            'tools': ai_tools.tool_catalogue(request.user),
        })


class AssistantQueryView(APIView):
    """The assistant endpoint (spec 62-68).

    It accepts a tool name plus arguments, and does exactly three things:
    authorise, call the real service, return the result. There is no free-form
    data path and no server-side prompt that could widen access, because a
    model's choice of tool is untrusted input and is authorised exactly like any
    other request.

    Writes are two-phase: the first call returns a confirmation token, and only
    a second call carrying that token performs the action.
    """

    permission_classes = [IsAuthenticated, HasSchool]

    def post(self, request):
        if not ai_tools.assistant_permissions(request.user):
            raise PermissionDenied('Your role does not have access to the assistant.')

        action = str(request.data.get('action') or '').strip()
        if action == 'confirm':
            return Response(ai_tools.confirm_write(
                request.user,
                str(request.data.get('writeAction') or ''),
                str(request.data.get('confirmationToken') or ''),
            ))
        if action == 'propose':
            return Response(ai_tools.propose_write(
                request.user,
                str(request.data.get('writeAction') or ''),
                request.data.get('arguments') or {},
            ))

        tool = str(request.data.get('tool') or '').strip()
        if not tool:
            raise ValidationError({'tool': 'Name the assistant tool to run.'})
        result = ai_tools.call_tool(request.user, tool, request.data.get('arguments') or {})
        return Response({'tool': tool, 'data': result})


class ResultSheetCreateView(APIView):
    """Create a DRAFT sheet for a class/subject/assessment, seeded from the roster."""

    permission_classes = [IsAuthenticated, HasSchool, require_permissions('results.write')]

    def post(self, request):
        school = request.user.school
        session = academic_service.current_session(school)
        if session is None:
            raise ValidationError({'session': 'This school has no current academic session.'})
        class_queryset = SchoolClass.objects.filter(school=school)
        class_id = request.data.get('classId')
        if class_id:
            class_obj = get_object_or_404(class_queryset, id=class_id)
        else:
            class_name = str(request.data.get('className') or '').strip()
            class_obj = get_object_or_404(class_queryset, name=class_name)
        subject = str(request.data.get('subject') or '').strip()
        term = str(request.data.get('term') or '').strip()
        if not subject or not term:
            raise ValidationError({
                'fields': 'A term result sheet needs a subject and term.',
            })
        sheet = result_service.create_sheet(
            school=school,
            academic_session=session,
            class_obj=class_obj,
            subject=subject,
            assessment=result_service.TERM_RESULTS_ASSESSMENT,
            assessment_max='100',
            term=term,
        )
        return Response(result_service.sheet_detail(sheet), status=status.HTTP_201_CREATED)


# ── Attendance ─────────────────────────────────────────────────────────────

class AttendanceRosterView(APIView):
    """The class register for one school day, resolved from Enrollment.

    `Student.class_name` is a denormalised mirror and is NOT authoritative for
    class membership: a stale or wrong value must not place a student in the
    wrong register. Membership comes from an ACTIVE `Enrollment` row, scoped to
    the caller's school (spec §35, §97).

    There is no subject dimension: attendance is taken once per school day.
    """

    permission_classes = [IsAuthenticated, HasSchool, CanReadAttendance]

    def get(self, request):
        school = request.user.school
        class_name = request.query_params.get('className', '').strip()
        arm = request.query_params.get('arm', '').strip()
        raw_date = request.query_params.get('date', '').strip()
        day = parse_date(raw_date) if raw_date else timezone.localdate()

        session = academic_service.current_session(school)

        # A class this school has configured but never provisioned as a
        # `SchoolClass` row is NOT a 404: it belongs to this school, so the
        # register is simply empty. Cross-school and unknown names still 404,
        # because the lookup is scoped to the caller's own school.
        school_class = attendance_service.resolve_class(school, class_name)
        if school_class is None:
            if not class_name or not attendance_service.is_configured_class(school, class_name):
                raise Http404

        section = None
        if arm and school_class is not None:
            section = attendance_service.resolve_section(school, school_class, arm)
            if section is None:
                raise Http404

        rows = attendance_service.roster_for(school, school_class, section, session)
        existing = attendance_service.existing_marks(school, school_class, day)

        # One lookup serves both the teacher's name and whether THIS caller may
        # submit, so the register costs no extra query to become read-only-aware.
        assignment = (
            attendance_service.class_teacher_for(school, school_class, session)
            if school_class is not None else None
        )
        can_submit = (
            request.user.role == 'school_admin'
            or (
                assignment is not None
                and getattr(request.user, 'staff_profile_id', None) == assignment.staff_id
            )
        )

        return Response({
            'students': rows,
            'date': day.isoformat(),
            'taken': bool(existing),
            'existing': existing,
            'classId': school_class.id if school_class else None,
            'className': school_class.name if school_class else class_name,
            'classConfigured': school_class is not None,
            'sections': list(
                school.sections.filter(class_obj=school_class).order_by('sort_order', 'name')
                .values_list('name', flat=True)
            ) if school_class is not None else [],
            'classTeacher': assignment.staff.full_name if assignment else '',
            'isSchoolDay': attendance_service.is_school_day(school, day),
            # Whether THIS caller may submit, so the client shows the register as
            # read-only instead of offering a Save that the server will reject.
            'canSubmit': school_class is not None and can_submit,
        })


class AttendanceSubmitView(APIView):
    """Save a whole-class register for one school day, in one transaction."""

    permission_classes = [IsAuthenticated, HasSchool, CanWriteAttendance]

    def post(self, request):
        serializer = AttendanceSubmitSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        school = request.user.school
        school_class = attendance_service.resolve_class(school, data['className'])
        if school_class is None:
            raise ValidationError({
                'className': f'"{data["className"]}" is not a class in this school.',
            })
        # An unrecognised arm must be rejected, not quietly widened to the whole
        # class: `resolve_section` returns None for both "no arm" and "bad arm",
        # so an ignored bad arm would record every student in the class under a
        # section the caller never asked for.
        raw_arm = (data.get('arm') or '').strip()
        section = attendance_service.resolve_section(school, school_class, raw_arm)
        if raw_arm and section is None:
            raise ValidationError({
                'arm': f'"{raw_arm}" is not a section of {school_class.name}.',
            })

        try:
            result = attendance_service.submit_register(
                user=request.user,
                school=school,
                class_obj=school_class,
                day=data['date'],
                records=data['records'],
                section=section,
            )
        except attendance_service.DuplicateRegister as duplicate:
            # Do not create a second register: hand back what was already taken so
            # the client can display it.
            return Response(
                {
                    'detail': (
                        f'Attendance has already been recorded for '
                        f'{school_class.name} on {data["date"].isoformat()}.'
                    ),
                    'taken': True,
                    'existing': duplicate.existing,
                },
                status=status.HTTP_409_CONFLICT,
            )

        return Response({
            'id': request.data.get('id', ''),
            'saved': result.saved,
            'skipped': result.skipped,
            'byStatus': result.by_status,
            'date': data['date'].isoformat(),
        }, status=status.HTTP_201_CREATED)


class AttendanceOverviewView(APIView):
    """Which classes have submitted their register today, and which have not.

    The admin board. Teachers only ever see their own assigned classes.
    """

    permission_classes = [IsAuthenticated, HasSchool, CanReadAttendance]

    def get(self, request):
        school = request.user.school
        raw_date = request.query_params.get('date', '').strip()
        day = parse_date(raw_date) if raw_date else timezone.localdate()

        classes = school.school_classes.filter(is_active=True)
        if request.user.role == 'teacher':
            staff = getattr(request.user, 'staff_profile', None)
            if staff is None:
                classes = classes.none()
            else:
                classes = classes.filter(
                    class_teacher_assignments__staff=staff,
                    class_teacher_assignments__academic_session=academic_service.current_session(school),
                ).distinct()

        rows = attendance_service.overview_for(school, day, class_objs=classes)
        return Response({
            'date': day.isoformat(),
            'isSchoolDay': attendance_service.is_school_day(school, day),
            'classes': rows,
            'submitted': sum(1 for row in rows if row['submitted'] > 0),
            'total': len(rows),
        })


class AttendanceHistoryView(APIView):
    """Attendance history for a class or a single student over a date range."""

    permission_classes = [IsAuthenticated, HasSchool, CanReadAttendance]

    def get(self, request):
        school = request.user.school
        params = request.query_params

        class_obj = None
        class_name = params.get('className', '').strip()
        if class_name:
            class_obj = attendance_service.resolve_class(school, class_name)
            if class_obj is None:
                raise Http404

        student = None
        student_id = params.get('studentId', '').strip()
        if student_id:
            # School-scoped, so a student from another school is a 404 here.
            student = get_object_or_404(
                Student.objects.filter(school_id=school.id), pk=student_id,
            )

        raw_date_from = params.get('dateFrom', '').strip()
        raw_date_to = params.get('dateTo', '').strip()
        date_from = parse_date(raw_date_from) if raw_date_from else None
        date_to = parse_date(raw_date_to) if raw_date_to else None
        if raw_date_from and date_from is None:
            raise ValidationError({'dateFrom': 'Enter a valid date in YYYY-MM-DD format.'})
        if raw_date_to and date_to is None:
            raise ValidationError({'dateTo': 'Enter a valid date in YYYY-MM-DD format.'})
        if date_from and date_to and date_from > date_to:
            raise ValidationError({'dateFrom': 'The start date cannot be after the end date.'})

        # A teacher holds `attendance.read` for the school, so without narrowing
        # here a free-text search would read any student's history. They are
        # confined to the classes they teach; other roles keep the full school.
        allowed = attendance_service.teacher_visible_class_ids(
            school, request.user, academic_service.current_session(school),
        )
        if class_obj is not None and allowed is not None and class_obj.id not in allowed:
            raise Http404
        if student is not None and allowed is not None:
            student_classes = attendance_service.history_class_ids_for_student(
                school, student, allowed,
            )
            if not student_classes:
                # 404, not 403: this user may not know the student exists.
                raise Http404
            allowed = student_classes

        records = attendance_service.history_for(
            school, student=student, class_obj=class_obj,
            date_from=date_from, date_to=date_to,
            allowed_class_ids=allowed,
        )
        page_records, count, page, page_size = _pagination_window(records, request)
        return Response({
            'records': [
                {
                    'id': record.id,
                    'studentId': str(record.student_id),
                    'studentName': f'{record.student.first_name} {record.student.last_name}'.strip(),
                    'admissionNumber': record.student.admission_number,
                    'className': record.class_name,
                    'date': record.date.isoformat(),
                    'status': record.status,
                    'submittedBy': record.submitted_by.get_full_name() if record.submitted_by else '',
                    'updatedAt': record.updated_at.isoformat(),
                }
                for record in page_records
            ],
            'count': count,
            'page': page,
            'pageSize': page_size,
            'totalPages': max((count + page_size - 1) // page_size, 1),
        })


class AttendanceCorrectView(APIView):
    """Amend one line of an already-taken register.

    Always audited: the before/after status and the reason are written to the
    audit log, so a corrected register stays explainable.
    """

    permission_classes = [IsAuthenticated, HasSchool, CanCorrectAttendance]

    def post(self, request):
        serializer = AttendanceCorrectionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        school = request.user.school
        change = attendance_service.correct_record(
            user=request.user,
            school=school,
            record_id=int(data['recordId']),
            new_status=data['status'],
            reason=data['reason'],
        )
        if not change['changed']:
            return Response({'changed': False, 'status': change['status']})

        # `before`/`after` are stored separately so a reviewer reads the change
        # without diffing tables; the reason is kept in the detail line.
        log_audit(
            request,
            action='attendance.correct',
            target=f'AttendanceRecord {data["recordId"]}',
            detail=change['reason'],
            entity='AttendanceRecord',
            entity_id=str(data['recordId']),
            before={'status': change['previousStatus']},
            after={'status': change['status']},
        )
        return Response({'changed': True, **change})


# ── Academics ──────────────────────────────────────────────────────────────

DEFAULT_CLASSES = [
    'Nursery 1',
    'Nursery 2',
    'Primary 1',
    'Primary 2',
    'Primary 3',
    'Primary 4',
    'Primary 5',
    'Primary 6',
    'JSS 1',
    'JSS 2',
    'JSS 3',
    'SS 1',
    'SS 2',
    'SS 3',
]

class AcademicsView(APIView):
    permission_classes = [IsAuthenticated, HasSchool]

    def _school(self, request):
        return get_object_or_404(School, id=request.user.school_id)

    def _payload(self, school):
        # Classes come from `SchoolClass`, which is what rosters resolve against.
        # Falling back to the 14-name default list here is what let a dropdown
        # offer a class the roster then 404'd on. Reading the JSON mirror
        # instead is what left an already-provisioned school showing an EMPTY
        # dropdown, because the mirror was never written. So `SchoolClass` is
        # authoritative and is synced back onto the mirror on read.
        return {
            'session': school.current_session,
            'term': school.current_term,
            'classes': academic_service.sync_school_class_names(school),
            'classIds': {
                row['name']: row['id']
                for row in school.school_classes.filter(is_active=True)
                .order_by('sort_order', 'name').values('id', 'name')
            },
            'subjects': school.subjects or DEFAULT_SUBJECTS,
            # The school calendar: which weekdays are non-teaching, and any
            # declared closures. Both feed `is_school_day`, so an unattended
            # register on a Sunday is a closure rather than a missing teacher.
            'attendanceWeekendDays': list(school.attendance_weekend_days or []),
            'nonSchoolDays': list(school.non_school_days or []),
        }

    def get(self, request):
        return Response(self._payload(self._school(request)))

    def patch(self, request):
        if not CanWriteAcademics().has_permission(request, self):
            raise PermissionDenied('You do not have permission to change academic settings.')
        school = self._school(request)
        update = []

        session = (request.data.get('session') or '').strip()
        term = (request.data.get('term') or '').strip()
        parsed_session = None
        if session:
            parsed_session = academic_service.parse_session_name(session)
            school.current_session = session
            update.append('current_session')
        if term:
            school.current_term = term
            update.append('current_term')

        # The calendar is sent only when the key is present, so a caller updating
        # the term alone does not silently wipe the school's weekends.
        if 'attendanceWeekendDays' in request.data:
            weekend = request.data.get('attendanceWeekendDays')
            if not isinstance(weekend, list):
                raise ValidationError({
                    'attendanceWeekendDays': 'Send the weekend days as a list of weekday '
                                             'numbers (Monday is 0).',
                })
            cleaned: list[int] = []
            for raw in weekend:
                try:
                    day = int(raw)
                except (TypeError, ValueError):
                    raise ValidationError({
                        'attendanceWeekendDays': f'"{raw}" is not a weekday number.',
                    })
                if day < 0 or day > 6:
                    raise ValidationError({
                        'attendanceWeekendDays': 'Weekday numbers run from 0 (Monday) '
                                                 'to 6 (Sunday).',
                    })
                if day not in cleaned:
                    cleaned.append(day)
            # Every day as a non-teaching day would silently switch the whole
            # register off, so it is refused rather than accepted.
            if len(cleaned) >= 7:
                raise ValidationError({
                    'attendanceWeekendDays': 'At least one weekday has to be a '
                                             'teaching day.',
                })
            school.attendance_weekend_days = sorted(cleaned)
            update.append('attendance_weekend_days')

        if 'nonSchoolDays' in request.data:
            closures = request.data.get('nonSchoolDays')
            if not isinstance(closures, list):
                raise ValidationError({
                    'nonSchoolDays': 'Send the closure dates as a list of YYYY-MM-DD strings.',
                })
            parsed: list[str] = []
            for raw in closures:
                day = parse_date(str(raw).strip())
                if day is None:
                    raise ValidationError({
                        'nonSchoolDays': f'"{raw}" is not a date. Use YYYY-MM-DD.',
                    })
                iso = day.isoformat()
                if iso not in parsed:
                    parsed.append(iso)
            # Stored sorted so the list reads chronologically wherever it is shown.
            school.non_school_days = sorted(parsed)
            update.append('non_school_days')

        if not update:
            raise ValidationError({
                'session': 'Provide a session, term or calendar setting to update.',
            })
        if session and parsed_session:
            start_year, end_year = parsed_session
            target_session = academic_service.ensure_session(
                school, session, start_year=start_year, end_year=end_year,
            )
            school.sessions.exclude(pk=target_session.pk).filter(is_current=True).update(
                is_current=False,
            )
            target_session.is_active = True
            target_session.is_current = True
            target_session.save(update_fields=['is_active', 'is_current'])
        school.save(update_fields=update)
        return Response(self._payload(school))


class AcademicSubjectsView(APIView):
    permission_classes = [IsAuthenticated, HasSchool, CanWriteRecords]

    def post(self, request):
        school = get_object_or_404(School, id=request.user.school_id)
        name = (request.data.get('name') or '').strip()
        if not name:
            raise ValidationError({'name': 'A subject name is required.'})
        subjects = list(school.subjects or DEFAULT_SUBJECTS)
        if name not in subjects:
            subjects.append(name)
            school.subjects = subjects
            school.save(update_fields=['subjects'])
        return Response(AcademicsView()._payload(school))


class AcademicSubjectDetailView(APIView):
    permission_classes = [IsAuthenticated, HasSchool, CanWriteRecords]

    def delete(self, request, name):
        school = get_object_or_404(School, id=request.user.school_id)
        subjects = list(school.subjects or DEFAULT_SUBJECTS)
        if name in subjects:
            subjects.remove(name)
            school.subjects = subjects
            school.save(update_fields=['subjects'])
        return Response(AcademicsView()._payload(school))


class AcademicClassesView(APIView):
    permission_classes = [IsAuthenticated, HasSchool, CanWriteRecords]

    def post(self, request):
        school = get_object_or_404(School, id=request.user.school_id)
        name = (request.data.get('name') or '').strip()
        if not name:
            raise ValidationError({'name': 'A class name is required.'})
        level_code = (request.data.get('level') or '').strip()
        # Create the real `SchoolClass` row, not just the dropdown string: a class
        # that exists only in `School.classes` has no roster, which is precisely
        # the split this endpoint used to create.
        academic_service.ensure_class(school, name, level_code=level_code or None)
        academic_service.sync_school_class_names(school)
        return Response(AcademicsView()._payload(school))


class AcademicClassDetailView(APIView):
    permission_classes = [IsAuthenticated, HasSchool, CanWriteRecords]

    def delete(self, request, name):
        school = get_object_or_404(School, id=request.user.school_id)
        class_obj = get_object_or_404(
            school.school_classes.all(), name=name,
        )
        # Retired rather than deleted: enrollments reference it, and the
        # attendance history for a past day must stay readable.
        class_obj.is_active = False
        class_obj.save(update_fields=['is_active'])
        academic_service.sync_school_class_names(school)
        return Response(AcademicsView()._payload(school))


# ── Timetable (spec §22) ───────────────────────────────────────────────────────
# One capability, two tables: the school's bell schedule (periods) and the
# lessons placed on it (entries). Reads are open to anyone holding
# `timetable.read`; writes are refused for everyone else. Role scoping of the
# *rows* a read returns lives in services.timetable.resolve_scope, because a
# teacher and a pupil must never see the whole school's grid.

# Audit lines are written by hand because the audit trail is read by staff who
# need to know *which* slot changed without opening the record.
def _entry_detail(entry) -> str:
    return (
        f'{entry.class_obj.name} {entry.subject} '
        f'{timetable_service.WEEKDAY_NAMES[entry.weekday]} {entry.period.name}'
    )


def _period_detail(period) -> str:
    return f'{period.name} {period.start_time:%H:%M}-{period.end_time:%H:%M}'


class TimetableView(APIView):
    """GET the week's grid plus everything the editor needs to place a lesson."""

    permission_classes = [IsAuthenticated, HasSchool]

    def get(self, request):
        school = get_object_or_404(School, id=request.user.school_id)
        return Response(timetable_service.grid_payload(
            request.user, school, request.query_params,
        ))


class TimetableEntryCreateView(APIView):
    permission_classes = [IsAuthenticated, HasSchool]

    def post(self, request):
        if not CanWriteTimetable().has_permission(request, self):
            raise PermissionDenied('You do not have permission to build the timetable.')
        school = get_object_or_404(School, id=request.user.school_id)
        entry = timetable_service.create_entry(school, request.data)
        log_audit(
            request, 'timetable.entry_created', target=f'TimetableEntry {entry.pk}',
            detail=_entry_detail(entry),
            entity='timetable_entry', entity_id=str(entry.pk),
            after={
                'class': entry.class_obj.name,
                'subject': entry.subject,
                'weekday': entry.weekday,
                'period': entry.period.name,
                'teacher': entry.teacher.full_name if entry.teacher else '',
                'room': entry.room,
            },
        )
        return Response(
            timetable_service.entry_payload(entry),
            status=status.HTTP_201_CREATED,
        )


class TimetableEntryDetailView(APIView):
    permission_classes = [IsAuthenticated, HasSchool]

    def _entry(self, request, pk):
        school = get_object_or_404(School, id=request.user.school_id)
        # Scoped by school inside the lookup: a pk belonging to another school
        # must be a 404 here rather than a row this school can read.
        entry = get_object_or_404(
            TimetableEntry.objects.select_related('period', 'class_obj', 'teacher'),
            pk=pk, school=school,
        )
        return school, entry

    def get(self, request, pk):
        _, entry = self._entry(request, pk)
        return Response(timetable_service.entry_payload(entry))

    def patch(self, request, pk):
        if not CanWriteTimetable().has_permission(request, self):
            raise PermissionDenied('You do not have permission to build the timetable.')
        school, entry = self._entry(request, pk)
        updated = timetable_service.update_entry(school, entry, request.data)
        log_audit(
            request, 'timetable.entry_updated', target=f'TimetableEntry {updated.pk}',
            detail=_entry_detail(updated),
            entity='timetable_entry', entity_id=str(updated.pk),
            after={
                'class': updated.class_obj.name,
                'subject': updated.subject,
                'weekday': updated.weekday,
                'period': updated.period.name,
                'teacher': updated.teacher.full_name if updated.teacher else '',
                'room': updated.room,
            },
        )
        return Response(timetable_service.entry_payload(updated))

    def delete(self, request, pk):
        if not CanWriteTimetable().has_permission(request, self):
            raise PermissionDenied('You do not have permission to build the timetable.')
        school, entry = self._entry(request, pk)
        log_audit(
            request, 'timetable.entry_deleted', target=f'TimetableEntry {entry.pk}',
            detail=_entry_detail(entry),
            entity='timetable_entry', entity_id=str(entry.pk),
            before={
                'class': entry.class_obj.name,
                'subject': entry.subject,
                'weekday': entry.weekday,
                'period': entry.period.name,
            },
        )
        timetable_service.delete_entry(school, entry)
        return Response(status=status.HTTP_204_NO_CONTENT)


class TimetablePeriodCreateView(APIView):
    permission_classes = [IsAuthenticated, HasSchool]

    def post(self, request):
        if not CanWriteTimetable().has_permission(request, self):
            raise PermissionDenied('You do not have permission to change the school day.')
        school = get_object_or_404(School, id=request.user.school_id)
        period = timetable_service.create_period(school, request.data)
        log_audit(
            request, 'timetable.period_created', target=f'TimetablePeriod {period.pk}',
            detail=_period_detail(period),
            entity='timetable_period', entity_id=str(period.pk),
            after={'name': period.name, 'isBreak': period.is_break},
        )
        return Response(
            timetable_service.period_payload(period),
            status=status.HTTP_201_CREATED,
        )


class TimetablePeriodDetailView(APIView):
    permission_classes = [IsAuthenticated, HasSchool]

    def _period(self, request, pk):
        school = get_object_or_404(School, id=request.user.school_id)
        return school, get_object_or_404(TimetablePeriod, pk=pk, school=school)

    def patch(self, request, pk):
        if not CanWriteTimetable().has_permission(request, self):
            raise PermissionDenied('You do not have permission to change the school day.')
        school, period = self._period(request, pk)
        updated = timetable_service.update_period(school, period, request.data)
        log_audit(
            request, 'timetable.period_updated', target=f'TimetablePeriod {updated.pk}',
            detail=_period_detail(updated),
            entity='timetable_period', entity_id=str(updated.pk),
            after={'name': updated.name, 'isBreak': updated.is_break},
        )
        return Response(timetable_service.period_payload(updated))

    def delete(self, request, pk):
        if not CanWriteTimetable().has_permission(request, self):
            raise PermissionDenied('You do not have permission to change the school day.')
        school, period = self._period(request, pk)
        # Deleting a period cascades to its lessons, which is almost never what an
        # administrator means, so an in-use period is refused with the count that
        # explains why rather than silently deleting a morning of teaching.
        lessons = period.entries.count()
        if lessons:
            raise ValidationError({
                'name': f'{period.name} still holds {lessons} '
                        f'{"lesson" if lessons == 1 else "lessons"}. '
                        f'Move or remove them first, then delete the period.',
            })
        log_audit(
            request, 'timetable.period_deleted', target=f'TimetablePeriod {period.pk}',
            detail=_period_detail(period),
            entity='timetable_period', entity_id=str(period.pk),
            before={'name': period.name},
        )
        period.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


# ─── Notifications (spec 32) ──────────────────────────────────────────────
#
# Every endpoint here is self-service: the caller reads and writes their own
# notifications and nothing else. There is deliberately no `schoolId` filter and
# no permission from the role matrix, because a notification feed is a private
# inbox rather than a school record — a parent reading their own inbox is not
# exercising a management right, and requiring one would have locked parents and
# students out of their own mail.
#
# The queryset is built from `request.user` on every path and never from
# request data, so there is no id here that could be tampered with to reach
# somebody else's notifications.


def _notification_json(item):
    return {
        'id': str(item.pk),
        'type': item.type,
        'title': item.title,
        'body': item.body,
        'link': item.link,
        'createdAt': item.created_at.isoformat(),
        'read': item.read,
        'readAt': item.read_at.isoformat() if item.read_at else None,
    }


def _notification_page(queryset, request):
    """Page a queryset and return the envelope the frontend list screens read.

    `count` and `unread` are both returned: the header badge needs the unread
    total on every poll, and making it a separate request would double the
    traffic of the most frequently called endpoint in the product.
    """
    try:
        page_number = max(1, int(request.query_params.get('page', 1)))
        page_size = min(50, max(1, int(request.query_params.get('pageSize', 20))))
    except (TypeError, ValueError):
        raise ValidationError({'page': 'page and pageSize must be numbers.'})

    total = queryset.count()
    start = (page_number - 1) * page_size
    rows = list(queryset[start:start + page_size])
    return {
        'results': [_notification_json(item) for item in rows],
        'count': total,
        'page': page_number,
        'pageSize': page_size,
        'hasMore': start + page_size < total,
        'unread': Notification.objects.filter(
            user=request.user, read_at__isnull=True,
        ).count(),
    }


def _coerce_bool(value, field, default=False):
    """Read a JSON boolean strictly.

    `bool("false")` is True, so a client that sends the string "false" would
    silently flip a flag the wrong way. Anything that is not already a boolean
    is rejected so the author finds out instead of guessing.
    """
    if value is None:
        return default
    if not isinstance(value, bool):
        raise ValidationError({field: 'Send true or false, not a string.'})
    return value


def _parse_expiry(raw, field='expiresAt'):
    """Parse an announcement expiry, refusing one that has already passed.

    Returns None for an absent or explicitly cleared value, which is how an
    announcement says "keep this until I delete it".
    """
    if raw in (None, ''):
        return None
    parsed = parse_datetime(raw)
    if parsed is None:
        raise ValidationError({field: 'Use an ISO 8601 date and time.'})
    if parsed <= timezone.now():
        raise ValidationError({field: 'That expiry is already in the past.'})
    return parsed


class NotificationListView(APIView):
    """The caller's own notification feed.

    Supports the two reads README 32 asks for: everything, and unread only.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        queryset = Notification.objects.filter(user=request.user)
        unread_only = str(request.query_params.get('unread', '')).lower() in (
            '1', 'true', 'yes',
        )
        if unread_only:
            queryset = queryset.filter(read_at__isnull=True)
        type_filter = (request.query_params.get('type') or '').strip()
        if type_filter:
            valid = {c[0] for c in Notification.Type.choices}
            if type_filter not in valid:
                raise ValidationError({'type': f'Unknown notification type {type_filter!r}.'})
            queryset = queryset.filter(type=type_filter)
        return Response(_notification_page(queryset.order_by('-created_at', '-id'), request))


class NotificationMarkReadView(APIView):
    """Mark one of the caller's own notifications read."""

    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        # Scoped to request.user in the lookup itself: a notification belonging
        # to somebody else is simply not found, never forbidden-but-revealed.
        item = get_object_or_404(
            Notification, pk=pk, user=request.user,
        )
        notification_service.mark_read(item)
        return Response(_notification_json(item))


class NotificationReadAllView(APIView):
    """Mark every unread notification for the caller read."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        updated = notification_service.mark_all_read(request.user)
        return Response({'markedRead': updated, 'unread': 0})


class NotificationPreferenceView(APIView):
    """Per-type opt-in/out, backing Settings -> Notifications.

    GET always returns all eight types, filling in the ones with no stored row,
    so the client never has to know that "no row" means "enabled".
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        stored = {
            pref.type: pref.in_app
            for pref in NotificationPreference.objects.filter(user=request.user)
        }
        return Response([
            {'type': value, 'label': label, 'inApp': stored.get(value, True)}
            for value, label in Notification.Type.choices
        ])

    def patch(self, request):
        payload = request.data.get('preferences') if isinstance(request.data, dict) else None
        if not isinstance(payload, list):
            raise ValidationError({
                'preferences': 'Send a list of {type, inApp} objects.',
            })
        valid = {c[0] for c in Notification.Type.choices}
        rows = []
        for entry in payload:
            if not isinstance(entry, dict) or entry.get('type') not in valid:
                raise ValidationError({
                    'preferences': f'Each entry needs a valid type. One of: '
                                   f'{", ".join(sorted(valid))}.',
                })
            if not isinstance(entry.get('inApp', True), bool):
                # Deliberately not `bool(...)`: the string "false" is truthy, so
                # a loose cast would silently switch a preference *on* for a
                # client that meant to turn it off.
                raise ValidationError({
                    'preferences': 'inApp must be true or false, not a string.',
                })
            rows.append(NotificationPreference(
                user=request.user,
                type=entry['type'],
                in_app=entry['inApp'],
            ))
        # One upsert rather than update_or_create per row: the pair is unique, so
        # a second save of the same toggle must update in place instead of
        # raising, and doing it in a single statement keeps this at one query
        # instead of two per toggle.
        NotificationPreference.objects.bulk_create(
            rows,
            update_conflicts=True,
            update_fields=['in_app'],
            unique_fields=['user', 'type'],
        )
        return Response(self.get(request).data)


# ─── Announcements (spec 30) ───────────────────────────────────────────────


class AnnouncementListCreateView(APIView):
    """Read the board, and publish to it.

    Reading is audience-filtered self-service: staff holding
    `communication.read` see the whole school board, parents and students see
    only their own audience. Publishing requires `communication.write`.
    """

    permission_classes = [IsAuthenticated, HasSchool]

    def get(self, request):
        items = announcement_service.visible_to(request.user)[:100]
        return Response([announcement_service.serialise(item) for item in items])

    def post(self, request):
        if not has_permission(request.user.role, 'communication.write'):
            raise PermissionDenied('You cannot publish announcements.')

        title = (request.data.get('title') or '').strip()
        body = (request.data.get('body') or '').strip()
        if not title:
            raise ValidationError({'title': 'A title is required.'})
        if not body:
            raise ValidationError({'body': 'Write the message you want to send.'})

        raw_audience = request.data.get('audience') or []
        if not isinstance(raw_audience, list):
            raise ValidationError({'audience': 'Audience must be a list of labels.'})
        # `create` fails closed on an unknown label, so check it here where the
        # author can be told, rather than silently publishing to nobody.
        audience = announcement_service.normalise_audience(raw_audience)
        if not audience:
            raise ValidationError({
                'audience': 'Choose who should receive this. '
                            'One of: All, Staff, Parents, Students.',
            })

        expires_at = _parse_expiry(request.data.get('expiresAt'))

        item = announcement_service.create(
            school=request.user.school,
            author=request.user,
            title=title,
            body=body,
            audience=audience,
            is_pinned=_coerce_bool(request.data.get('isPinned'), 'isPinned', False),
            expires_at=expires_at,
        )
        log_audit(
            request, 'announcement.published', target=item.title,
            detail=f'{len(audience)} audience(s)',
            entity='announcement', entity_id=str(item.pk),
            after={'title': item.title, 'audience': audience},
        )
        return Response(announcement_service.serialise(item), status=status.HTTP_201_CREATED)


class AnnouncementDetailView(APIView):
    """Pin, unpin, edit or withdraw one school announcement."""

    permission_classes = [IsAuthenticated, HasSchool]

    def _get(self, request, pk):
        # Scoped to the caller's own school so another tenant's notice is not
        # reachable by guessing an id.
        return get_object_or_404(Announcement, pk=pk, school_id=request.user.school_id)

    def _require_write(self, request):
        if not has_permission(request.user.role, 'communication.write'):
            raise PermissionDenied('You cannot change announcements.')

    def get(self, request, pk):
        item = self._get(request, pk)
        # A parent may only read an announcement addressed to their audience.
        if item.pk not in announcement_service.visible_to(request.user).values_list('pk', flat=True):
            raise Http404
        return Response(announcement_service.serialise(item))

    def patch(self, request, pk):
        self._require_write(request)
        item = self._get(request, pk)
        changed = {}
        if 'title' in request.data:
            title = (request.data.get('title') or '').strip()
            if not title:
                raise ValidationError({'title': 'A title is required.'})
            item.title = title
            changed['title'] = title
        # `fields` holds model field names for update_fields; `changed` holds the
        # camelCase wire keys for the audit trail. Mixing the two would either
        # write nothing or raise FieldError.
        fields: list[str] = []
        changed: dict = {}
        if 'title' in request.data:
            title = (request.data.get('title') or '').strip()
            if not title:
                raise ValidationError({'title': 'A title is required.'})
            item.title = title
            fields.append('title')
            changed['title'] = title
        if 'body' in request.data:
            body = (request.data.get('body') or '').strip()
            if not body:
                raise ValidationError({'body': 'Write the message you want to send.'})
            item.body = body
            fields.append('body')
            changed['body'] = body
        if 'isPinned' in request.data:
            item.is_pinned = _coerce_bool(request.data['isPinned'], 'isPinned')
            fields.append('is_pinned')
            changed['isPinned'] = item.is_pinned
        if 'expiresAt' in request.data:
            # Same rule as create: an expiry in the past would publish a notice
            # that is already gone, which reads as the school losing it.
            item.expires_at = _parse_expiry(request.data['expiresAt'])
            fields.append('expires_at')
            changed['expiresAt'] = item.expires_at.isoformat() if item.expires_at else None
        if not fields:
            raise ValidationError({'detail': 'Nothing to update.'})
        item.save(update_fields=[*fields, 'updated_at'])
        log_audit(
            request, 'announcement.updated', target=item.title,
            detail=', '.join(changed.keys()),
            entity='announcement', entity_id=str(item.pk), after=changed,
        )
        return Response(announcement_service.serialise(item))

    def delete(self, request, pk):
        self._require_write(request)
        item = self._get(request, pk)
        title = item.title
        item.delete()
        log_audit(
            request, 'announcement.deleted', target=title,
            entity='announcement', entity_id=str(pk), before={'title': title},
        )
        return Response(status=status.HTTP_204_NO_CONTENT)


# ── Lesson plans ───────────────────────────────────────────────────────────

LESSON_PLAN_TEXT_FIELDS = {
    'topic': ('topic', True),
    'objectives': ('objectives', True),
    'previousKnowledge': ('previous_knowledge', False),
    'introduction': ('introduction', False),
    'teacherActivities': ('teacher_activities', False),
    'studentActivities': ('student_activities', False),
    'materials': ('materials', False),
    'assessment': ('assessment', False),
    'homework': ('homework', False),
}


def _lesson_plan_payload(plan):
    return {
        'id': str(plan.pk),
        'subject': plan.subject,
        'className': plan.class_obj.name,
        'session': plan.academic_session.name,
        'term': plan.term,
        'topic': plan.topic,
        'durationMinutes': plan.duration_minutes,
        'objectives': plan.objectives,
        'previousKnowledge': plan.previous_knowledge,
        'introduction': plan.introduction,
        'teacherActivities': plan.teacher_activities,
        'studentActivities': plan.student_activities,
        'materials': plan.materials,
        'assessment': plan.assessment,
        'homework': plan.homework,
        'updatedAt': plan.updated_at.isoformat(),
    }


def _lesson_plan_class_and_subject(request, school, data, plan=None):
    class_name = data.get('className', plan.class_obj.name if plan else '')
    subject = data.get('subject', plan.subject if plan else '')
    if not isinstance(class_name, str) or not class_name.strip():
        raise ValidationError({'className': 'Choose a class.'})
    if not isinstance(subject, str) or not subject.strip():
        raise ValidationError({'subject': 'Choose a subject.'})
    if len(class_name.strip()) > 50:
        raise ValidationError({'className': 'Class names must be 50 characters or fewer.'})
    if len(subject.strip()) > 100:
        raise ValidationError({'subject': 'Subject names must be 100 characters or fewer.'})
    if plan and plan.class_obj.name == class_name.strip():
        school_class = plan.class_obj
    else:
        school_class = get_object_or_404(
            SchoolClass.objects.filter(school=school, is_active=True),
            name=class_name.strip(),
        )
    subjects = school.subjects or DEFAULT_SUBJECTS
    canonical_subject = next(
        (name for name in subjects if name.casefold() == subject.strip().casefold()),
        plan.subject if plan and plan.subject.casefold() == subject.strip().casefold() else None,
    )
    if canonical_subject is None:
        raise ValidationError({'subject': 'Choose a subject configured for this school.'})

    if request.user.role == 'teacher':
        staff = getattr(request.user, 'staff_profile', None)
        if staff is None or staff.status != StaffMember.Status.ACTIVE:
            raise PermissionDenied('An active teacher profile is required to write lesson plans.')
        session = academic_service.current_session(school)
        assigned_as_class_teacher = bool(
            session
            and ClassTeacherAssignment.objects.filter(
                school=school, staff=staff, class_obj=school_class,
                academic_session=session,
            ).exists()
        )
        timetable_assignment = TimetableEntry.objects.filter(
            school=school, teacher=staff, class_obj=school_class,
        )
        class_assigned = (
            school_class.name in (staff.classes or [])
            or assigned_as_class_teacher
            or timetable_assignment.exists()
        )
        subject_assigned = (
            canonical_subject.casefold() in {
                value.casefold() for value in (staff.subjects or [])
            }
            or timetable_assignment.filter(subject__iexact=canonical_subject).exists()
            or (assigned_as_class_teacher and not staff.subjects)
        )
        if not class_assigned or not subject_assigned:
            raise PermissionDenied('You can only write plans for your assigned classes and subjects.')
    return school_class, canonical_subject


def _lesson_plan_changes(request, school, plan=None):
    data = request.data
    school_class, subject = _lesson_plan_class_and_subject(request, school, data, plan)
    changes = {'class_obj': school_class, 'subject': subject}

    if 'durationMinutes' in data:
        try:
            duration = int(data['durationMinutes'])
        except (TypeError, ValueError):
            raise ValidationError({'durationMinutes': 'Enter a whole number of minutes.'})
        if isinstance(data['durationMinutes'], bool) or not 1 <= duration <= 240:
            raise ValidationError({'durationMinutes': 'Duration must be between 1 and 240 minutes.'})
        changes['duration_minutes'] = duration
    elif plan is None:
        changes['duration_minutes'] = 40

    for input_name, (model_name, required) in LESSON_PLAN_TEXT_FIELDS.items():
        if input_name not in data:
            if plan is None:
                changes[model_name] = ''
            continue
        value = data[input_name]
        if not isinstance(value, str):
            raise ValidationError({input_name: 'Enter text.'})
        value = value.strip()
        if required and not value:
            raise ValidationError({input_name: 'This field is required.'})
        if input_name == 'topic' and len(value) > 200:
            raise ValidationError({input_name: 'Topic must be 200 characters or fewer.'})
        if len(value) > 10000:
            raise ValidationError({input_name: 'Keep this field under 10,000 characters.'})
        changes[model_name] = value

    if plan is None:
        session = academic_service.current_session(school) or academic_service.ensure_session(school)
        changes.update({
            'school': school,
            'academic_session': session,
            'term': school.current_term,
            'created_by': request.user,
        })
    return changes


class LessonPlanListCreateView(APIView):
    permission_classes = [IsAuthenticated, HasSchool]

    def get(self, request):
        if not has_permission(request.user.role, 'lessonplans.read'):
            raise PermissionDenied('You do not have permission to read lesson plans.')
        plans = (
            LessonPlan.objects.filter(school_id=request.user.school_id)
            .select_related('class_obj', 'academic_session')
        )
        return Response([_lesson_plan_payload(plan) for plan in plans])

    def post(self, request):
        if not has_permission(request.user.role, 'lessonplans.write'):
            raise PermissionDenied('You do not have permission to write lesson plans.')
        school = request.user.school
        plan = LessonPlan.objects.create(**_lesson_plan_changes(request, school))
        log_audit(
            request, 'lesson_plan.created', target=plan.topic,
            entity='lesson_plan', entity_id=str(plan.pk),
            after={'className': plan.class_obj.name, 'subject': plan.subject},
        )
        return Response(_lesson_plan_payload(plan), status=status.HTTP_201_CREATED)


class LessonPlanDetailView(APIView):
    permission_classes = [IsAuthenticated, HasSchool]

    def _get_plan(self, request, pk):
        return get_object_or_404(
            LessonPlan.objects.select_related('class_obj', 'academic_session'),
            pk=pk, school_id=request.user.school_id,
        )

    def get(self, request, pk):
        if not has_permission(request.user.role, 'lessonplans.read'):
            raise PermissionDenied('You do not have permission to read lesson plans.')
        return Response(_lesson_plan_payload(self._get_plan(request, pk)))

    def patch(self, request, pk):
        if not has_permission(request.user.role, 'lessonplans.write'):
            raise PermissionDenied('You do not have permission to write lesson plans.')
        plan = self._get_plan(request, pk)
        changes = _lesson_plan_changes(request, request.user.school, plan)
        for key, value in changes.items():
            setattr(plan, key, value)
        plan.save(update_fields=[*changes.keys(), 'updated_at'])
        log_audit(
            request, 'lesson_plan.updated', target=plan.topic,
            entity='lesson_plan', entity_id=str(plan.pk),
            after={'className': plan.class_obj.name, 'subject': plan.subject},
        )
        return Response(_lesson_plan_payload(plan))

    def delete(self, request, pk):
        if not has_permission(request.user.role, 'lessonplans.write'):
            raise PermissionDenied('You do not have permission to delete lesson plans.')
        plan = self._get_plan(request, pk)
        topic = plan.topic
        plan.delete()
        log_audit(
            request, 'lesson_plan.deleted', target=topic,
            entity='lesson_plan', entity_id=str(pk), before={'topic': topic},
        )
        return Response(status=status.HTTP_204_NO_CONTENT)


# ── Promotion centre ──────────────────────────────────────────────────────

def _promotion_policy_payload(policy):
    return {
        'promoteMinAverage': float(policy.promote_min_average),
        'promoteMinAttendance': float(policy.promote_min_attendance),
        'conditionalMinAverage': float(policy.conditional_min_average),
        'conditionalMinAttendance': float(policy.conditional_min_attendance),
        'conditionalMaxFailedSubjects': policy.conditional_max_failed_subjects,
    }


def _promotion_context(school):
    source = academic_service.current_session(school) or academic_service.ensure_session(school)
    policy = promotion_service.policy_for(school)
    return source, policy


class PromotionPolicyView(APIView):
    permission_classes = [IsAuthenticated, HasSchool]

    def get(self, request):
        if not has_permission(request.user.role, 'academics.read'):
            raise PermissionDenied('You do not have permission to read promotion policy.')
        _, policy = _promotion_context(request.user.school)
        return Response(_promotion_policy_payload(policy))

    def patch(self, request):
        if not has_permission(request.user.role, 'academics.write'):
            raise PermissionDenied('You do not have permission to change promotion policy.')
        _, policy = _promotion_context(request.user.school)
        fields = {
            'promoteMinAverage': ('promote_min_average', Decimal),
            'promoteMinAttendance': ('promote_min_attendance', Decimal),
            'conditionalMinAverage': ('conditional_min_average', Decimal),
            'conditionalMinAttendance': ('conditional_min_attendance', Decimal),
            'conditionalMaxFailedSubjects': ('conditional_max_failed_subjects', int),
        }
        unknown = set(request.data) - set(fields)
        if unknown:
            raise ValidationError({'detail': f'Unknown policy fields: {", ".join(sorted(unknown))}.'})
        changes = {}
        for input_name, (model_name, convert) in fields.items():
            if input_name not in request.data:
                continue
            raw = request.data[input_name]
            try:
                value = convert(str(raw)) if convert is Decimal else convert(raw)
            except (TypeError, ValueError, InvalidOperation):
                raise ValidationError({input_name: 'Enter a valid numeric value.'})
            if isinstance(raw, bool):
                raise ValidationError({input_name: 'Enter a valid numeric value.'})
            if convert is Decimal and (value < 0 or value > 100):
                raise ValidationError({input_name: 'Enter a percentage from 0 to 100.'})
            if convert is int and (str(raw) != str(value) or value < 0 or value > 20):
                raise ValidationError({input_name: 'Enter a whole number from 0 to 20.'})
            changes[model_name] = value
        if not changes:
            raise ValidationError({'detail': 'Provide at least one policy setting.'})
        values = {
            model_name: getattr(policy, model_name)
            for model_name, _ in fields.values()
        }
        values.update(changes)
        if values['conditional_min_average'] > values['promote_min_average']:
            raise ValidationError({
                'conditionalMinAverage': 'The conditional threshold cannot exceed the promotion threshold.',
            })
        if values['conditional_min_attendance'] > values['promote_min_attendance']:
            raise ValidationError({
                'conditionalMinAttendance': 'The conditional threshold cannot exceed the promotion threshold.',
            })
        for field, value in changes.items():
            setattr(policy, field, value)
        policy.save(update_fields=[*changes.keys(), 'updated_at'])
        log_audit(
            request, 'promotion.policy_updated', target=request.user.school.name,
            entity='promotion_policy', entity_id=str(policy.pk),
            after={key: str(value) for key, value in changes.items()},
        )
        return Response(_promotion_policy_payload(policy))


class PromotionClassesView(APIView):
    permission_classes = [IsAuthenticated, HasSchool]

    def get(self, request):
        if not has_permission(request.user.role, 'academics.read'):
            raise PermissionDenied('You do not have permission to review promotion candidates.')
        source, policy = _promotion_context(request.user.school)
        return Response({
            'sourceSession': source.name,
            'targetSession': promotion_service.next_session_name(source),
            'policy': _promotion_policy_payload(policy),
            'classes': promotion_service.class_summaries(request.user.school, source, policy),
        })


class PromotionCandidatesView(APIView):
    permission_classes = [IsAuthenticated, HasSchool]

    def get(self, request, class_name):
        if not has_permission(request.user.role, 'academics.read'):
            raise PermissionDenied('You do not have permission to review promotion candidates.')
        school = request.user.school
        school_class = get_object_or_404(
            SchoolClass.objects.filter(school=school, is_active=True).select_related('level'),
            name=class_name,
        )
        source, policy = _promotion_context(school)
        destination = promotion_service.next_class_for(school_class)
        return Response({
            'className': school_class.name,
            'nextClass': destination.name if destination else None,
            'sourceSession': source.name,
            'targetSession': promotion_service.next_session_name(source),
            'policy': _promotion_policy_payload(policy),
            'candidates': promotion_service.candidates_for(
                school, source, school_class, policy,
            ),
        })


class PromotionApplyView(APIView):
    permission_classes = [IsAuthenticated, HasSchool]

    def post(self, request, class_name):
        if not (
            has_permission(request.user.role, 'students.write')
            and has_permission(request.user.role, 'academics.write')
        ):
            raise PermissionDenied('You do not have permission to apply promotion decisions.')
        school = request.user.school
        school_class = get_object_or_404(
            SchoolClass.objects.filter(school=school, is_active=True).select_related('level'),
            name=class_name,
        )
        source, policy = _promotion_context(school)
        candidates = promotion_service.candidates_for(school, source, school_class, policy)
        candidate_ids = {candidate['studentId'] for candidate in candidates}
        if not candidates:
            raise ValidationError({'decisions': 'There are no active students to process in this class.'})
        decisions = request.data.get('decisions')
        if not isinstance(decisions, dict):
            raise ValidationError({'decisions': 'Send a decision for every active student in the class.'})
        if set(decisions) != candidate_ids:
            raise ValidationError({
                'decisions': 'The class roster changed. Reload the candidates before applying decisions.',
            })
        invalid = {
            student_id: decision for student_id, decision in decisions.items()
            if not isinstance(decision, str) or decision not in promotion_service.DECISIONS
        }
        if invalid:
            raise ValidationError({'decisions': 'Choose a valid promotion decision for every student.'})

        destination_name = promotion_service.next_session_name(source)
        destination_start, destination_end = academic_service.parse_session_name(destination_name)
        destination_class = promotion_service.next_class_for(school_class)
        result = {
            'className': school_class.name,
            'sourceSession': source.name,
            'targetSession': destination_name,
            'promoted': 0,
            'conditional': 0,
            'repeated': 0,
            'underReview': 0,
            'graduated': 0,
        }
        with transaction.atomic():
            active_enrollments = list(
                Enrollment.objects.select_for_update().filter(
                    school=school,
                    academic_session=source,
                    class_obj=school_class,
                    status=Enrollment.Status.ACTIVE,
                    student__status=Student.Status.ACTIVE,
                ).select_related('student', 'section')
            )
            current_ids = {str(row.student_id) for row in active_enrollments}
            if current_ids != candidate_ids:
                raise ValidationError({
                    'decisions': 'The class roster changed. Reload the candidates before applying decisions.',
                })
            needs_destination = any(
                decision != 'review'
                and not (decision == 'promote' and destination_class is None)
                for decision in decisions.values()
            )
            target = None
            if needs_destination:
                target, _ = AcademicSession.objects.get_or_create(
                    school=school,
                    name=destination_name,
                    defaults={
                        'start_year': destination_start,
                        'end_year': destination_end,
                        'is_active': True,
                    },
                )
                if not target.is_active:
                    raise ValidationError({'targetSession': 'The next academic session is inactive.'})
            moving_ids = [
                row.student_id for row in active_enrollments
                if decisions[str(row.student_id)] != 'review'
                and not (
                    decisions[str(row.student_id)] == 'promote'
                    and destination_class is None
                )
            ]
            existing_target = (
                Enrollment.objects.filter(
                    school=school,
                    academic_session=target,
                    student_id__in=moving_ids,
                    status=Enrollment.Status.ACTIVE,
                ).exists()
                if target is not None else False
            )
            if existing_target:
                raise ValidationError({
                    'targetSession': 'Some students already have an active enrolment in the next session.',
                })

            candidate_by_id = {candidate['studentId']: candidate for candidate in candidates}
            for previous in active_enrollments:
                student = previous.student
                decision = decisions[str(student.pk)]
                student_summary = candidate_by_id[str(student.pk)]
                if decision == 'review':
                    result['underReview'] += 1
                    log_audit(
                        request, 'student.promotion_reviewed', target=student.admission_number,
                        entity='student', entity_id=str(student.pk),
                        after={'decision': 'review', 'session': source.name},
                    )
                    continue

                if decision == 'promote' and destination_class is None:
                    previous.status = Enrollment.Status.COMPLETED
                    previous.review_note = ''
                    previous.save(update_fields=['status', 'review_note', 'updated_at'])
                    student.status = Student.Status.GRADUATED
                    student.save(update_fields=['status', 'updated_at'])
                    result['graduated'] += 1
                    log_audit(
                        request, 'student.graduated', target=student.admission_number,
                        detail=f'Graduated after {source.name}.',
                        entity='student', entity_id=str(student.pk),
                        before={'className': school_class.name, 'session': source.name},
                        after={'status': Student.Status.GRADUATED, 'session': destination_name},
                    )
                    continue

                if decision in ('promote', 'conditional'):
                    if destination_class is None:
                        raise ValidationError({
                            'decisions': 'Students in the final class can only graduate, repeat or be reviewed.',
                        })
                    target_class = destination_class
                    result['promoted' if decision == 'promote' else 'conditional'] += 1
                else:
                    target_class = school_class
                    result['repeated'] += 1

                section = None
                if previous.section_id:
                    if target_class.pk == school_class.pk:
                        section = previous.section
                    else:
                        section = target_class.sections.filter(
                            is_active=True, name=previous.section.name,
                        ).first()
                promoted = enrollment_service.promote_student(
                    student,
                    from_session=source,
                    to_session=target,
                    class_obj=target_class,
                    section=section,
                    actor=request.user,
                )
                if decision == 'conditional':
                    promoted.review_note = (
                        f'Promoted with conditions: average {student_summary["average"]}%, '
                        f'attendance {student_summary["attendanceRate"]}%, '
                        f'{student_summary["failedSubjects"]} failed subject(s).'
                    )[:255]
                    promoted.save(update_fields=['review_note', 'updated_at'])
                log_audit(
                    request, 'student.promoted', target=student.admission_number,
                    detail=f'{source.name} {school_class.name} -> {target.name} {target_class.name}',
                    entity='student', entity_id=str(student.pk),
                    before={'className': school_class.name, 'session': source.name},
                    after={
                        'decision': decision,
                        'className': target_class.name,
                        'session': target.name,
                        'reviewNote': promoted.review_note,
                    },
                )
        return Response(result)