from django.db import models
from django.utils.text import slugify


def _default_attendance_weekend_days():
    """Saturday and Sunday are non-school days unless a school says otherwise."""
    return [5, 6]


class School(models.Model):
    class SchoolType(models.TextChoices):
        NURSERY = 'nursery', 'Nursery'
        PRIMARY = 'primary', 'Primary'
        SECONDARY = 'secondary', 'Secondary'
        MIXED = 'mixed', 'Mixed'

    name = models.CharField(max_length=255)
    slug = models.SlugField(unique=True, max_length=255)
    # Short, stable code used as the first segment of every admission number
    # (spec §27). Stored permanently: admission numbers must never be recomputed
    # from the school name, so renaming a school must not rewrite identifiers.
    # Blank until an administrator confirms it (admission numbers cannot be
    # issued without it). `suggest_code` only proposes a starting point.
    code = models.CharField(max_length=10, blank=True, default='')
    school_type = models.CharField(
        max_length=20, choices=SchoolType.choices, default=SchoolType.MIXED,
    )
    address = models.TextField()
    state = models.CharField(max_length=100)
    lga = models.CharField(max_length=100)
    phone = models.CharField(max_length=20)
    email = models.EmailField()
    logo = models.ImageField(upload_to='schools/logos/', null=True, blank=True)
    website = models.URLField(blank=True, default='')

    # Branding
    primary_color = models.CharField(max_length=7, default='#1e40af')
    secondary_color = models.CharField(max_length=7, default='#3b82f6')

    is_active = models.BooleanField(default=False)
    current_session = models.CharField(max_length=20, default='2025/2026')
    current_term = models.CharField(max_length=50, default='First Term')
    classes = models.JSONField(default=list, blank=True)
    subjects = models.JSONField(default=list, blank=True)
    # ── Attendance calendar (spec §attendance) ──
    # ISO dates ('2026-12-25') the school is closed, e.g. public holidays.
    non_school_days = models.JSONField(default=list, blank=True, db_default=[])
    # Python weekday numbers that are non-school days. 5 = Saturday, 6 = Sunday.
    attendance_weekend_days = models.JSONField(
        default=_default_attendance_weekend_days, blank=True, db_default=[5, 6],
    )
    fee_structure = models.JSONField(default=list, blank=True)
    # Financial clearance policy (spec 21, 44).
    #
    # False (default): a registration fee alone is enough to clear a new
    # student, so a family that has paid the admission charge is enrolled even
    # while tuition is arranged separately.
    # True: every required fee on the admission invoice must be paid in full
    # before the student is financially cleared.
    #
    # Either way a student still needs a valid `Enrollment` to appear in a class
    # roster: payment never activates a student by itself.
    # `db_default` as well as `default`: the database itself needs a default so
    # the column is safe to add to existing rows and so any write that does not
    # name the field (a bulk load, a historical model, raw SQL) still works.
    activation_requires_full_settlement = models.BooleanField(default=False, db_default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']
        indexes = [
            models.Index(fields=['is_active']),
            models.Index(fields=['state']),
        ]

    def __str__(self):
        return self.name

    # Words that carry no meaning in a school code, so "The" in "The Success
    # Academy" does not become the T of TSA.
    CODE_STOPWORDS = {'the', 'a', 'an', 'of', 'and'}

    @classmethod
    def suggest_code(cls, name):
        """Propose a short uppercase code for a school name (spec §28).

        Deliberately simple: the initials of at most three words, so
        "Success Academy" → "SA" and "Bright Hope International School" → "BHI".
        This is a *suggestion* only. The stored `code` is the source of truth
        and is never recalculated once admission numbers have been issued.

        Words like "School" and "Academy" are kept: they are the school's own
        words, and dropping them turns "Success Academy" into "SUC".
        """
        words = [w for w in ''.join(c if c.isalnum() else ' ' for c in name).split() if w]
        significant = [w for w in words if w.lower() not in cls.CODE_STOPWORDS] or words
        if not significant:
            return ''
        if len(significant) == 1:
            return significant[0][:3].upper()
        return ''.join(w[0] for w in significant[:3]).upper()

    def save(self, *args, **kwargs):
        if not self.slug:
            base = slugify(self.name)
            slug = base
            counter = 1
            while School.objects.filter(slug=slug).exists():
                slug = f'{base}-{counter}'
                counter += 1
            self.slug = slug
        super().save(*args, **kwargs)


class SubscriptionPlan(models.Model):
    name = models.CharField(max_length=100)
    min_students = models.PositiveIntegerField()
    max_students = models.PositiveIntegerField()
    monthly_price = models.DecimalField(max_digits=12, decimal_places=2)
    ai_credits = models.PositiveIntegerField(default=0)
    features = models.JSONField(default=list, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['min_students']

    def __str__(self):
        return f'{self.name} ({self.min_students}–{self.max_students} students)'


class SchoolSubscription(models.Model):
    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending'
        ACTIVE = 'active', 'Active'
        EXPIRED = 'expired', 'Expired'
        SUSPENDED = 'suspended', 'Suspended'

    school = models.OneToOneField(
        School, on_delete=models.CASCADE, related_name='subscription',
    )
    plan = models.ForeignKey(
        SubscriptionPlan, on_delete=models.SET_NULL, null=True, blank=True,
    )
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.PENDING,
    )
    starts_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f'{self.school.name} – {self.status}'

    class Meta:
        indexes = [
            models.Index(fields=['status']),
        ]


class AuditLog(models.Model):
    class Severity(models.TextChoices):
        INFO = 'info', 'Info'
        WARNING = 'warning', 'Warning'
        CRITICAL = 'critical', 'Critical'

    school = models.ForeignKey(
        School,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='audit_logs',
    )
    actor = models.CharField(max_length=255)
    role = models.CharField(max_length=20, blank=True, default='')
    action = models.CharField(max_length=100)
    target = models.CharField(max_length=255, blank=True, default='')
    # The acting account, so an audit entry is attributable even if the person
    # later leaves the school or their name/email changes. `actor` above stays
    # as the human-readable string the platform screens already display.
    user = models.ForeignKey(
        'accounts.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='audit_entries',
    )
    # The record the entry is about, e.g. 'student' / 'payment' / 'enrollment'.
    entity = models.CharField(max_length=40, blank=True, default='')
    entity_id = models.CharField(max_length=40, blank=True, default='')
    # Before/after values for the fields an operation changed, so a reviewer can
    # see what moved without diffing every table.
    before = models.JSONField(default=dict, blank=True)
    after = models.JSONField(default=dict, blank=True)
    detail = models.TextField(blank=True, default='')
    ip = models.CharField(max_length=64, blank=True, default='')
    severity = models.CharField(
        max_length=10, choices=Severity.choices, default=Severity.INFO,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        # A single `indexes` declaration. This was previously declared twice:
        # Python kept only the last one, so the `(school, action)` and
        # `(school, entity, entity_id)` indexes the audit screen depends on were
        # never actually created. Attendance corrections add a lot of audit
        # volume, which is exactly when those filters start to hurt.
        indexes = [
            models.Index(fields=['school']),
            models.Index(fields=['-created_at']),
            # The audit screen filters a school's entries by action, and a
            # per-entity trail filters by school + entity + id.
            models.Index(fields=['school', 'action']),
            models.Index(fields=['school', 'entity', 'entity_id']),
        ]

    def __str__(self):
        return f'{self.action} → {self.target} by {self.actor}'


class SupportTicket(models.Model):
    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending'
        UNDER_REVIEW = 'under_review', 'Under review'
        VERIFIED = 'verified', 'Resolved'

    school = models.ForeignKey(
        School, on_delete=models.SET_NULL, null=True, blank=True, related_name='support_tickets',
    )
    requester = models.EmailField()
    subject = models.CharField(max_length=200)
    message = models.TextField(blank=True, default='')
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'#{self.pk} {self.subject}'


class Announcement(models.Model):
    class Scope(models.TextChoices):
        SCHOOL = 'school', 'School'
        PLATFORM = 'platform', 'Platform'

    school = models.ForeignKey(
        School, on_delete=models.CASCADE, null=True, blank=True, related_name='announcements',
    )
    author = models.ForeignKey(
        'accounts.User', on_delete=models.SET_NULL, null=True, blank=True,
    )
    title = models.CharField(max_length=200)
    body = models.TextField(blank=True, default='')
    audience = models.JSONField(default=list, blank=True)
    scope = models.CharField(max_length=20, choices=Scope.choices, default=Scope.PLATFORM)
    created_at = models.DateTimeField(auto_now_add=True)

    # A pinned notice stays at the top of the list regardless of publish date,
    # because the messages a school actually needs to not lose are the ones
    # about an exam, a closure or a fee deadline.
    is_pinned = models.BooleanField(default=False)
    # Optional. A school sets this on a notice that stops being true (a
    # rescheduled exam, a cleared closure); the read path hides anything past
    # it while the row is kept, so the history stays intact.
    expires_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Optional class/session targeting. When any of these is set, recipients
    # are resolved through ACTIVE enrollments — never from a hand-maintained
    # recipient list — so a transfer/promotion/section change moves
    # accordingly. All three must belong to the announcement's school (checked
    # in services.announcements.create).
    target_class = models.ForeignKey(
        'records.SchoolClass', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='+',
    )
    target_section = models.ForeignKey(
        'records.Section', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='+',
    )
    target_academic_session = models.ForeignKey(
        'records.AcademicSession', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='+',
    )

    class Meta:
        ordering = ['-is_pinned', '-created_at']
        indexes = [
            # The read path is always "this school's live notices, pinned
            # first", so the school column is the leading filter.
            models.Index(fields=['school', '-is_pinned', '-created_at']),
            # Class-targeted boards filter on target_class within one school.
            models.Index(fields=['school', 'target_class']),
        ]

    def __str__(self):
        return self.title
