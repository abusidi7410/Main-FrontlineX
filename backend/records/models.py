import datetime
from decimal import Decimal

from django.db import models
from django.db.models import Q

from schools.models import School

# Sentinel "effective from" for fee rows that apply to the whole session. Using a
# real date instead of NULL keeps the conflicting-definition constraint effective
# on both PostgreSQL and SQLite (NULLs compare distinct, so a NULL column would
# silently defeat the uniqueness guarantee in spec §6/§86).
EPOCH = datetime.date(1970, 1, 1)


class Level(models.Model):
    """Explicit school level — the authoritative source of the admission-number
    segment (spec §21).

    Class names must never be parsed to infer a level; a class points at its
    level and the level carries the code.
    """

    NURSERY = 'NUR'
    PRIMARY = 'PRI'
    JUNIOR_SECONDARY = 'JSS'
    SENIOR_SECONDARY = 'SSS'

    CODE_CHOICES = [
        (NURSERY, 'NUR — Nursery'),
        (PRIMARY, 'PRI — Primary'),
        (JUNIOR_SECONDARY, 'JSS — Junior Secondary'),
        (SENIOR_SECONDARY, 'SSS — Senior Secondary'),
    ]

    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name='levels')
    code = models.CharField(max_length=3, choices=CODE_CHOICES)
    name = models.CharField(max_length=50)
    sort_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['sort_order', 'name']
        constraints = [
            models.UniqueConstraint(fields=['school', 'code'], name='unique_level_code_per_school'),
        ]

    def __str__(self):
        return f'{self.code} — {self.name}'


class SchoolClass(models.Model):
    """A class configured by the school (spec §21).

    `Student.class_name` stays as a denormalised mirror of `name` so the
    existing academics / attendance / reports modules keep working; `Enrollment`
    is the source of truth for rosters (spec §35).
    """

    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name='school_classes')
    level = models.ForeignKey(Level, on_delete=models.PROTECT, related_name='classes')
    name = models.CharField(max_length=50)
    sort_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['sort_order', 'name']
        constraints = [
            models.UniqueConstraint(fields=['school', 'name'], name='unique_class_name_per_school'),
        ]
        indexes = [
            models.Index(fields=['school', 'level']),
        ]

    def __str__(self):
        return f'{self.name} ({self.level.code})'


class Section(models.Model):
    """A section/arm inside a class. Mirrors `Student.arm`."""

    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name='sections')
    class_obj = models.ForeignKey(SchoolClass, on_delete=models.CASCADE, related_name='sections')
    name = models.CharField(max_length=5)
    sort_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['sort_order', 'name']
        constraints = [
            models.UniqueConstraint(fields=['class_obj', 'name'], name='unique_section_per_class'),
        ]
        indexes = [
            models.Index(fields=['school', 'class_obj']),
        ]

    def __str__(self):
        return f'{self.class_obj.name} - {self.name}'


class AcademicSession(models.Model):
    """Academic session/year (spec §7).

    `School.current_session` stays the school's convenience pointer; this model
    is the queryable history and the anchor for fees and enrollments.
    """

    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name='sessions')
    name = models.CharField(max_length=20)
    start_year = models.PositiveIntegerField()
    end_year = models.PositiveIntegerField()
    is_current = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-start_year', 'name']
        constraints = [
            models.UniqueConstraint(fields=['school', 'name'], name='unique_session_per_school'),
            models.CheckConstraint(
                condition=Q(end_year__gte=models.F('start_year')),
                name='session_end_year_after_start',
            ),
        ]
        indexes = [
            models.Index(fields=['school', 'is_current']),
        ]

    def __str__(self):
        return self.name


class AdmissionSequence(models.Model):
    """Per school + level + admission year serial counter (spec §23/§24).

    Never derive the next admission number with `max(serial) + 1`: that races
    under concurrent registration. Rows are locked with select_for_update and
    the counter is advanced in place.
    """

    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name='admission_sequences')
    level = models.ForeignKey(Level, on_delete=models.CASCADE, related_name='admission_sequences')
    year = models.PositiveIntegerField()
    last_serial = models.PositiveIntegerField(default=0)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['school', 'level', 'year'], name='unique_admission_sequence',
            ),
        ]

    def __str__(self):
        return f'{self.school_id}/{self.level_id}/{self.year} → {self.last_serial}'


