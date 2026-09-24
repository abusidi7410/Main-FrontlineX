import uuid
from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils.dateparse import parse_date
from rest_framework import status
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.permissions import HasSchool, require_roles
from schools.models import School, SchoolSubscription
from .models import AttendanceRecord, Invoice, Payment, StaffMember, Student
from .serializers import (
    AttendanceSubmitSerializer,
    InvoiceSerializer,
    PaymentSerializer,
    StaffMemberSerializer,
    StudentSerializer,
)

CanWriteRecords = require_roles('school_admin', 'principal', 'secretary')
CanWriteAttendance = require_roles('school_admin', 'principal', 'secretary', 'teacher')
CanReadFinance = require_roles('school_admin', 'principal', 'accountant', 'student')
CanWriteFinance = require_roles('school_admin', 'accountant')
FINANCE_WRITE_ROLES = ('school_admin', 'accountant')
SELF_SERVICE_METHODS = ('card', 'bank_transfer', 'online', 'ussd')


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


# ── Students ───────────────────────────────────────────────────────────────

class StudentListCreateView(APIView):
    permission_classes = [IsAuthenticated, HasSchool]

    def get(self, request):
        qs = Student.objects.filter(school_id=request.user.school_id)
        search = request.query_params.get('search', '').strip()
        if search:
            qs = qs.filter(
                first_name__icontains=search,
            ) | qs.filter(last_name__icontains=search) | qs.filter(
                admission_number__icontains=search,
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
        serializer = StudentSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        serializer.save(school_id=request.user.school_id, status=Student.Status.ACTIVE)
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class StudentStatsView(APIView):
    permission_classes = [IsAuthenticated, HasSchool]

    def get(self, request):
        qs = Student.objects.filter(school_id=request.user.school_id)
        total = qs.count()
        active = qs.filter(status=Student.Status.ACTIVE).count()
        suspended = qs.filter(status=Student.Status.SUSPENDED).count()
        outstanding = float(sum((i.total - i.paid) for i in Invoice.objects.filter(school_id=request.user.school_id)))
        return Response({
            'total': total,
            'active': active,
            'suspended': suspended,
            'averageAttendance': 100,
            'outstandingFees': outstanding,
        })


class StudentDetailView(APIView):
    permission_classes = [IsAuthenticated, HasSchool]

    def get_object(self, request, pk):
        return get_object_or_404(Student, id=pk, school_id=request.user.school_id)

    def get(self, request, pk):
        student = self.get_object(request, pk)
        return Response(StudentSerializer(student, context={'request': request}).data)

    def patch(self, request, pk):
        student = self.get_object(request, pk)
        serializer = StudentSerializer(student, data=request.data, partial=True, context={'request': request})
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)


class StudentTransferView(APIView):
    permission_classes = [IsAuthenticated, HasSchool, CanWriteRecords]

    def post(self, request, pk):
        student = get_object_or_404(Student, id=pk, school_id=request.user.school_id)
        to_school_id = request.data.get('toSchoolId')
        target = get_object_or_404(School, id=to_school_id)
        student.transferred_to = target
        student.transferred_at = __import__('django.utils.timezone', fromlist=['now']).now()
        student.status = Student.Status.TRANSFERRED
        student.save(update_fields=['transferred_to', 'transferred_at', 'status'])
        return Response(StudentSerializer(student, context={'request': request}).data)


class StudentImportView(APIView):
    permission_classes = [IsAuthenticated, HasSchool, CanWriteRecords]

    def post(self, request):
        rows = request.data.get('rows', [])
        created = 0
        existing = set(
            Student.objects.filter(school_id=request.user.school_id).values_list('admission_number', flat=True)
        )
        with transaction.atomic():
            for row in rows:
                number = (row.get('admissionNumber') or '').strip()
                if not number or number in existing:
                    continue
                Student.objects.get_or_create(
                    school_id=request.user.school_id,
                    admission_number=number,
                    defaults={
                        'first_name': row.get('firstName') or '',
                        'last_name': row.get('lastName') or '',
                        'gender': Student.Gender.MALE,
                        'class_name': row.get('className') or '',
                        'guardian_name': '',
                        'guardian_phone': row.get('guardianPhone') or '',
                    },
                )
                existing.add(number)
                created += 1
        return Response({'imported': created})


