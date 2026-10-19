from rest_framework import serializers

from .models import AttendanceRecord, Invoice, Payment, StaffMember, Student
from .services import attendance_rate


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
    # Raw counts travel with the rate so a client can build a *class* or
    # *school* average by summing counts and dividing once. Averaging
    # already-rounded percentages over-weights a pupil with one recorded day as
    # heavily as one with forty.
    attendanceRecorded = serializers.SerializerMethodField()
    attendanceAttended = serializers.SerializerMethodField()
    attendanceExcused = serializers.SerializerMethodField()
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
            'attendanceRecorded', 'attendanceAttended', 'attendanceExcused',
        ]
        fields = [
            'id', 'admissionNumber', 'firstName', 'lastName', 'gender', 'dateOfBirth',
            'className', 'arm', 'status', 'guardianName', 'guardianPhone', 'photoUrl',
            'transferredTo', 'attendanceRate', 'average', 'outstandingFees', 'enrollmentHistory',
            'attendanceRecorded', 'attendanceAttended', 'attendanceExcused',
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
            instance = getattr(self, 'instance', None)
            if (
                instance is not None
                and request.method in ('PUT', 'PATCH')
                and instance.admission_number
            ):
                incoming = attrs.get('admission_number')
                if incoming is not None and str(incoming).strip() != instance.admission_number:
                    raise serializers.ValidationError({
                        'admissionNumber': (
                            'Admission numbers are issued once and cannot be changed.'
                        ),
                    })
        return attrs

    def get_id(self, obj):
        return str(obj.public_id)

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

    def _attendance_counts(self, obj):
        """Raw register counts for this student.

        Prefers the queryset-level annotations built by
        `Student.objects.for_roster()` so a page of students costs one query
        rather than several per student. Falls back to per-student queries only
        when the caller used a plain queryset.
        """
        cached_total = getattr(obj, 'attendance_total', None)
        if cached_total is not None:
            return {
                'recorded': cached_total or 0,
                'present': getattr(obj, 'attendance_present', 0) or 0,
                'excused': getattr(obj, 'attendance_excused', 0) or 0,
            }
        records = obj.attendance.all()
        return {
            'recorded': records.count(),
            'present': records.filter(
                status__in=attendance_rate.ATTENDED_STATUSES,
            ).count(),
            'excused': records.filter(
                status=AttendanceRecord.Status.EXCUSED,
            ).count(),
        }

    def get_attendanceRate(self, obj):
        # One formula, one place — the same service the parent portal, report
        # card and promotion engine use. It was four different expressions of
        # the same idea, and they disagreed.
        rate = attendance_rate.rate_from_counts(self._attendance_counts(obj))
        # A pupil with no register yet has no rate; the list renders "—".
        return 0 if rate is None else rate

    def get_attendanceRecorded(self, obj):
        return self._attendance_counts(obj)['recorded']

    def get_attendanceAttended(self, obj):
        return self._attendance_counts(obj)['present']

    def get_attendanceExcused(self, obj):
        return self._attendance_counts(obj)['excused']

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
                'reviewNote': item.review_note,
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
        return str(obj.public_id)


class InvoiceSerializer(serializers.ModelSerializer):
    id = serializers.SerializerMethodField()
    studentId = serializers.SerializerMethodField()
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

    def get_studentId(self, obj):
        return str(obj.student.public_id)

    def get_studentName(self, obj):
        return f'{obj.student.first_name} {obj.student.last_name}'

    def get_className(self, obj):
        return obj.student.class_name


class PaymentSerializer(serializers.ModelSerializer):
    id = serializers.SerializerMethodField()
    invoiceId = serializers.CharField(source='invoice_id')
    studentName = serializers.SerializerMethodField()
    admissionNumber = serializers.SerializerMethodField()
    invoiceTotal = serializers.SerializerMethodField()
    invoicePaid = serializers.SerializerMethodField()
    recordedBy = serializers.SerializerMethodField()
    createdAt = serializers.DateTimeField(source='created_at', format='%Y-%m-%dT%H:%M:%S')

    class Meta:
        model = Payment
        fields = [
            'id', 'invoiceId', 'studentName', 'admissionNumber', 'amount', 'method',
            'status', 'reference', 'recordedBy', 'createdAt',
            'invoiceTotal', 'invoicePaid',
        ]
        read_only_fields = ['status']

    def get_id(self, obj):
        return str(obj.id)

    def get_studentName(self, obj):
        return f'{obj.invoice.student.first_name} {obj.invoice.student.last_name}'

    def get_admissionNumber(self, obj):
        return obj.invoice.student.admission_number

    def get_invoiceTotal(self, obj):
        return float(obj.invoice.total)

    def get_invoicePaid(self, obj):
        return float(obj.invoice.paid)

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


class StaffCheckInSerializer(serializers.Serializer):
    """A staff member's own check-in for a school day.

    Coordinates are optional so a device that cannot get a fix still records
    that the person arrived; the service marks such a check-in unverified
    rather than dropping it.
    """

    latitude = serializers.FloatField(required=False, allow_null=True, min_value=-90, max_value=90)
    longitude = serializers.FloatField(
        required=False, allow_null=True, min_value=-180, max_value=180,
    )
    accuracy = serializers.FloatField(required=False, allow_null=True, min_value=0)
    notes = serializers.CharField(required=False, allow_blank=True, max_length=280, default='')
    # Only used by the offline queue: the day the check-in was captured on the
    # device. Omitted for a normal live check-in (the server uses today).
    date = serializers.DateField(required=False)

    def validate(self, data):
        has_lat = data.get('latitude') is not None
        has_lng = data.get('longitude') is not None
        if has_lat != has_lng:
            raise serializers.ValidationError({
                'latitude': 'Provide both latitude and longitude, or neither.',
            })
        return data


class StaffAttendanceReviewSerializer(serializers.Serializer):
    """An administrator's decision on an uncertain staff check-in."""

    decision = serializers.ChoiceField(choices=['approve', 'reject'])
    note = serializers.CharField(required=False, allow_blank=True, max_length=280, default='')


class TeacherClassCheckInSerializer(serializers.Serializer):
    """A teacher checking in to one timetabled lesson.

    Same contract as the daily staff check-in: coordinates optional (no fix
    still records the arrival, marked unverified), both-or-neither enforced.
    Which lesson is identified by `entryId`, and the service proves the lesson
    belongs to this school, this teacher and today before writing anything.
    """

    entryId = serializers.IntegerField(min_value=1)
    latitude = serializers.FloatField(required=False, allow_null=True, min_value=-90, max_value=90)
    longitude = serializers.FloatField(
        required=False, allow_null=True, min_value=-180, max_value=180,
    )
    accuracy = serializers.FloatField(required=False, allow_null=True, min_value=0)

    def validate(self, data):
        has_lat = data.get('latitude') is not None
        has_lng = data.get('longitude') is not None
        if has_lat != has_lng:
            raise serializers.ValidationError({
                'latitude': 'Provide both latitude and longitude, or neither.',
            })
        return data


class TeacherCheckInDecisionSerializer(serializers.Serializer):
    """An administrator's decision on one teacher class check-in.

    `cancel` records that the lesson did not run (the teacher can no longer
    check in); `override` sets a verified/late/unverified state by hand with a
    required reason, mirroring an attendance correction.
    """

    action = serializers.ChoiceField(choices=['cancel', 'override'])
    status = serializers.ChoiceField(required=False, allow_blank=True, choices=[
        'present_verified', 'late_verified', 'unverified',
    ])
    note = serializers.CharField(required=False, allow_blank=True, max_length=280, default='')

    def validate(self, data):
        if data['action'] == 'override' and not data.get('status'):
            raise serializers.ValidationError({
                'status': 'Choose the status to record.',
            })
        if data['action'] == 'override' and not (data.get('note') or '').strip():
            raise serializers.ValidationError({
                'note': 'A reason is required for an override.',
            })
        return data