class StudentQuerySet(models.QuerySet):
    """Query helpers for the two hot student list endpoints (spec §72)."""

    def for_roster(self):
        """Annotate attendance counts and outstanding fees for list rendering.

        A page of students previously cost two extra queries each — one to count
        attendance and one to count present days — plus one to sum invoices.
        These annotations fold that work into the page query itself, so listing
        N students stays at a constant number of queries.

        The annotations alias onto attribute names the serializer reads
        directly, and are safe on any queryset.
        """
        from django.db.models import Count, DecimalField, Q, Sum, Value
        from django.db.models.functions import Coalesce

        # `Value(Decimal('0'), DecimalField(...))` keeps the fallback the same
        # type as the sums; a bare `0` would mix DecimalField and IntegerField
        # and Django refuses to guess the output type.
        zero = Value(Decimal('0'), output_field=DecimalField(max_digits=12, decimal_places=2))
        return self.annotate(
            attendance_total=Count('attendance', distinct=True),
            attendance_present=Count(
                'attendance',
                filter=Q(attendance__status__in=['present', 'late']),
                distinct=True,
            ),
            outstanding_total=Coalesce(Sum('invoices__total'), zero)
            - Coalesce(Sum('invoices__paid'), zero),
        )


class Student(models.Model):
    class Gender(models.TextChoices):
        MALE = 'male', 'Male'
        FEMALE = 'female', 'Female'

    class Status(models.TextChoices):
        ACTIVE = 'active', 'Active'
        SUSPENDED = 'suspended', 'Suspended'
        GRADUATED = 'graduated', 'Graduated'
        WITHDRAWN = 'withdrawn', 'Withdrawn'
        TRANSFERRED = 'transferred', 'Transferred'

    class AdmissionNumberSource(models.TextChoices):
        SCHOOL_ASSIGNED = 'school_assigned', 'School assigned'
        SYSTEM_GENERATED = 'system_generated', 'System generated'
        IMPORTED = 'imported', 'Imported'

    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name='students')
    admission_number = models.CharField(max_length=30)
    # Provenance of the identifier (spec §54). Purely informational: it never
    # changes how the number is generated or validated.
    admission_number_source = models.CharField(
        max_length=20, choices=AdmissionNumberSource.choices,
        default=AdmissionNumberSource.SCHOOL_ASSIGNED,
    )
    # Explicit historical admission year. Set from the registering session's
    # start year for new students, or from the school's own records during
    # migration. It is part of the permanent identifier and is never
    # recalculated from today's session (spec §22, §29).
    admission_year = models.PositiveIntegerField(null=True, blank=True)
    admission_date = models.DateField(null=True, blank=True)
    first_name = models.CharField(max_length=150)
    middle_name = models.CharField(max_length=150, blank=True, default='')
    last_name = models.CharField(max_length=150)
    gender = models.CharField(max_length=10, choices=Gender.choices)
    date_of_birth = models.DateField(null=True, blank=True)
    # Denormalised mirrors of the active Enrollment (spec §35): existing
    # academics / attendance / reports modules read these, but a class roster
    # is always built from Enrollment, never from this column.
    class_name = models.CharField(max_length=50)
    arm = models.CharField(max_length=5, blank=True, default='')
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE)
    guardian_name = models.CharField(max_length=200, blank=True, default='')
    guardian_phone = models.CharField(max_length=20, blank=True, default='')
    address = models.TextField(blank=True, default='')
    email = models.EmailField(blank=True, default='')
    photo = models.ImageField(upload_to='students/photos/', null=True, blank=True)
    transferred_to = models.ForeignKey(
        School, on_delete=models.SET_NULL, null=True, blank=True, related_name='incoming_transfers'
    )
    transferred_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['last_name', 'first_name']
        constraints = [
            models.UniqueConstraint(
                fields=['school', 'admission_number'], name='unique_admission_per_school'
            )
        ]
        indexes = [
            # Roster and student-list lookups are always school-scoped.
            models.Index(fields=['school', 'class_name']),
            models.Index(fields=['school', 'status']),
        ]

    objects = StudentQuerySet.as_manager()

    def __str__(self):
        return f'{self.last_name}, {self.first_name} ({self.admission_number})'


