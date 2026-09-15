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
    updated_at = models.DateTimeField(auto_now=True)

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['first_name', 'last_name']

    objects = UserManager()

    class Meta:
        ordering = ['-date_joined']
        indexes = [
            models.Index(fields=['role']),
            models.Index(fields=['school', 'role']),
        ]

    def __str__(self):
        return f'{self.get_full_name()} ({self.role})'
