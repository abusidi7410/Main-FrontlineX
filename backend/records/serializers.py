from rest_framework import serializers

from .models import AttendanceRecord, Invoice, Payment, StaffMember, Student


class StudentSerializer(serializers.ModelSerializer):
    id = serializers.SerializerMethodField()
    admissionNumber = serializers.CharField(source='admission_number')
    firstName = serializers.CharField(source='first_name')
    lastName = serializers.CharField(source='last_name')
    dateOfBirth = serializers.DateField(source='date_of_birth', format='%Y-%m-%d', required=False)
    className = serializers.CharField(source='class_name')
    guardianName = serializers.CharField(source='guardian_name')
    guardianPhone = serializers.CharField(source='guardian_phone')
    photoUrl = serializers.SerializerMethodField()
    transferredTo = serializers.SerializerMethodField()
    attendanceRate = serializers.SerializerMethodField()
    average = serializers.SerializerMethodField()
    outstandingFees = serializers.SerializerMethodField()
    enrollmentHistory = serializers.SerializerMethodField()

    class Meta:
        model = Student
        read_only_fields = ['transferredTo', 'attendanceRate', 'average', 'outstandingFees', 'enrollmentHistory']
        fields = [
            'id', 'admissionNumber', 'firstName', 'lastName', 'gender', 'dateOfBirth',
            'className', 'arm', 'status', 'guardianName', 'guardianPhone', 'photoUrl',
            'transferredTo', 'attendanceRate', 'average', 'outstandingFees', 'enrollmentHistory',
        ]

    def get_id(self, obj):
        return str(obj.id)

    def get_photoUrl(self, obj):
        if not obj.photo:
            return None
        request = self.context.get('request')
        url = obj.photo.url
        return request.build_absolute_uri(url) if request else url

    def get_transferredTo(self, obj):
        if not obj.transferred_to_id:
            return None
        return {
            'schoolId': str(obj.transferred_to_id),
            'schoolName': obj.transferred_to.name,
            'transferredAt': obj.transferred_at.isoformat() if obj.transferred_at else None,
        }

    def get_attendanceRate(self, obj):
        records = obj.attendance.all()
        count = records.count()
        if count == 0:
            return 100
        present = records.filter(status__in=[AttendanceRecord.Status.PRESENT, AttendanceRecord.Status.LATE]).count()
        return round((present / count) * 100, 1)

    def get_average(self, obj):
        return 0

    def get_outstandingFees(self, obj):
        return float(sum((i.total - i.paid) for i in obj.invoices.all()))

    def get_enrollmentHistory(self, obj):
        return []


class StaffMemberSerializer(serializers.ModelSerializer):
    id = serializers.SerializerMethodField()
    fullName = serializers.CharField(source='full_name')

    class Meta:
        model = StaffMember
        fields = ['id', 'fullName', 'email', 'phone', 'role', 'subjects', 'classes', 'status']

    def get_id(self, obj):
        return str(obj.id)


class InvoiceSerializer(serializers.ModelSerializer):
    id = serializers.SerializerMethodField()
    studentId = serializers.CharField(source='student_id')
    studentName = serializers.SerializerMethodField()
    className = serializers.SerializerMethodField()

    class Meta:
        model = Invoice
        fields = ['id', 'studentId', 'studentName', 'className', 'term', 'total', 'paid', 'items', 'status']
        read_only_fields = ['status']

    def get_id(self, obj):
        return str(obj.id)

    def get_studentName(self, obj):
        return f'{obj.student.first_name} {obj.student.last_name}'

    def get_className(self, obj):
        return obj.student.class_name


class PaymentSerializer(serializers.ModelSerializer):
    id = serializers.SerializerMethodField()
    invoiceId = serializers.CharField(source='invoice_id')
    studentName = serializers.SerializerMethodField()
    recordedBy = serializers.SerializerMethodField()
    createdAt = serializers.DateTimeField(source='created_at', format='%Y-%m-%dT%H:%M:%S')

    class Meta:
        model = Payment
        fields = ['id', 'invoiceId', 'studentName', 'amount', 'method', 'status', 'reference', 'recordedBy', 'createdAt']
        read_only_fields = ['status']

    def get_id(self, obj):
        return str(obj.id)

    def get_studentName(self, obj):
        return f'{obj.invoice.student.first_name} {obj.invoice.student.last_name}'

    def get_recordedBy(self, obj):
        return obj.recorded_by.get_full_name() if obj.recorded_by else ''


class AttendanceSubmitSerializer(serializers.Serializer):
    className = serializers.CharField()
    date = serializers.DateField()
    subject = serializers.CharField(required=False, allow_blank=True, default='')
    records = serializers.ListField(child=serializers.DictField())

    def validate(self, data):
        student_ids = [r.get('studentId') for r in data.get('records', []) if r.get('studentId')]
        if not student_ids:
            raise serializers.ValidationError({'records': 'At least one attendance record is required.'})
        return data