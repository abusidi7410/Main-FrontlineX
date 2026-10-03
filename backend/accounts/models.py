from django.contrib.auth.models import AbstractUser
from django.db import models
from .managers import UserManager


class User(AbstractUser):
    """Frontline Nexus custom user model.

    - No username field (use email or phone to log in)
    - School FK provides tenant scope (superadmin has none)
    - role enum governs access across the whole platform
    """

    class Role(models.TextChoices):
        PLATFORM_MANAGER = 'platform_manager', 'Platform Manager'
        SCHOOL_ADMIN = 'school_admin', 'School Admin'
        PRINCIPAL = 'principal', 'Principal'
        TEACHER = 'teacher', 'Teacher'
        ACCOUNTANT = 'accountant', 'Accountant'
        SECRETARY = 'secretary', 'Secretary'
        PARENT = 'parent', 'Parent'
        STUDENT = 'student', 'Student'

    username = None  # disable username entirely

    email = models.EmailField(unique=True)
    phone = models.CharField(max_length=20, unique=True, null=True, blank=True)
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.SCHOOL_ADMIN)
    school = models.ForeignKey(
        'schools.School',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='users',
    )
    is_verified = models.BooleanField(default=False)

    # Optional links so role accounts map onto the school roster records.
    # SET_NULL: removing a Student/StaffMember keeps the login account alive.
    student_profile = models.OneToOneField(
        'records.Student',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='user_account',
    )
    staff_profile = models.OneToOneField(
        'records.StaffMember',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='user_account',
    )

    # Which students a parent/guardian account may see (spec 62, 65).
    #
    # Explicit, and never inferred from a surname or a phone number: a match on
    # a shared phone or family name would silently hand one family another
    # family's attendance and results. Nothing is visible until an
    # administrator links the account here.
    linked_students = models.ManyToManyField(
        'records.Student',
        blank=True,
        related_name='guardian_accounts',
    )

    # True when a login was provisioned with a generated one-time password;
    # the user must change it on first successful authentication.
    must_change_password = models.BooleanField(default=False)
    last_password_reset_at = models.DateTimeField(null=True, blank=True)
    # Where this account last signed in from. Compared on each login to raise a
    # `security` notification when the answer changes, so a head teacher can see
    # a colleague's account being used from somewhere else. NULL means "never
    # recorded", which is deliberately *not* treated as a change: the first
    # login after this field exists is not a suspicious sign-in.
    last_login_ip = models.GenericIPAddressField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['first_name', 'last_name']

    objects = UserManager()

    class Meta:
        ordering = ['-date_joined']
        indexes = [
            models.Index(fields=['role']),
            models.Index(fields=['school', 'role']),
            # Hot paths: school-scoped account lists, role filters and
            # active-user counts (thousands of schools, each with many users).
            models.Index(fields=['school', 'role', 'is_active']),
            models.Index(fields=['school', 'last_name', 'first_name']),
        ]

    def __str__(self):
        return f'{self.get_full_name()} ({self.role})'


class Notification(models.Model):
    """One delivered, per-recipient notification (spec 32).

    A row is written per recipient rather than computed at read time. Two things
    force that: unread state belongs to a person and has to survive across
    devices and sessions, and eight different subsystems (payments, attendance,
    results, announcements, subscription, AI, security, system) have to appear
    in one ordered, paginated feed. Deriving that feed per request would mean
    scanning each source table on every poll and still could not paginate.

    `school` records where the event happened so the row stays attributable and
    survives the recipient leaving the school (SET_NULL); it is never used to
    decide who may read the notification, which is `user` alone.
    """

    class Type(models.TextChoices):
        PAYMENT = 'payment', 'Payment'
        ATTENDANCE = 'attendance', 'Attendance'
        RESULT = 'result', 'Result'
        ANNOUNCEMENT = 'announcement', 'Announcement'
        SUBSCRIPTION = 'subscription', 'Subscription'
        AI = 'ai', 'AI usage'
        SECURITY = 'security', 'Security'
        SYSTEM = 'system', 'System'

    user = models.ForeignKey(
        'accounts.User', on_delete=models.CASCADE, related_name='notifications',
    )
    school = models.ForeignKey(
        'schools.School', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='notifications',
    )
    type = models.CharField(max_length=20, choices=Type.choices, default=Type.SYSTEM)
    title = models.CharField(max_length=200)
    body = models.TextField(blank=True, default='')
    # In-app route the notification opens, e.g. '/timetable'. Stored as a path
    # rather than a URL so it can never point at another host.
    link = models.CharField(max_length=200, blank=True, default='')
    read_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    # Set when one event should produce at most one notification per person,
    # e.g. `payment:<id>`. Lets a retried or replayed event stay idempotent
    # instead of stacking duplicates in the feed.
    dedupe_key = models.CharField(max_length=120, blank=True, default='')

    class Meta:
        ordering = ['-created_at', '-id']
        indexes = [
            # The whole product reads this list through the same index: the
            # notification centre pages through it and the bell counts from it.
            models.Index(fields=['user', '-created_at']),
            models.Index(fields=['user', 'type']),
            # Unread counting, which runs on every poll and must not walk the
            # user's entire history.
            models.Index(
                fields=['user'],
                condition=models.Q(read_at__isnull=True),
                name='notif_unread_idx',
            ),
        ]
        constraints = [
            # Blank means "no dedupe", so a partial unique index is the only
            # form that leaves repeat notifications alone.
            models.UniqueConstraint(
                fields=('user', 'dedupe_key'),
                condition=~models.Q(dedupe_key=''),
                name='unique_notification_per_user_dedupe',
            ),
        ]

    def __str__(self):
        return f'{self.type}: {self.title}'

    @property
    def read(self) -> bool:
        return self.read_at is not None


class NotificationPreference(models.Model):
    """A person's per-type opt-out (spec 35, Settings → Notifications).

    Absence of a row means enabled, so the default for a new account is
    "notify me" without needing a seed row per type.
    """

    user = models.ForeignKey(
        'accounts.User', on_delete=models.CASCADE, related_name='notification_preferences',
    )
    type = models.CharField(max_length=20, choices=Notification.Type.choices)
    in_app = models.BooleanField(default=True)

    class Meta:
        ordering = ['type']
        constraints = [
            models.UniqueConstraint(fields=('user', 'type'), name='unique_notification_pref'),
        ]

    def __str__(self):
        return f'{self.user_id}:{self.type}={self.in_app}'
