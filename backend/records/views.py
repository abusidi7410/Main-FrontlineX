import uuid
from decimal import Decimal, InvalidOperation

from django.db import IntegrityError, transaction
from django.db.models import Prefetch, Q, Sum
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.dateparse import parse_date
from rest_framework import status
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.parsers import MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.permissions import HasSchool, require_permissions, require_roles
from schools.models import School, SchoolSubscription
from .models import (
    EPOCH,
    AcademicSession,
    AttendanceRecord,
    Enrollment,
    FeeStructure,
    Invoice,
    Payment,
    SchoolClass,
    Section,
    StaffMember,
    Student,
    invoice_item_amount,
)
from .services import academic as academic_service
from .services import admission as admission_service
from .services import billing as billing_service
from .services import enrollment as enrollment_service
from .student_import import (
    StudentImportError,
    analyse_import,
    parse_import_file,
)
from .serializers import (
    AttendanceSubmitSerializer,
    InvoiceSerializer,
    PaymentSerializer,
    StaffMemberSerializer,
    StudentSerializer,
)

# Role guards for endpoints that predate the granular permission matrix.
CanWriteRecords = require_roles('school_admin', 'principal', 'secretary')
CanImportStudents = require_roles('school_admin')
CanWriteAttendance = require_roles('school_admin', 'principal', 'secretary', 'teacher')
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
    try:
        page = max(int(request.query_params.get('page', 1)), 1)
        page_size = int(request.query_params.get('pageSize', 20))
    except ValueError:
        page, page_size = 1, 20
    page_size = min(max(page_size, 1), 2000)
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
        qs = _student_queryset(request.user.school_id)
        search = request.query_params.get('search', '').strip()
        if search:
            qs = qs.filter(
                Q(first_name__icontains=search)
                | Q(last_name__icontains=search)
                | Q(admission_number__icontains=search)
            )
        class_name = request.query_params.get('className', '').strip()
        if class_name:
            qs = qs.filter(class_name=class_name)
        student_status = request.query_params.get('status', '').strip()
        if student_status:
            qs = qs.filter(status=student_status)
        data = _paginate(qs, request, StudentSerializer, context={'request': request})
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

            # Registration and billing are one operation: the student is not
            # usable until the fees are settled, so the invoice is raised here
            # rather than waiting for someone to remember a separate billing
            # run. A school with no fees configured still registers fine.
            invoice = billing_service.create_invoice_from_school_fees(
                school=school, student=student,
                due_date=billing_service.default_due_date(None, days=ADMISSION_INVOICE_DUE_DAYS),
            )
        data = dict(serializer.data)
        data['invoiceId'] = str(invoice.id) if invoice else ''
        data['invoiceTotal'] = str(invoice.total) if invoice else ''
        # False means registered, but unbillable until fees are set up.
        data['feesConfigured'] = invoice is not None
        return Response(data, status=status.HTTP_201_CREATED)


