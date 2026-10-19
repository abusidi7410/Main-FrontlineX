import datetime

from rest_framework import serializers

from .models import AdmissionApplication, AdmissionDocument, AdmissionSettings
from .services import get_settings, missing_required_documents


def _clean(value):
    return value.strip() if isinstance(value, str) else value


class AdmissionDocumentSerializer(serializers.ModelSerializer):
    id = serializers.SerializerMethodField()
    categoryLabel = serializers.CharField(source='get_category_display', read_only=True)
    originalFilename = serializers.CharField(source='original_filename', read_only=True)
    contentType = serializers.CharField(source='content_type', read_only=True)
    sizeBytes = serializers.IntegerField(source='size_bytes', read_only=True)
    uploadedAt = serializers.DateTimeField(source='uploaded_at', format='%Y-%m-%dT%H:%M:%S')
    uploadedBy = serializers.SerializerMethodField()
    reviewedBy = serializers.SerializerMethodField()
    reviewedAt = serializers.DateTimeField(
        source='reviewed_at', format='%Y-%m-%dT%H:%M:%S', read_only=True,
    )
    reviewNote = serializers.CharField(source='review_note', read_only=True)
    downloadUrl = serializers.SerializerMethodField()
    applicationId = serializers.SerializerMethodField()
    studentId = serializers.SerializerMethodField()

    class Meta:
        model = AdmissionDocument
        fields = [
            'id', 'category', 'categoryLabel', 'originalFilename', 'contentType',
            'sizeBytes', 'status', 'uploadedAt', 'uploadedBy', 'reviewedBy',
            'reviewedAt', 'reviewNote', 'downloadUrl', 'applicationId', 'studentId',
        ]

    def get_id(self, obj):
        return str(obj.public_id)

    def get_uploadedBy(self, obj):
        return obj.uploaded_by.get_full_name() if obj.uploaded_by else ''

    def get_reviewedBy(self, obj):
        return obj.reviewed_by.get_full_name() if obj.reviewed_by else ''

    def get_downloadUrl(self, obj):
        return f'/api/v1/admissions/documents/{obj.public_id}/download/'

    def get_applicationId(self, obj):
        return str(obj.application.public_id) if obj.application_id else None

    def get_studentId(self, obj):
        return str(obj.student.public_id) if obj.student_id else None


