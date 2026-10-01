from rest_framework import serializers

from .models import AttendanceRecord, Invoice, Payment, StaffMember, Student


class StudentSerializer(serializers.ModelSerializer):
    id = serializers.SerializerMethodField()
    # Optional on input: the server generates the number when the client omits
    # it (the default path). A school that keeps its own historical numbering
    # can still supply one. The database constraint is (school, admission_number),
    # so a duplicate has to be rejected here to return a 400 instead of a 500.
    admissionNumber = serializers.CharField(
        source='admission_number', required=False, allow_blank=True, max_length=30,
    )
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
        # `school` is absent from `fields` and the rest are derived, so no
        # request body can move a student between tenants. Ownership is decided
        # by the view from `request.user.school_id`, never by client input.
        read_only_fields = [
            'transferredTo', 'attendanceRate', 'average',
            'outstandingFees', 'enrollmentHistory',
        ]
        fields = [
            'id', 'admissionNumber', 'firstName', 'lastName', 'gender', 'dateOfBirth',
            'className', 'arm', 'status', 'guardianName', 'guardianPhone', 'photoUrl',
            'transferredTo', 'attendanceRate', 'average', 'outstandingFees', 'enrollmentHistory',
        ]

    def validate(self, attrs):
        """Reject attempts to write tenant or lifecycle fields directly.

        A client-supplied `school` / `schoolId` would be a cross-tenant write
        attempt, so it fails loudly rather than being silently ignored.
        """
        request = self.context.get('request')
        if request is not None:
            school_id = getattr(request.user, 'school_id', None)
            for key in ('school', 'schoolId', 'school_id'):
                if key in request.data:
                    raise serializers.ValidationError({
                        key: 'The school is taken from your account and cannot be set here.',
                    })
            if school_id is None:
                raise serializers.ValidationError(
                    {'detail': 'Your account is not attached to a school.'},
                )
            # Uniqueness must be checked here rather than with a
            # UniqueTogetherValidator: `school` is not a serializer field, so
            # DRF would skip that validator and the IntegrityError would escape
            # the view as a 500 instead of a readable 400.
            number = attrs.get('admission_number')
            if number and request.method in ('POST', 'PUT', 'PATCH'):
                clash = Student.objects.filter(
                    school_id=school_id, admission_number=number,
                )
                instance = getattr(self, 'instance', None)
                if instance is not None:
                    clash = clash.exclude(pk=instance.pk)
                if clash.exists():
                    raise serializers.ValidationError({
                        'admissionNumber': (
                            f'"{number}" is already used by another student in this school.'
                        ),
                    })
        return attrs

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
        # Prefer the queryset-level annotation built by
        # `Student.objects.for_roster()` so a page of students costs one query
        # rather than two per student.
        cached = getattr(obj, 'attendance_total', None)
        if cached is not None:
            present = getattr(obj, 'attendance_present', 0) or 0
            return round((present / cached) * 100, 1) if cached else 0
        records = obj.attendance.all()
        count = records.count()
        if count == 0:
            # No records is not perfect attendance. This used to return 100, so
            # every newly registered student showed a flawless record and the
            # list rendered it green before a single day had been marked.
            return 0
        present = records.filter(status__in=[AttendanceRecord.Status.PRESENT, AttendanceRecord.Status.LATE]).count()
        return round((present / count) * 100, 1)

    def get_average(self, obj):
        return 0

    def get_outstandingFees(self, obj):
        cached = getattr(obj, 'outstanding_total', None)
        if cached is not None:
            return float(cached)
        return float(sum((i.total - i.paid) for i in obj.invoices.all()))

    def get_enrollmentHistory(self, obj):
        # Served from the prefetch when the view provides one, so a student's
        # history is not re-queried per render.
        history = getattr(obj, '_enrollment_history_cache', None)
        if history is None:
            return []
        return [
            {
                'sessionId': str(item.academic_session_id),
                'session': item.academic_session.name,
                'className': item.class_obj.name,
                'arm': item.section.name if item.section_id else '',
                'status': item.status,
                'flaggedForReview': item.flagged_for_review,
            }
            for item in history
        ]


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
    source = serializers.CharField(read_only=True)

    class Meta:
        model = Invoice
        fields = [
            'id', 'studentId', 'studentName', 'className', 'term', 'source',
            'total', 'paid', 'items', 'status',
        ]
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


class AttendanceCorrectionSerializer(serializers.Serializer):
    """One attendance line amended after the register was submitted."""

    recordId = serializers.CharField()
    status = serializers.ChoiceField(choices=AttendanceRecord.Status.choices)
    reason = serializers.CharField(max_length=255)


class AttendanceSubmitSerializer(serializers.Serializer):
    """One whole-class register for one school day.

    There is deliberately no `subject` field: attendance is taken once per school
    day, not once per subject, and a student may only have one record per day.
    """

    className = serializers.CharField()
    date = serializers.DateField()
    arm = serializers.CharField(required=False, allow_blank=True, default='')
    records = serializers.ListField(child=serializers.DictField())

    def validate(self, data):
        student_ids = [r.get('studentId') for r in data.get('records', []) if r.get('studentId')]
        if not student_ids:
            raise serializers.ValidationError({'records': 'At least one attendance record is required.'})
        # Reject an obviously duplicated student in one payload rather than
        # letting it silently collapse into one row.
        if len(student_ids) != len(set(student_ids)):
            raise serializers.ValidationError({
                'records': 'The same student appears more than once in this register.',
            })
        return data