class StaffMember(models.Model):
    class Status(models.TextChoices):
        ACTIVE = 'active', 'Active'
        INVITED = 'invited', 'Invited'
        SUSPENDED = 'suspended', 'Suspended'

    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name='staff')
    full_name = models.CharField(max_length=200)
    email = models.EmailField(blank=True, default='')
    phone = models.CharField(max_length=20, blank=True, default='')
    role = models.CharField(max_length=20, default='teacher')
    subjects = models.JSONField(default=list, blank=True)
    classes = models.JSONField(default=list, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['full_name']

    def __str__(self):
        return self.full_name


class AttendanceRecord(models.Model):
    class Status(models.TextChoices):
        PRESENT = 'present', 'Present'
        ABSENT = 'absent', 'Absent'
        LATE = 'late', 'Late'
        EXCUSED = 'excused', 'Excused'

    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name='attendance_records')
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='attendance')
    class_name = models.CharField(max_length=50)
    subject = models.CharField(max_length=100, blank=True, default='')
    date = models.DateField()
    status = models.CharField(max_length=10, choices=Status.choices)
    submitted_by = models.ForeignKey(
        'accounts.User', on_delete=models.SET_NULL, null=True, blank=True
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-date']
        constraints = [
            models.UniqueConstraint(
                fields=['student', 'date', 'subject'], name='unique_attendance_per_student_day'
            )
        ]

    def __str__(self):
        return f'{self.student_id} {self.date} {self.status}'


class FeeStructure(models.Model):
    """Payment Structure — what the school charges (spec §5).

    The administrator configures fees here; invoices are always derived from
    these rows and never typed by hand. Resolution precedence is
    class → level → school/session default (spec §6); a more specific active row
    overrides a less specific one for the same fee type.

    `scope` + `scope_key` are always populated ('*' for the session default,
    otherwise the level/class id) so the conflict constraint below works on
    every database backend. Two rows may not be simultaneously active at the
    exact same scope unless they differ by `effective_from`, which acts as the
    explicit version marker.
    """

    class Scope(models.TextChoices):
        CLASS = 'class', 'Class'
        LEVEL = 'level', 'Level'
        SCHOOL = 'school', 'School / session default'

    class FeeType(models.TextChoices):
        REGISTRATION = 'registration', 'Registration'
        TUITION = 'tuition', 'Tuition'
        DEVELOPMENT = 'development', 'Development'
        ICT = 'ict', 'ICT'
        UNIFORM = 'uniform', 'Uniform'
        EXAM = 'exam', 'Examination'
        TRANSPORT = 'transport', 'Transport'
        MEALS = 'meals', 'Meals'
        OTHER = 'other', 'Other'

    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name='fee_structures')
    academic_session = models.ForeignKey(
        AcademicSession, on_delete=models.CASCADE, related_name='fee_structures',
    )
    # Blank means the fee applies to the whole session (annual / registration),
    # otherwise it is charged only for that term (spec §7).
    term = models.CharField(max_length=50, blank=True, default='')
    scope = models.CharField(max_length=10, choices=Scope.choices, default=Scope.SCHOOL)
    scope_key = models.CharField(max_length=20, default='*')
    level = models.ForeignKey(
        Level, on_delete=models.CASCADE, null=True, blank=True, related_name='fee_structures',
    )
    school_class = models.ForeignKey(
        SchoolClass, on_delete=models.CASCADE, null=True, blank=True, related_name='fee_structures',
    )
    fee_type = models.CharField(max_length=20, choices=FeeType.choices)
    label = models.CharField(max_length=100)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    is_required = models.BooleanField(default=True)
    is_active = models.BooleanField(default=True)
    effective_from = models.DateField(default=EPOCH)
    created_by = models.ForeignKey(
        'accounts.User', on_delete=models.SET_NULL, null=True, blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['scope', 'fee_type']
        constraints = [
            models.UniqueConstraint(
                fields=[
                    'school', 'academic_session', 'term', 'scope', 'scope_key',
                    'fee_type', 'effective_from',
                ],
                name='unique_fee_structure_scope',
            ),
            models.CheckConstraint(
                condition=Q(amount__gt=0), name='fee_structure_amount_positive',
            ),
        ]
        indexes = [
            models.Index(fields=['school', 'academic_session', 'is_active']),
        ]

    def __str__(self):
        return f'{self.label} {self.amount} ({self.scope}:{self.scope_key})'

    def applies_to(self, *, term, school_class, level) -> bool:
        """Whether this row charges a given class in a given term (spec §6/§7).

        A row with a blank `term` is an annual / session-wide fee and applies to
        every term; a row naming a term only applies to that term. Scope must
        match exactly: a class row does not leak to the rest of the level, and a
        level row does not leak to other levels.
        """
        own_term = (self.term or '').strip()
        wanted_term = (term or '').strip()
        if own_term and own_term != wanted_term:
            return False
        if self.scope == self.Scope.CLASS:
            return school_class is not None and self.school_class_id == school_class.id
        if self.scope == self.Scope.LEVEL:
            return level is not None and self.level_id == level.id
        return True

    def save(self, *args, **kwargs):
        # Derive the non-null scope key from whichever FK is authoritative, so
        # the conflict constraint above is always meaningful.
        if self.scope == self.Scope.CLASS and self.school_class_id:
            self.scope_key = str(self.school_class_id)
            if self.school_class is not None:
                self.level = self.school_class.level
        elif self.scope == self.Scope.LEVEL and self.level_id:
            self.scope_key = str(self.level_id)
            self.school_class = None
        else:
            self.scope = self.Scope.SCHOOL
            self.scope_key = '*'
            self.level = None
            self.school_class = None
        super().save(*args, **kwargs)


def invoice_item_amount(item):
    """Read one line amount from an invoice snapshot.

    Snapshots written before the decimal-exact representation may hold floats or
    ints, so both are accepted (spec §8 — the snapshot is the source of truth
    for historical totals).
    """
    value = item.get('amount') if isinstance(item, dict) else None
    if value is None:
        return Decimal('0')
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


class Invoice(models.Model):
    class Source(models.TextChoices):
        ADMISSION = 'admission', 'New admission'
        BULK = 'bulk', 'Bulk generated'
        MIGRATION = 'migration', 'Migrated opening balance'

    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name='invoices')
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='invoices')
    academic_session = models.ForeignKey(
        AcademicSession, on_delete=models.SET_NULL, null=True, blank=True, related_name='invoices',
    )
    term = models.CharField(max_length=50)
    source = models.CharField(
        max_length=20, choices=Source.choices, default=Source.BULK,
    )
    # Immutable snapshot of the charges as configured when the invoice was
    # issued. `total` is always derived from this list — never from today's
    # FeeStructure (spec §8). Each entry: label, feeType, amount, scope, required.
    total = models.DecimalField(max_digits=12, decimal_places=2)
    paid = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    items = models.JSONField(default=list, blank=True)
    due_date = models.DateField(null=True, blank=True)
    is_cancelled = models.BooleanField(default=False)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    cancelled_by = models.ForeignKey(
        'accounts.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='cancelled_invoices',
    )
    cancel_reason = models.CharField(max_length=255, blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        constraints = [
            models.CheckConstraint(
                condition=Q(total__gte=0), name='invoice_total_non_negative',
            ),
            models.UniqueConstraint(
                fields=['student', 'academic_session', 'term'],
                condition=Q(academic_session__isnull=False),
                name='unique_invoice_per_student_session_term',
            ),
        ]
        indexes = [
            models.Index(fields=['school', 'student']),
            models.Index(fields=['school', 'academic_session']),
        ]

    def __str__(self):
        return f'{self.student_id} {self.term} {self.total}'

    @property
    def verified_paid(self):
        """Verified payments only (spec §10, §14).

        Authoritative when the invoice is not annotated; list endpoints
        annotate `verified_paid_total` to avoid the extra query.
        """
        annotated = getattr(self, 'verified_paid_total', None)
        if annotated is not None:
            return Decimal(annotated or 0)
        return self.payments.filter(status=Payment.Status.VERIFIED).aggregate(
            total=models.Sum('amount'),
        )['total'] or Decimal('0')

    @property
    def outstanding(self):
        return max(self.total - self.verified_paid, Decimal('0'))

    @property
    def status(self):
        """Derived status with fixed precedence (spec §11).

        CANCELLED → PAID → OVERDUE → PARTIALLY_PAID → UNPAID. Never trusts a
        client-supplied value.
        """
        if self.is_cancelled:
            return 'cancelled'
        paid = self.verified_paid
        if paid >= self.total:
            return 'paid'
        outstanding = self.total - paid
        if self.due_date and self.due_date < datetime.date.today():
            return 'overdue'
        if paid > 0:
            return 'partially_paid'
        return 'unpaid'


class Payment(models.Model):
    class Method(models.TextChoices):
        CASH = 'cash', 'Cash'
        BANK_TRANSFER = 'bank_transfer', 'Bank Transfer'
        CARD = 'card', 'Card'
        POS = 'pos', 'POS'
        USSD = 'ussd', 'USSD'
        ONLINE = 'online', 'Online'

    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending'
        VERIFIED = 'verified', 'Verified'
        FAILED = 'failed', 'Failed'
        REFUNDED = 'refunded', 'Refunded'
        REVERSED = 'reversed', 'Reversed'
        CANCELLED = 'cancelled', 'Cancelled'

    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name='payments')
    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name='payments')
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    method = models.CharField(max_length=20, choices=Method.choices)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PENDING)
    reference = models.CharField(max_length=64, unique=True)
    provider = models.CharField(max_length=30, blank=True, default='')
    # The provider's own reference. Unique so a replayed webhook can never
    # create a second payment (spec §17, §86).
    provider_reference = models.CharField(
        max_length=100, null=True, blank=True, unique=True,
    )
    # Opening balances brought in by the migration workflow are clearly
    # distinguishable from real money received on the day (spec §57).
    is_migration_data = models.BooleanField(default=False)
    payment_date = models.DateField(null=True, blank=True)
    recorded_by = models.ForeignKey(
        'accounts.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='recorded_payments',
    )
    verified_by = models.ForeignKey(
        'accounts.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='verified_payments',
    )
    verified_at = models.DateTimeField(null=True, blank=True)
    reversal_reason = models.CharField(max_length=255, blank=True, default='')
    note = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        constraints = [
            models.CheckConstraint(
                condition=Q(amount__gt=0), name='payment_amount_positive',
            ),
        ]
        indexes = [
            models.Index(fields=['school', 'status']),
            models.Index(fields=['invoice', 'status']),
        ]

    def __str__(self):
        return f'{self.reference} {self.amount} {self.status}'