class AdmissionApplicationBaseSerializer(serializers.ModelSerializer):
    id = serializers.SerializerMethodField()
    applicantType = serializers.CharField(source='applicant_type', required=False)
    firstName = serializers.CharField(source='first_name', required=False, allow_blank=True)
    middleName = serializers.CharField(
        source='middle_name', required=False, allow_blank=True,
    )
    lastName = serializers.CharField(source='last_name', required=False, allow_blank=True)
    dateOfBirth = serializers.DateField(
        source='date_of_birth', required=False, allow_null=True, format='%Y-%m-%d',
    )
    stateOfOrigin = serializers.CharField(
        source='state_of_origin', required=False, allow_blank=True,
    )
    lgaOfOrigin = serializers.CharField(
        source='lga_of_origin', required=False, allow_blank=True,
    )
    classId = serializers.IntegerField(
        source='class_applied_id', required=False, allow_null=True,
    )
    academicSessionId = serializers.IntegerField(
        source='academic_session_id', required=False, allow_null=True,
    )
    admissionYear = serializers.IntegerField(
        source='admission_year', required=False, allow_null=True,
    )
    guardianName = serializers.CharField(
        source='guardian_name', required=False, allow_blank=True,
    )
    guardianRelationship = serializers.CharField(
        source='guardian_relationship', required=False, allow_blank=True,
    )
    guardianPhone = serializers.CharField(
        source='guardian_phone', required=False, allow_blank=True,
    )
    guardianEmail = serializers.EmailField(
        source='guardian_email', required=False, allow_blank=True,
    )
    guardianOccupation = serializers.CharField(
        source='guardian_occupation', required=False, allow_blank=True,
    )
    guardianAddress = serializers.CharField(
        source='guardian_address', required=False, allow_blank=True,
    )
    secondGuardianName = serializers.CharField(
        source='second_guardian_name', required=False, allow_blank=True,
    )
    secondGuardianPhone = serializers.CharField(
        source='second_guardian_phone', required=False, allow_blank=True,
    )
    bloodGroup = serializers.CharField(
        source='blood_group', required=False, allow_blank=True,
    )
    medicalConditions = serializers.CharField(
        source='medical_conditions', required=False, allow_blank=True,
    )
    emergencyContactName = serializers.CharField(
        source='emergency_contact_name', required=False, allow_blank=True,
    )
    emergencyContactPhone = serializers.CharField(
        source='emergency_contact_phone', required=False, allow_blank=True,
    )
    previousSchoolName = serializers.CharField(
        source='previous_school_name', required=False, allow_blank=True,
    )
    previousSchoolAddress = serializers.CharField(
        source='previous_school_address', required=False, allow_blank=True,
    )
    lastClassCompleted = serializers.CharField(
        source='last_class_completed', required=False, allow_blank=True,
    )
    reasonForTransfer = serializers.CharField(
        source='reason_for_transfer', required=False, allow_blank=True,
    )
    refereeName = serializers.CharField(
        source='referee_name', required=False, allow_blank=True,
    )
    refereePhone = serializers.CharField(
        source='referee_phone', required=False, allow_blank=True,
    )
    refereeAddress = serializers.CharField(
        source='referee_address', required=False, allow_blank=True,
    )
    sponsorName = serializers.CharField(
        source='sponsor_name', required=False, allow_blank=True,
    )
    sponsorRelationship = serializers.CharField(
        source='sponsor_relationship', required=False, allow_blank=True,
    )
    sponsorPhone = serializers.CharField(
        source='sponsor_phone', required=False, allow_blank=True,
    )
    sponsorEmail = serializers.EmailField(
        source='sponsor_email', required=False, allow_blank=True,
    )
    sponsorAddress = serializers.CharField(
        source='sponsor_address', required=False, allow_blank=True,
    )
    mailingAddress = serializers.CharField(
        source='mailing_address', required=False, allow_blank=True,
    )
    declaredBy = serializers.CharField(
        source='declared_by', required=False, allow_blank=True,
    )
    declaredAt = serializers.DateTimeField(
        source='declared_at', format='%Y-%m-%dT%H:%M:%S', read_only=True,
    )
    submittedAt = serializers.DateTimeField(
        source='submitted_at', format='%Y-%m-%dT%H:%M:%S', read_only=True,
    )
    reviewedAt = serializers.DateTimeField(
        source='reviewed_at', format='%Y-%m-%dT%H:%M:%S', read_only=True,
    )
    decisionReason = serializers.CharField(source='decision_reason', read_only=True)
    admissionNumber = serializers.CharField(source='admission_number', read_only=True)
    studentId = serializers.SerializerMethodField()
    className = serializers.SerializerMethodField()
    levelCode = serializers.CharField(source='applied_level_code', read_only=True)
    academicSession = serializers.SerializerMethodField()
    reviewedBy = serializers.SerializerMethodField()
    createdBy = serializers.SerializerMethodField()
    createdAt = serializers.DateTimeField(
        source='created_at', format='%Y-%m-%dT%H:%M:%S', read_only=True,
    )
    lastSavedAt = serializers.DateTimeField(
        source='last_saved_at', format='%Y-%m-%dT%H:%M:%S', read_only=True,
    )
    duplicateOf = serializers.SerializerMethodField()
    requiredDocuments = serializers.SerializerMethodField()
    missingDocuments = serializers.SerializerMethodField()

    class Meta:
        model = AdmissionApplication
        fields = [
            'id', 'status', 'applicantType',
            'firstName', 'middleName', 'lastName', 'gender', 'dateOfBirth',
            'nationality', 'stateOfOrigin', 'lgaOfOrigin', 'religion',
            'classId', 'className', 'levelCode', 'academicSessionId',
            'academicSession', 'admissionYear',
            'guardianName', 'guardianRelationship', 'guardianPhone', 'guardianEmail',
            'guardianOccupation', 'guardianAddress', 'secondGuardianName',
            'secondGuardianPhone',
            'bloodGroup', 'allergies', 'medicalConditions',
            'emergencyContactName', 'emergencyContactPhone',
            'previousSchoolName', 'previousSchoolAddress', 'lastClassCompleted',
            'reasonForTransfer',
            'refereeName', 'refereePhone', 'refereeAddress',
            'sponsorName', 'sponsorRelationship', 'sponsorPhone', 'sponsorEmail',
            'sponsorAddress',
            'mailingAddress', 'declaredBy', 'declaredAt', 'submittedAt',
            'reviewedBy', 'reviewedAt', 'decisionReason',
            'admissionNumber', 'studentId', 'duplicateOf',
            'requiredDocuments', 'missingDocuments',
            'createdBy', 'createdAt', 'lastSavedAt',
        ]
        read_only_fields = [
            'status', 'declaredAt', 'submittedAt', 'reviewedBy', 'reviewedAt',
            'decisionReason', 'admissionNumber', 'studentId', 'duplicateOf',
            'requiredDocuments', 'missingDocuments',
        ]

    def get_id(self, obj):
        return str(obj.public_id)

    def get_studentId(self, obj):
        return str(obj.student.public_id) if obj.student_id else None

    def get_className(self, obj):
        return obj.class_applied.name if obj.class_applied_id else ''

    def get_academicSession(self, obj):
        return obj.academic_session.name if obj.academic_session_id else ''

    def get_reviewedBy(self, obj):
        return obj.reviewed_by.get_full_name() if obj.reviewed_by else ''

    def get_createdBy(self, obj):
        return obj.created_by.get_full_name() if obj.created_by else ''

    def get_duplicateOf(self, obj):
        return str(obj.duplicate_of.public_id) if obj.duplicate_of_id else None

    def get_requiredDocuments(self, obj):
        return list(get_settings(obj.school).required_documents or [])

    def get_missingDocuments(self, obj):
        return missing_required_documents(obj)

    def validate_dateOfBirth(self, value):
        if value is not None and value > datetime.date.today():
            raise serializers.ValidationError('Date of birth cannot be in the future.')
        return value

    def validate_admissionYear(self, value):
        if value is not None and not 1900 <= value <= 2100:
            raise serializers.ValidationError('Enter a valid admission year.')
        return value

    def validate_classId(self, value):
        request = self.context.get('request')
        school_id = getattr(getattr(request, 'user', None), 'school_id', None)
        if value in (None, ''):
            return None
        from records.models import SchoolClass

        if not SchoolClass.objects.filter(pk=value, school_id=school_id).exists():
            raise serializers.ValidationError('Select a class that belongs to your school.')
        return value

    def validate_academicSessionId(self, value):
        request = self.context.get('request')
        school_id = getattr(getattr(request, 'user', None), 'school_id', None)
        if value in (None, ''):
            return None
        from records.models import AcademicSession

        if not AcademicSession.objects.filter(pk=value, school_id=school_id).exists():
            raise serializers.ValidationError('Select a session that belongs to your school.')
        return value

    def validate(self, attrs):
        for field in (
            'first_name', 'middle_name', 'last_name', 'nationality',
            'state_of_origin', 'lga_of_origin', 'religion', 'guardian_name',
            'guardian_relationship', 'guardian_phone', 'guardian_occupation',
            'guardian_address', 'second_guardian_name', 'second_guardian_phone',
            'blood_group', 'allergies', 'medical_conditions',
            'emergency_contact_name', 'emergency_contact_phone',
            'previous_school_name', 'previous_school_address',
            'last_class_completed', 'reason_for_transfer', 'referee_name',
            'referee_phone', 'referee_address', 'sponsor_name',
            'sponsor_relationship', 'sponsor_phone', 'sponsor_address',
            'mailing_address', 'declared_by',
        ):
            if field in attrs:
                attrs[field] = _clean(attrs[field]) or ''

        if 'guardian_phone' in attrs:
            from accounts.validators import normalize_phone

            attrs['guardian_phone'] = normalize_phone(attrs['guardian_phone'] or '')

        if 'class_applied_id' in attrs:
            class_id = attrs['class_applied_id']
            if class_id:
                from records.models import SchoolClass

                school_class = (
                    SchoolClass.objects.select_related('level').filter(pk=class_id).first()
                )
                attrs['applied_level_code'] = (
                    school_class.level.code if school_class is not None else ''
                )
            else:
                attrs['applied_level_code'] = ''

        return attrs

    def update(self, instance, validated_data):
        # An admission year is only a planning value until approval; once the
        # student exists the application is read-only anyway.
        return super().update(instance, validated_data)


