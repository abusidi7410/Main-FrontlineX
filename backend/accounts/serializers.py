from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers
from .permissions import ROLE_PERMISSIONS
from .validators import normalize_phone

User = get_user_model()

_SCHOOL_TYPE_CHOICES = ['nursery', 'primary', 'secondary', 'mixed']


# ── Registration ──────────────────────────────────────────────────────────────

class SchoolRegistrationSerializer(serializers.Serializer):
    """One-shot: creates a School + its first Admin user."""

    # School info
    school_name = serializers.CharField(max_length=255)
    school_type = serializers.ChoiceField(choices=_SCHOOL_TYPE_CHOICES)
    school_address = serializers.CharField()
    school_state = serializers.CharField(max_length=100)
    school_lga = serializers.CharField(max_length=100)
    school_phone = serializers.CharField(max_length=20)
    school_email = serializers.EmailField()
    school_website = serializers.URLField(required=False, allow_blank=True, default='')

    # Admin info
    admin_first_name = serializers.CharField(max_length=150)
    admin_last_name = serializers.CharField(max_length=150)
    admin_email = serializers.EmailField()
    admin_phone = serializers.CharField(
        max_length=20, required=False, allow_blank=True, default='',
    )
    admin_password = serializers.CharField(
        write_only=True, min_length=8, validators=[validate_password],
    )
    admin_password_confirm = serializers.CharField(write_only=True)

    # ── field-level validators ────────────────────────────────────────────

    def validate_admin_email(self, value):
        if User.objects.filter(email=value).exists():
            raise serializers.ValidationError(
                'A user with this email already exists.',
            )
        return value

    def validate_admin_phone(self, value):
        if not value:
            return value
        return normalize_phone(value)

    def validate_school_phone(self, value):
        return normalize_phone(value)

    # ── cross-field ───────────────────────────────────────────────────────

    def validate(self, data):
        if data['admin_password'] != data['admin_password_confirm']:
            raise serializers.ValidationError({
                'admin_password_confirm': 'Passwords do not match.',
            })
        return data

    # ── create ────────────────────────────────────────────────────────────

    def create(self, validated_data):
        from django.db import transaction
        from schools.models import School

        with transaction.atomic():
            school = School.objects.create(
                name=validated_data['school_name'],
                school_type=validated_data['school_type'],
                address=validated_data['school_address'],
                state=validated_data['school_state'],
                lga=validated_data['school_lga'],
                phone=validated_data['school_phone'],
                email=validated_data['school_email'],
                website=validated_data.get('school_website', ''),
                is_active=True,
            )

            user = User.objects.create_user(
                email=validated_data['admin_email'],
                phone=validated_data.get('admin_phone') or None,
                password=validated_data['admin_password'],
                first_name=validated_data['admin_first_name'],
                last_name=validated_data['admin_last_name'],
                role=User.Role.ADMIN,
                school=school,
                is_verified=True,
            )

        return user, school


# ── Login ─────────────────────────────────────────────────────────────────────

class LoginSerializer(serializers.Serializer):
    identifier = serializers.CharField(help_text='Email or phone number')
    password = serializers.CharField(write_only=True)

    def validate(self, data):
        # Accept legacy `login` key alongside `identifier`.
        if not data.get('identifier') and self.initial_data.get('login'):
            data['identifier'] = self.initial_data['login']
        return data


# ── User ──────────────────────────────────────────────────────────────────────

class AuthUserSerializer(serializers.ModelSerializer):
    """Frontend AuthUser shape: camelCase, permissions, schoolId, string ids."""

    id = serializers.SerializerMethodField()
    fullName = serializers.CharField(source='get_full_name')
    permissions = serializers.SerializerMethodField()
    schoolId = serializers.SerializerMethodField()
    avatarUrl = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            'id', 'fullName', 'email', 'phone', 'role', 'permissions',
            'schoolId', 'avatarUrl',
        ]
        read_only_fields = fields

    def get_id(self, obj):
        return str(obj.pk)

    def get_permissions(self, obj):
        return ROLE_PERMISSIONS.get(obj.role, [])

    def get_schoolId(self, obj):
        return str(obj.school_id) if obj.school_id else None

    def get_avatarUrl(self, obj):
        return None


class UserSerializer(serializers.ModelSerializer):
    school_name = serializers.CharField(
        source='school.name', read_only=True, default=None,
    )
    full_name = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            'id', 'email', 'phone', 'first_name', 'last_name',
            'full_name', 'role', 'school', 'school_name',
            'is_verified', 'date_joined',
        ]
        read_only_fields = fields

    def get_full_name(self, obj):
        return obj.get_full_name()


# ── Password change ───────────────────────────────────────────────────────────

class ChangePasswordSerializer(serializers.Serializer):
    current = serializers.CharField(write_only=True)
    next = serializers.CharField(
        write_only=True, min_length=8, validators=[validate_password],
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._user = self.context['request'].user

    def validate_current(self, value):
        if not self._user.check_password(value):
            raise serializers.ValidationError('Incorrect password.')
        return value

    def validate(self, data):
        if data['current'] == data['next']:
            raise serializers.ValidationError({
                'next': 'The new password must be different from the current one.',
            })
        return data


# ── Email verification ────────────────────────────────────────────────────────

class VerifyEmailRequestSerializer(serializers.Serializer):
    email = serializers.EmailField()


class VerifyEmailConfirmSerializer(serializers.Serializer):
    uid = serializers.CharField()
    token = serializers.CharField()


# ── Password reset ────────────────────────────────────────────────────────────

class PasswordResetRequestSerializer(serializers.Serializer):
    email = serializers.EmailField()


class PasswordResetConfirmSerializer(serializers.Serializer):
    """Frontend sends {token, password}; token is `<uid64>.<token>`."""
    token = serializers.CharField()
    password = serializers.CharField(
        write_only=True, min_length=8, validators=[validate_password],
    )
