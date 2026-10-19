import uuid

from django.db import models

from schools.models import School


def _default_required_documents():
    return ['birth_certificate', 'passport_photo']


DEFAULT_DECLARATION = (
    'I declare that the information provided on this form is true and complete '
    'to the best of my knowledge. I understand that a false declaration may '
    'lead to the withdrawal of the admission offer.'
)


class AdmissionSettings(models.Model):
    """Per-school admission configuration.

    Created lazily with sensible defaults so a school can start accepting
    applications immediately, then tightened from the Admissions settings
    screen (which documents are mandatory before approval).
    """

    school = models.OneToOneField(
        School, on_delete=models.CASCADE, related_name='admission_settings',
    )
    required_documents = models.JSONField(
        default=_default_required_documents, blank=True,
    )
    referee_required = models.BooleanField(default=False)
    sponsor_enabled = models.BooleanField(default=True)
    require_previous_school_for_transfer = models.BooleanField(default=True)
    declaration_text = models.TextField(default=DEFAULT_DECLARATION, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = 'admission settings'

    def __str__(self):
        return f'Admission settings — {self.school_id}'


class AdmissionApplication(models.Model):
    """A complete admission application, editable while it is a draft.

    The model intentionally keeps the form's sections as flat columns (rather
    than a JSON blob) so the dashboard can search and filter on them, and so a
    rejected/approved application stays a queryable historical record.

    Approval creates a `records.Student` through the existing registration,
    invoice, admission-number and wallet-activation services; this row then
    links to that student and keeps the applicant data as a snapshot of what the
    family actually submitted.
    """

    class Status(models.TextChoices):
        DRAFT = 'draft', 'Draft'
        SUBMITTED = 'submitted', 'Submitted'
        UNDER_REVIEW = 'under_review', 'Under review'
        APPROVED = 'approved', 'Approved'
        REJECTED = 'rejected', 'Rejected'
        WITHDRAWN = 'withdrawn', 'Withdrawn'

    class ApplicantType(models.TextChoices):
        NEW = 'new', 'New applicant'
        TRANSFER = 'transfer', 'Transfer applicant'
        RETURNING = 'returning', 'Returning student'

    class Gender(models.TextChoices):
        MALE = 'male', 'Male'
        FEMALE = 'female', 'Female'

    school = models.ForeignKey(
        School, on_delete=models.CASCADE, related_name='admission_applications',
    )
    public_id = models.UUIDField(
        default=uuid.uuid4, unique=True, editable=False, db_index=True,
    )
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.DRAFT,
    )
    applicant_type = models.CharField(
        max_length=20, choices=ApplicantType.choices, default=ApplicantType.NEW,
    )

    # ── Section A: applicant ────────────────────────────────────────────────
    first_name = models.CharField(max_length=150, blank=True, default='')
    middle_name = models.CharField(max_length=150, blank=True, default='')
    last_name = models.CharField(max_length=150, blank=True, default='')
    gender = models.CharField(
        max_length=10, choices=Gender.choices, blank=True, default='',
    )
    date_of_birth = models.DateField(null=True, blank=True)
    nationality = models.CharField(max_length=100, blank=True, default='Nigerian')
    state_of_origin = models.CharField(max_length=100, blank=True, default='')
    lga_of_origin = models.CharField(max_length=100, blank=True, default='')
    religion = models.CharField(max_length=100, blank=True, default='')

    # ── Section B: class applied for ────────────────────────────────────────
    academic_session = models.ForeignKey(
        'records.AcademicSession', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='admission_applications',
    )
    class_applied = models.ForeignKey(
        'records.SchoolClass', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='admission_applications',
    )
    applied_level_code = models.CharField(max_length=3, blank=True, default='')
    admission_year = models.PositiveIntegerField(null=True, blank=True)

    # ── Section C: parent / guardian ────────────────────────────────────────
    guardian_name = models.CharField(max_length=200, blank=True, default='')
    guardian_relationship = models.CharField(max_length=50, blank=True, default='')
    guardian_phone = models.CharField(max_length=20, blank=True, default='')
    guardian_email = models.EmailField(blank=True, default='')
    guardian_occupation = models.CharField(max_length=120, blank=True, default='')
    guardian_address = models.TextField(blank=True, default='')
    second_guardian_name = models.CharField(max_length=200, blank=True, default='')
    second_guardian_phone = models.CharField(max_length=20, blank=True, default='')

    # ── Section D: health and emergency contact ─────────────────────────────
    blood_group = models.CharField(max_length=10, blank=True, default='')
    allergies = models.CharField(max_length=255, blank=True, default='')
    medical_conditions = models.TextField(blank=True, default='')
    emergency_contact_name = models.CharField(max_length=200, blank=True, default='')
    emergency_contact_phone = models.CharField(max_length=20, blank=True, default='')

    # ── Section E: previous school (transfers) ──────────────────────────────
    previous_school_name = models.CharField(max_length=255, blank=True, default='')
    previous_school_address = models.TextField(blank=True, default='')
    last_class_completed = models.CharField(max_length=50, blank=True, default='')
    reason_for_transfer = models.TextField(blank=True, default='')

    # ── Section F: referee ──────────────────────────────────────────────────
    referee_name = models.CharField(max_length=200, blank=True, default='')
    referee_phone = models.CharField(max_length=20, blank=True, default='')
    referee_address = models.TextField(blank=True, default='')

    # ── Section G: sponsor (optional) ───────────────────────────────────────
    sponsor_name = models.CharField(max_length=200, blank=True, default='')
    sponsor_relationship = models.CharField(max_length=50, blank=True, default='')
    sponsor_phone = models.CharField(max_length=20, blank=True, default='')
    sponsor_email = models.EmailField(blank=True, default='')
    sponsor_address = models.TextField(blank=True, default='')

    # ── Section H: correspondence ───────────────────────────────────────────
    mailing_address = models.TextField(blank=True, default='')

    # ── Section I: declaration ──────────────────────────────────────────────
    declared_by = models.CharField(max_length=200, blank=True, default='')
    declared_at = models.DateTimeField(null=True, blank=True)

    # ── Workflow / tracking ─────────────────────────────────────────────────
    submitted_at = models.DateTimeField(null=True, blank=True)
    reviewed_by = models.ForeignKey(
        'accounts.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='reviewed_admission_applications',
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    decision_reason = models.CharField(max_length=255, blank=True, default='')
    student = models.ForeignKey(
        'records.Student', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='admission_applications',
    )
    admission_number = models.CharField(max_length=30, blank=True, default='')
    duplicate_of = models.ForeignKey(
        'self', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='duplicates',
    )
    created_by = models.ForeignKey(
        'accounts.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='created_admission_applications',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    last_saved_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['school', 'status']),
            models.Index(fields=['school', '-created_at']),
            models.Index(fields=['school', 'last_name', 'first_name']),
        ]

    def __str__(self):
        return f'{self.last_name}, {self.first_name} ({self.status})'

    @property
    def is_editable(self) -> bool:
        return self.status == self.Status.DRAFT

    @property
    def full_name(self) -> str:
        return ' '.join(
            part for part in (self.first_name, self.middle_name, self.last_name) if part
        ).strip()


class AdmissionDocument(models.Model):
    """A private file attached to an application.

    The bytes are *not* a Django ``FileField``: that would place them under
    ``MEDIA_ROOT`` and hand out a public URL. ``storage_key`` is an opaque,
    server-generated path resolved by `admissions.storage` and only ever served
    by the authorised download endpoint.
    """

    class Category(models.TextChoices):
        BIRTH_CERTIFICATE = 'birth_certificate', 'Birth certificate'
        PASSPORT_PHOTO = 'passport_photo', 'Passport photograph'
        PREVIOUS_REPORT = 'previous_report', 'Previous school report'
        TRANSFER_CERTIFICATE = 'transfer_certificate', 'Transfer certificate'
        IMMUNIZATION = 'immunization', 'Immunization record'
        OTHER = 'other', 'Other supporting document'

    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending review'
        VERIFIED = 'verified', 'Verified'
        REJECTED = 'rejected', 'Rejected'

    school = models.ForeignKey(
        School, on_delete=models.CASCADE, related_name='admission_documents',
    )
    public_id = models.UUIDField(
        default=uuid.uuid4, unique=True, editable=False, db_index=True,
    )
    application = models.ForeignKey(
        AdmissionApplication, on_delete=models.CASCADE, null=True, blank=True,
        related_name='documents',
    )
    student = models.ForeignKey(
        'records.Student', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='admission_documents',
    )
    category = models.CharField(max_length=30, choices=Category.choices)
    storage_key = models.CharField(max_length=500, unique=True)
    original_filename = models.CharField(max_length=255)
    content_type = models.CharField(max_length=100)
    size_bytes = models.PositiveIntegerField()
    checksum = models.CharField(max_length=64)
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.PENDING,
    )
    uploaded_by = models.ForeignKey(
        'accounts.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='uploaded_admission_documents',
    )
    uploaded_at = models.DateTimeField(auto_now_add=True)
    reviewed_by = models.ForeignKey(
        'accounts.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='reviewed_admission_documents',
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    review_note = models.CharField(max_length=255, blank=True, default='')

    class Meta:
        ordering = ['-uploaded_at']
        indexes = [
            models.Index(fields=['school', 'application']),
            models.Index(fields=['school', 'status']),
        ]

    def __str__(self):
        return f'{self.get_category_display()} — {self.original_filename}'

    @property
    def extension(self) -> str:
        from .storage import EXTENSION_BY_CONTENT_TYPE

        return EXTENSION_BY_CONTENT_TYPE.get(self.content_type, 'bin')