# ── Staff ──────────────────────────────────────────────────────────────────

class StaffListView(APIView):
    permission_classes = [IsAuthenticated, HasSchool]

    def get(self, request):
        qs = StaffMember.objects.filter(school_id=request.user.school_id)
        return Response(StaffMemberSerializer(qs, many=True).data)

    def post(self, request):
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
        member = self.get_object(request, pk)
        serializer = StaffMemberSerializer(member, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)

    def delete(self, request, pk):
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
        structure = school.fee_structure or []
        items = [it for it in structure if it.get('className', '*') in ('*', class_name)]
        if not items:
            raise ValidationError({
                'className': f'No fee items are set up for {class_name}. Add a fee structure first.',
            })
        total = Decimal(sum(Decimal(it['amount']) for it in items))
        students = Student.objects.filter(
            school_id=school.id, class_name=class_name, status=Student.Status.ACTIVE,
        )
        generated = updated = 0
        with transaction.atomic():
            for student in students.select_for_update():
                invoice = Invoice.objects.filter(
                    school_id=school.id, student_id=student.id, term=term,
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


class FeeStructureView(APIView):
    permission_classes = [IsAuthenticated, HasSchool, CanWriteFinance]

    def _school(self, request):
        return get_object_or_404(School, id=request.user.school_id)

    def get(self, request):
        return Response({'items': self._school(request).fee_structure or []})

    def put(self, request):
        school = self._school(request)
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
        return Response({'items': school.fee_structure})


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
        return Response(PaymentSerializer(payment).data, status=status.HTTP_201_CREATED)


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
                return Response(PaymentSerializer(payment).data)
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
        return Response(PaymentSerializer(payment).data)


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

class AttendanceRosterView(APIView):
    permission_classes = [IsAuthenticated, HasSchool]

    def get(self, request):
        class_name = request.query_params.get('className', '').strip()
        arm = request.query_params.get('arm', '').strip()
        subject = request.query_params.get('subject', '').strip()
        date = parse_date(request.query_params.get('date', '').strip()) if request.query_params.get('date', '').strip() else None
        qs = Student.objects.filter(school_id=request.user.school_id, status=Student.Status.ACTIVE)
        if class_name:
            qs = qs.filter(class_name=class_name)
        if arm:
            qs = qs.filter(arm=arm)
        data = [
            {
                'id': str(s.id),
                'firstName': s.first_name,
                'lastName': s.last_name,
                'admissionNumber': s.admission_number,
                'className': s.class_name,
                'arm': s.arm,
                'gender': s.gender,
                'status': s.status,
                'attendanceRate': 100,
                'average': 0,
                'outstandingFees': 0,
            }
            for s in qs
        ]
        taken = False
        existing = {}
        if class_name and date:
            attendance_qs = AttendanceRecord.objects.filter(
                school_id=request.user.school_id,
                class_name=class_name,
                date=date,
            )
            if subject:
                attendance_qs = attendance_qs.filter(subject=subject)
            taken = attendance_qs.exists()
            existing = {str(record.student_id): record.status for record in attendance_qs}
        return Response({'students': data, 'taken': taken, 'existing': existing})


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
            roster = {
                s.id: s
                for s in Student.objects.filter(
                    school_id=request.user.school_id,
                    class_name=data['className'],
                    status=Student.Status.ACTIVE,
                )
            }
            for item in data['records']:
                student_id = item.get('studentId')
                student = roster.get(int(student_id)) if student_id else None
                if student is None:
                    continue
                record, _ = AttendanceRecord.objects.update_or_create(
                    school_id=request.user.school_id,
                    student=student,
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