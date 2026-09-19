from django.db import models
from django.utils.text import slugify


class School(models.Model):
    class SchoolType(models.TextChoices):
        NURSERY = 'nursery', 'Nursery'
        PRIMARY = 'primary', 'Primary'
        SECONDARY = 'secondary', 'Secondary'
        MIXED = 'mixed', 'Mixed'

    name = models.CharField(max_length=255)
    slug = models.SlugField(unique=True, max_length=255)
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

    actor = models.CharField(max_length=255)
    role = models.CharField(max_length=20, blank=True, default='')
    action = models.CharField(max_length=100)
    target = models.CharField(max_length=255, blank=True, default='')
    detail = models.TextField(blank=True, default='')
    ip = models.CharField(max_length=64, blank=True, default='')
    severity = models.CharField(
        max_length=10, choices=Severity.choices, default=Severity.INFO,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

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

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.title
