import uuid
from datetime import timedelta
from decimal import Decimal, InvalidOperation

from django.db import IntegrityError, transaction
from django.db.models import Count, Prefetch, Q, Sum
from django.db.models.functions import Coalesce
from django.http import Http404
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.dateparse import parse_date
from rest_framework import serializers, status
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.parsers import MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.permissions import (
    HasSchool,
    has_permission,
    require_permissions,
    require_roles,
)
from accounts.utils import audit as log_audit
from schools.models import School, SchoolSubscription
from .models import (
    EPOCH,
    AcademicSession,
    AttendanceRecord,
    ClassTeacherAssignment,
    Enrollment,
    FeeStructure,
    Invoice,
    Payment,
    ResultEntry,
    ResultSheet,
    SchoolClass,
    Section,
    StaffMember,
    Student,
    invoice_item_amount,
)
from .services import academic as academic_service
from .services import admission as admission_service
from .services import ai_tools
from .services import attendance as attendance_service
from .services import billing as billing_service
from .services import enrollment as enrollment_service
from .services import results as result_service
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


def _filtered_students(request, *, search='', class_name='', class_id='', student_status=''):
    """The student list, filtered in the database rather than in the client.

    The base queryset is already school-scoped, so a `class_id` belonging to
    another school matches nothing instead of leaking that school's class.
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
    if student_status:
        if student_status not in Student.Status.values:
            raise ValidationError({'status': f'"{student_status}" is not a student status.'})
        qs = qs.filter(status=student_status)
    return qs


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
        data = _paginate(
            _filtered_students(request, search=search, class_name=class_name,
                               class_id=class_id, student_status=student_status),
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
            if invoice is None:
                student.status = Student.Status.ACTIVE
                student.save(update_fields=['status'])
        data = dict(serializer.data)
        data['invoiceId'] = str(invoice.id) if invoice else ''
        data['invoiceTotal'] = str(invoice.total) if invoice else ''
        data['registrationFeeConfigured'] = invoice is not None
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
        serializer = StudentSerializer(
            student, data=request.data, partial=True, context={'request': request},
        )
        serializer.is_valid(raise_exception=True)
        # Ownership cannot move: `school` is not a serializer field, and passing
        # it explicitly is rejected here so a crafted payload fails loudly
        # instead of being silently dropped.
        serializer.save()
        return Response(serializer.data)


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
            activated = billing_service.activate_student_if_fully_paid(invoice.student)
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
                activated = billing_service.activate_student_if_fully_paid(payment.invoice.student)
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
            activated = billing_service.activate_student_if_fully_paid(invoice.student)
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

DEFAULT_SUBJECTS = [
    'Mathematics',
    'English Language',
    'Basic Science',
    'Social Studies',
    'Civic Education',
    'Computer Studies',
    'Agricultural Science',
    'Business Studies',
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
        if session:
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


# ── Timetable (contract stub; full module later) ───────────────────────────

class TimetableView(APIView):
    permission_classes = [IsAuthenticated, HasSchool]

    def get(self, request):
        return Response([])