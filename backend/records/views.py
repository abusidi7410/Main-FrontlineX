from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework import status
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
    permission_classes = [IsAuthenticated, HasSchool]

    def get(self, request):
        qs = Invoice.objects.filter(school_id=request.user.school_id)
        search = request.query_params.get('search', '').strip()
        if search:
            qs = qs.filter(
                student__first_name__icontains=search,
            ) | qs.filter(student__last_name__icontains=search) | qs.filter(
                student__admission_number__icontains=search,
            )
        return Response(InvoiceSerializer(qs, many=True).data)


class PaymentListView(APIView):
    permission_classes = [IsAuthenticated, HasSchool]

    def get(self, request):
        qs = Payment.objects.filter(school_id=request.user.school_id)
        return Response(PaymentSerializer(qs, many=True).data)

    def post(self, request):
        amount = request.data.get('amount')
        invoice = get_object_or_404(Invoice, id=request.data.get('invoiceId'), school_id=request.user.school_id)
        import uuid
        payment = Payment.objects.create(
            school_id=request.user.school_id,
            invoice=invoice,
            amount=amount,
            method=request.data.get('method', Payment.Method.CASH),
            status=Payment.Status.PENDING,
            reference=request.data.get('reference') or f'FN-{uuid.uuid4().hex[:10].upper()}',
            note=request.data.get('note', ''),
            recorded_by=request.user if request.user.school_id else None,
        )
        return Response(PaymentSerializer(payment).data, status=status.HTTP_201_CREATED)


class PaymentVerifyView(APIView):
    permission_classes = [IsAuthenticated, HasSchool]

    def post(self, request, pk):
        payment = get_object_or_404(Payment, id=pk, school_id=request.user.school_id)
        payment.status = Payment.Status.VERIFIED
        payment.invoice.paid += payment.amount
        payment.invoice.save(update_fields=['paid'])
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
        qs = Student.objects.filter(school_id=request.user.school_id, status=Student.Status.ACTIVE)
        if class_name:
            qs = qs.filter(class_name=class_name)
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
        return Response(data)


class AttendanceSubmitView(APIView):
    permission_classes = [IsAuthenticated, HasSchool, CanWriteRecords]

    def post(self, request):
        serializer = AttendanceSubmitSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        roster = {
            s.id: s
            for s in Student.objects.filter(
                school_id=request.user.school_id,
                class_name=data['className'],
                status=Student.Status.ACTIVE,
            )
        }
        created_ids = []
        with transaction.atomic():
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