class Registration(models.Model):
    """New-student admission (spec §19, §30).

    Deliberately separate from Student, Invoice and Enrollment so a registration
    can be PENDING while the invoice is PARTIALLY_PAID and no enrollment exists.
    """

    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending'
        APPROVED = 'approved', 'Approved'
        REJECTED = 'rejected', 'Rejected'
        CANCELLED = 'cancelled', 'Cancelled'

    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name='registrations')
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='registrations')
    academic_session = models.ForeignKey(
        AcademicSession, on_delete=models.PROTECT, related_name='registrations',
    )
    intended_class = models.ForeignKey(
        SchoolClass, on_delete=models.PROTECT, related_name='registrations',
    )
    intended_section = models.ForeignKey(
        Section, on_delete=models.SET_NULL, null=True, blank=True, related_name='registrations',
    )
    invoice = models.OneToOneField(
        Invoice, on_delete=models.SET_NULL, null=True, blank=True, related_name='registration',
    )
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.PENDING,
    )
    created_by = models.ForeignKey(
        'accounts.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='created_registrations',
    )
    approved_by = models.ForeignKey(
        'accounts.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='approved_registrations',
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    decision_reason = models.CharField(max_length=255, blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        constraints = [
            models.UniqueConstraint(
                fields=['student', 'academic_session'],
                name='unique_registration_per_student_session',
            ),
        ]
        indexes = [
            models.Index(fields=['school', 'status']),
        ]

    def __str__(self):
        return f'{self.student_id} {self.academic_session_id} {self.status}'


class Enrollment(models.Model):
    """The class/section assignment a roster is built from (spec §35, §49).

    A student with no ACTIVE enrollment must never appear in a class roster.
    """

    class Status(models.TextChoices):
        NOT_ENROLLED = 'not_enrolled', 'Not enrolled'
        ACTIVE = 'active', 'Active'
        SUSPENDED = 'suspended', 'Suspended'
        COMPLETED = 'completed', 'Completed'

    class ActivationSource(models.TextChoices):
        FULL_PAYMENT = 'full_payment', 'Full verified payment'
        ADMIN_APPROVAL = 'admin_approval', 'Administrator approval'
        MIGRATION = 'migration', 'Existing student migration'

    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name='enrollments')
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='enrollments')
    academic_session = models.ForeignKey(
        AcademicSession, on_delete=models.PROTECT, related_name='enrollments',
    )
    class_obj = models.ForeignKey(
        SchoolClass, on_delete=models.PROTECT, related_name='enrollments',
    )
    section = models.ForeignKey(
        Section, on_delete=models.SET_NULL, null=True, blank=True, related_name='enrollments',
    )
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.NOT_ENROLLED,
    )
    activation_source = models.CharField(
        max_length=20, choices=ActivationSource.choices, blank=True, default='',
    )
    activated_at = models.DateTimeField(null=True, blank=True)
    activated_by = models.ForeignKey(
        'accounts.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='activated_enrollments',
    )
    # Set when a later reversal leaves an enrollment running on money that is no
    # longer verified; an administrator reviews it (spec §44).
    flagged_for_review = models.BooleanField(default=False)
    review_note = models.CharField(max_length=255, blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        constraints = [
            # At most one active enrollment per student per session. A partial
            # index keeps previous sessions' history intact.
            models.UniqueConstraint(
                fields=['student', 'academic_session'],
                condition=Q(status='active'),
                name='unique_active_enrollment_per_session',
            ),
        ]
        indexes = [
            # Roster hot path (spec §74).
            models.Index(fields=['school', 'academic_session', 'class_obj', 'section', 'status']),
            models.Index(fields=['school', 'status']),
        ]

    def __str__(self):
        return f'{self.student_id} {self.class_obj_id} {self.status}'


class ImportBatch(models.Model):
    """Auditable record of one bulk student-migration run (spec §64-§66)."""

    class Status(models.TextChoices):
        COMPLETED = 'completed', 'Completed'
        FAILED = 'failed', 'Failed'

    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name='import_batches')
    batch_code = models.CharField(max_length=20)
    academic_session = models.ForeignKey(
        AcademicSession, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='import_batches',
    )
    uploaded_by = models.ForeignKey(
        'accounts.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='import_batches',
    )
    file_name = models.CharField(max_length=255)
    file_size = models.PositiveIntegerField(default=0)
    uploaded_count = models.PositiveIntegerField(default=0)
    created_count = models.PositiveIntegerField(default=0)
    updated_count = models.PositiveIntegerField(default=0)
    duplicate_count = models.PositiveIntegerField(default=0)
    error_count = models.PositiveIntegerField(default=0)
    errors_json = models.JSONField(default=list, blank=True)
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.COMPLETED,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        constraints = [
            models.UniqueConstraint(
                fields=['school', 'batch_code'], name='unique_import_batch_per_school',
            ),
        ]

    def __str__(self):
        return f'{self.batch_code} ({self.created_count} created)'