class AdmissionApplicationListSerializer(AdmissionApplicationBaseSerializer):
    class Meta(AdmissionApplicationBaseSerializer.Meta):
        fields = [
            'id', 'status', 'applicantType', 'firstName', 'middleName', 'lastName',
            'gender', 'dateOfBirth', 'classId', 'className', 'levelCode',
            'academicSession', 'guardianName', 'guardianPhone', 'admissionNumber',
            'studentId', 'submittedAt', 'createdAt', 'lastSavedAt',
            'missingDocuments',
        ]
        read_only_fields = fields


class AdmissionApplicationDetailSerializer(AdmissionApplicationBaseSerializer):
    documents = AdmissionDocumentSerializer(many=True, read_only=True)

    class Meta(AdmissionApplicationBaseSerializer.Meta):
        fields = AdmissionApplicationBaseSerializer.Meta.fields + ['documents']
        read_only_fields = AdmissionApplicationBaseSerializer.Meta.read_only_fields


class AdmissionSettingsSerializer(serializers.ModelSerializer):
    requiredDocuments = serializers.ListField(
        source='required_documents',
        child=serializers.ChoiceField(choices=AdmissionDocument.Category.choices),
        required=False,
    )
    refereeRequired = serializers.BooleanField(
        source='referee_required', required=False,
    )
    sponsorEnabled = serializers.BooleanField(source='sponsor_enabled', required=False)
    requirePreviousSchoolForTransfer = serializers.BooleanField(
        source='require_previous_school_for_transfer', required=False,
    )
    declarationText = serializers.CharField(
        source='declaration_text', required=False, allow_blank=True,
    )

    class Meta:
        model = AdmissionSettings
        fields = [
            'requiredDocuments', 'refereeRequired', 'sponsorEnabled',
            'requirePreviousSchoolForTransfer', 'declarationText',
        ]

    def validate_requiredDocuments(self, value):
        return list(dict.fromkeys(value))
