from django.contrib.auth.models import BaseUserManager
from .validators import normalize_phone


class UserManager(BaseUserManager):
    """Custom manager where email is the primary login identifier."""

    def create_user(self, email, password=None, phone=None, **extra_fields):
        # Email is optional for phone-provisioned accounts (e.g. the parent
        # accounts auto-created at student registration); such users sign in
        # with their phone number instead. Phone is globally unique, so a
        # blank phone is normalised to None to avoid duplicate '' rows.
        email = self.normalize_email(email) if email else None
        normalized_phone = normalize_phone(phone) if phone else None
        user = self.model(email=email, phone=normalized_phone, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('is_active', True)
        # The role must be one the model actually accepts. This used to demand a
        # 'superadmin' value that is not in `User.Role`, so `createsuperuser`
        # always raised and the only way to create the first platform user
        # (the `create_superadmin` command, which passes 'platform_manager')
        # was rejected too.
        extra_fields.setdefault('role', self.model.Role.PLATFORM_MANAGER)

        if extra_fields.get('role') != self.model.Role.PLATFORM_MANAGER:
            raise ValueError('Superuser must have role=platform_manager.')

        return self.create_user(email, password=password, **extra_fields)