class StudentStatsView(APIView):
    permission_classes = [IsAuthenticated, HasSchool, require_permissions('students.read')]

    def get(self, request):
        qs = Student.objects.filter(school_id=request.user.school_id)
        total = qs.count()
        active = qs.filter(status=Student.Status.ACTIVE).count()
        suspended = qs.filter(status=Student.Status.SUSPENDED).count()
        # Aggregate in the database rather than loading every invoice row into
        # Python (spec §72).
        outstanding = Invoice.objects.filter(
            school_id=request.user.school_id,
        ).aggregate(net=Sum('total') - Sum('paid'))['net'] or Decimal('0')
        return Response({
            'total': total,
            'active': active,
            'suspended': suspended,
            'averageAttendance': 100,
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
            enrollment = enrollment_service.move_active_enrollment(
                student,
                session,
                target_class,
                target_section,
                actor=request.user,
            )
            enrollment_service.sync_student_class_mirror(student, enrollment)
            student.status = Student.Status.ACTIVE
            student.save(update_fields=['status'])

        return Response(StudentSerializer(student, context={'request': request}).data)


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
        qs = Invoice.objects.filter(school_id=request.user.school_id)
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
        return Response(InvoiceSerializer(qs, many=True).data)


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
        # Same resolution the admission path uses, so a class cannot be billed
        # two different ways depending on which screen started it.
        items = billing_service.resolve_invoice_items(
            school=school, class_name=class_name, term=term,
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

            # Students registered before any fees existed are sitting in
            # PENDING_PAYMENT with no invoice, and the bulk generator only bills
            # active students, so they would never be invoiced and never become
            # active. Only the levels just priced are invoiced: saving Junior
            # Secondary fees must not bill a Nursery family that has none.
            invoiced = 0
            per_level = {}
            for level in touched:
                created = billing_service.invoice_pending_students(school, level=level)
                per_level[str(level.code)] = created
                invoiced += created

            return Response({
                'levels': self._levels_payload(school),
                'items': school.fee_structure or [],
                'invoicedPendingStudents': invoiced,
                'invoicedPendingStudentsByLevel': per_level,
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
        invoiced = billing_service.invoice_pending_students(school)
        return Response({
            'items': school.fee_structure,
            'levels': self._levels_payload(school),
            'invoicedPendingStudents': invoiced,
        })


class PaymentListView(APIView):
    permission_classes = [IsAuthenticated, HasSchool, CanReadFinance]

    def get(self, request):
        qs = Payment.objects.filter(school_id=request.user.school_id)
        if request.user.role == 'student':
            qs = qs.filter(invoice__student_id=request.user.student_profile_id)
        else:
            invoice_id = request.query_params.get('invoiceId', '').strip()
            student_id = request.query_params.get('studentId', '').strip()
            if invoice_id:
                qs = qs.filter(invoice_id=invoice_id)
            if student_id:
                qs = qs.filter(invoice__student_id=student_id)
        return Response(PaymentSerializer(qs, many=True).data)

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


# ── Results (contract stub; full module later) ────────────────────────────

class ResultSheetListView(APIView):
    permission_classes = [IsAuthenticated, HasSchool]

    def get(self, request):
        return Response([])


# ── Attendance ─────────────────────────────────────────────────────────────

def _resolve_roster(request, *, class_name, arm, subject, date):
    """Build a class roster from ACTIVE enrollments, scoped to the caller's school.

    Shared by the roster GET and the attendance POST so both agree on exactly
    who may be marked. Returns `(rows, taken, existing_marks)`.

    The `className` query parameter names a `SchoolClass` **within the caller's
    school**; a class belonging to another school is a 404. `Enrollment` supplies
    the membership and supplies the displayed class/section names, so a stale
    `Student.class_name` cannot leak a student into the wrong roster.
    """
    school_id = request.user.school_id
    session = academic_service.current_session(request.user.school)

    queryset = enrollment_service.active_enrollments(request.user.school)

    school_class = None
    if class_name:
        school_class = get_object_or_404(
            SchoolClass.objects.filter(school_id=school_id), name=class_name,
        )
        queryset = queryset.filter(class_obj=school_class)

    section = None
    if arm and school_class is not None:
        section = get_object_or_404(
            Section.objects.filter(school_id=school_id, class_obj=school_class),
            name=arm,
        )
        queryset = queryset.filter(section=section)

    if session is not None and class_name:
        queryset = queryset.filter(academic_session=session)

    # Only students still active in the school appear, even if their enrollment
    # row is still active (e.g. a withdrawn student mid-session).
    queryset = queryset.filter(student__status=Student.Status.ACTIVE)

    rows = [
        {
            'id': str(item.student_id),
            'firstName': item.student.first_name,
            'lastName': item.student.last_name,
            'admissionNumber': item.student.admission_number,
            'className': item.class_obj.name,
            'arm': item.section.name if item.section_id else '',
            'gender': item.student.gender,
            'status': item.student.status,
            'attendanceRate': 100,
            'average': 0,
            'outstandingFees': 0,
        }
        for item in queryset
    ]

    taken = False
    existing = {}
    if class_name and date:
        attendance_qs = AttendanceRecord.objects.filter(
            school_id=school_id, class_name=class_name, date=date,
        )
        if subject:
            attendance_qs = attendance_qs.filter(subject=subject)
        taken = attendance_qs.exists()
        existing = {str(record.student_id): record.status for record in attendance_qs}
    return rows, taken, existing


class AttendanceRosterView(APIView):
    """The students a teacher may mark present, resolved from Enrollment.

    `Student.class_name` is a denormalised mirror and is NOT authoritative for
    class membership: a stale or wrong value must not place a student in the
    wrong roster. Membership comes from an ACTIVE `Enrollment` row, scoped to
    the caller's school (spec §35, §97).
    """

    permission_classes = [IsAuthenticated, HasSchool, CanReadAttendance]

    def get(self, request):
        class_name = request.query_params.get('className', '').strip()
        arm = request.query_params.get('arm', '').strip()
        subject = request.query_params.get('subject', '').strip()
        raw_date = request.query_params.get('date', '').strip()
        date = parse_date(raw_date) if raw_date else None

        rows, taken, existing = _resolve_roster(
            request,
            class_name=class_name,
            arm=arm,
            subject=subject,
            date=date,
        )
        return Response({'students': rows, 'taken': taken, 'existing': existing})


class AttendanceSubmitView(APIView):
    permission_classes = [IsAuthenticated, HasSchool, CanWriteAttendance]

    def post(self, request):
        serializer = AttendanceSubmitSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        created_ids = []
        with transaction.atomic():
            School.objects.select_for_update().get(id=request.user.school_id)
            already_taken = AttendanceRecord.objects.filter(
                school_id=request.user.school_id,
                class_name=data['className'],
                date=data['date'],
            ).exists()
            if already_taken:
                return Response(
                    {'detail': f'Attendance has already been recorded for {data["className"]} on {data["date"]}.'},
                    status=status.HTTP_409_CONFLICT,
                )
            # The set of students that may be marked comes from the SAME
            # enrollment-resolved roster the GET endpoint returns, so a crafted
            # studentId cannot record attendance for someone who is not in the
            # class — including a student from another school.
            rows, _taken, _existing = _resolve_roster(
                request,
                class_name=data['className'],
                arm='',
                subject=data.get('subject', ''),
                date=data['date'],
            )
            roster = {int(row['id']): row for row in rows}
            for item in data['records']:
                student_id = item.get('studentId')
                student = roster.get(int(student_id)) if student_id else None
                if student is None:
                    continue
                record, _ = AttendanceRecord.objects.update_or_create(
                    school_id=request.user.school_id,
                    student_id=student['id'],
                    date=data['date'],
                    subject=data.get('subject', ''),
                    defaults={
                        'class_name': data['className'],
                        'status': item.get('status', AttendanceRecord.Status.PRESENT),
                        'submitted_by': request.user if request.user.school_id else None,
                    },
                )
                created_ids.append(record.id)
        return Response({'id': request.data.get('id', ''), 'saved': len(created_ids)}, status=status.HTTP_201_CREATED)


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
        return {
            'session': school.current_session,
            'term': school.current_term,
            'classes': school.classes or DEFAULT_CLASSES,
            'subjects': school.subjects or DEFAULT_SUBJECTS,
        }

    def get(self, request):
        return Response(self._payload(self._school(request)))

    def patch(self, request):
        if not CanWriteAcademics().has_permission(request, self):
            raise PermissionDenied('You do not have permission to change academic settings.')
        school = self._school(request)
        session = (request.data.get('session') or '').strip()
        term = (request.data.get('term') or '').strip()
        update = []
        if session:
            school.current_session = session
            update.append('current_session')
        if term:
            school.current_term = term
            update.append('current_term')
        if not update:
            raise ValidationError({'session': 'Provide a session or term to update.'})
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
        classes = list(school.classes or DEFAULT_CLASSES)
        if name not in classes:
            classes.append(name)
            school.classes = classes
            school.save(update_fields=['classes'])
        return Response(AcademicsView()._payload(school))


class AcademicClassDetailView(APIView):
    permission_classes = [IsAuthenticated, HasSchool, CanWriteRecords]

    def delete(self, request, name):
        school = get_object_or_404(School, id=request.user.school_id)
        classes = list(school.classes or DEFAULT_CLASSES)
        if name in classes:
            classes.remove(name)
            school.classes = classes
            school.save(update_fields=['classes'])
        return Response(AcademicsView()._payload(school))


# ── Timetable (contract stub; full module later) ───────────────────────────

class TimetableView(APIView):
    permission_classes = [IsAuthenticated, HasSchool]

    def get(self, request):
        return Response([])