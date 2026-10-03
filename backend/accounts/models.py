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
    profile_photo_public_id = models.CharField(max_length=255, blank=True, default='')

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
