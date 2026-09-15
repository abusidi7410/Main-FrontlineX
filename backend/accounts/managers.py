from django.contrib.auth.models import BaseUserManager
from .validators import normalize_phone


class UserManager(BaseUserManager):
    """Custom manager where email is the primary login identifier."""

    def create_user(self, email, password=None, phone=None, **extra_fields):
        if not email:
            raise ValueError('Email is required.')

        email = self.normalize_email(email)
        user = self.model(email=email, phone=normalize_phone(phone) if phone else None, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('is_active', True)
        extra_fields.setdefault('role', 'superadmin')

        if extra_fields.get('role') != 'superadmin':
            raise ValueError('Superuser must have role=superadmin.')

        return self.create_user(email, password=password, **extra_fields)
