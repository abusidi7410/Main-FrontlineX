import secrets

from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers
from .permissions import ROLE_PERMISSIONS
from .utils import generate_temp_password
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


# ── School-scoped account management ────────────────────────────────────────
#
# These serializers power the /accounts/users/ endpoints used by a school to
# provision logins for its own students, teachers, admins and finance staff.

# Roles a school may NOT provision internally.
_NON_PROVISIONABLE_ROLES = {'platform_manager'}

# Roles that are recognised as staff roster records and may carry a
# staff_profile link.
_STAFF_ROLES = {'principal', 'teacher', 'accountant', 'secretary', 'school_admin'}


class AccountSerializer(serializers.ModelSerializer):
    """Read model for a school account. CamelCase, string ids, no N+1."""

    id = serializers.SerializerMethodField()
    fullName = serializers.CharField(source='get_full_name')
    role = serializers.CharField(read_only=True)
    status = serializers.SerializerMethodField()
    mustChangePassword = serializers.BooleanField(
        source='must_change_password', read_only=True,
    )
    lastLogin = serializers.DateTimeField(
        source='last_login', format='%Y-%m-%dT%H:%M:%S', default=None,
    )
    joinedAt = serializers.DateTimeField(
        source='date_joined', format='%Y-%m-%dT%H:%M:%S',
    )
    student = serializers.SerializerMethodField()
    staff = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            'id', 'fullName', 'email', 'phone', 'role', 'status',
            'mustChangePassword', 'lastLogin', 'joinedAt', 'student', 'staff',
        ]

    def get_id(self, obj):
        return str(obj.pk)

    def get_status(self, obj):
        return 'active' if obj.is_active else 'inactive'

    def get_student(self, obj):
        student = getattr(obj, 'student_profile', None)
        if student is None:
            return None
        return {
            'id': str(student.id),
            'name': f'{student.first_name} {student.last_name}',
            'admissionNumber': student.admission_number,
            'className': student.class_name,
        }

    def get_staff(self, obj):
        staff = getattr(obj, 'staff_profile', None)
        if staff is None:
            return None
        return {
            'id': str(staff.id),
            'fullName': staff.full_name,
            'role': staff.role,
        }


class AccountCreateSerializer(serializers.Serializer):
    """Create a login account inside the caller's school.

    ``password`` is optional — when omitted the API provisions a temporary
    password and returns it once as ``defaultCredentials`` so only the
    person creating the account ever sees it.
    """

    fullName = serializers.CharField(max_length=300)
    email = serializers.EmailField()
    phone = serializers.CharField(required=False, allow_blank=True, default='')
    role = serializers.ChoiceField(
        choices=[c for c in User.Role.choices if c[0] not in _NON_PROVISIONABLE_ROLES],
    )
    password = serializers.CharField(
        required=False, allow_blank=True, default='',
        write_only=True, min_length=8, validators=[validate_password],
    )
    studentId = serializers.CharField(required=False, allow_blank=True, default='')
    staffId = serializers.CharField(required=False, allow_blank=True, default='')
    admissionNumber = serializers.CharField(required=False, allow_blank=True, default='')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._allowed_roles = kwargs['context']['allowed_roles']
        self._school_id = kwargs['context']['school_id']

    def validate_email(self, value):
        if User.objects.filter(email=value).exists():
            raise serializers.ValidationError('An account with this email already exists.')
        return value.lower()

    def validate_phone(self, value):
        if not value:
            return value
        normalized = normalize_phone(value)
        if not normalized:
            raise serializers.ValidationError('Enter a valid phone number.')
        if User.objects.filter(phone=normalized).exists():
            raise serializers.ValidationError('An account with this phone number already exists.')
        return normalized

    def validate_role(self, value):
        if value not in self._allowed_roles:
            raise serializers.ValidationError(
                'Your role does not allow creating accounts with this role.',
            )
        return value

    def _resolve_linked(self, attrs):
        """Validate and return (student, staff) linked to the same school."""
        student, staff = None, None
        student_id = (attrs.get('studentId') or '').strip()
        admission_number = (attrs.get('admissionNumber') or '').strip()
        staff_id = (attrs.get('staffId') or '').strip()

        if student_id:
            from records.models import Student
            student = Student.objects.filter(
                id=student_id, school_id=self._school_id,
            ).first()
            if student is None:
                raise serializers.ValidationError(
                    {'studentId': 'Student not found in your school.'},
                )
            if attrs.get('role') != User.Role.STUDENT:
                raise serializers.ValidationError(
                    {'studentId': 'Only student accounts can be linked to a student record.'},
                )
        elif admission_number:
            from records.models import Student
            student = Student.objects.filter(
                admission_number__iexact=admission_number,
                school_id=self._school_id,
            ).first()
            if student is None:
                raise serializers.ValidationError(
                    {'admissionNumber': 'No student with this admission number in your school.'},
                )
            if attrs.get('role') != User.Role.STUDENT:
                raise serializers.ValidationError(
                    {'admissionNumber': 'Only student accounts can be linked to a student record.'},
                )

        if staff_id:
            from records.models import StaffMember
            staff = StaffMember.objects.filter(
                id=staff_id, school_id=self._school_id,
            ).first()
            if staff is None:
                raise serializers.ValidationError(
                    {'staffId': 'Staff member not found in your school.'},
                )
            if attrs.get('role') not in _STAFF_ROLES:
                raise serializers.ValidationError(
                    {'staffId': 'Staff links are only valid for staff-role accounts.'},
                )

        return student, staff

    def validate(self, attrs):
        if attrs.get('role') == User.Role.STUDENT:
            if not ((attrs.get('studentId') or '').strip() or (attrs.get('admissionNumber') or '').strip()):
                raise serializers.ValidationError(
                    {'studentId': 'Student accounts must be linked to a student record '
                                  '(provide a student id or admission number).'},
                )
        self._resolve_linked(attrs)
        return attrs

    def create(self, validated_data):
        from django.db import transaction

        from .utils import audit

        school_id = self._school_id
        student, staff = self._resolve_linked(validated_data)
        role = validated_data['role']

        first_name, _, last_name = validated_data['fullName'].strip().partition(' ')

        password = validated_data.get('password') or ''
        generated = not password
        if not password:
            password = generate_temp_password()

        with transaction.atomic():
            user = User.objects.create_user(
                email=validated_data['email'],
                phone=validated_data.get('phone') or None,
                password=password,
                first_name=first_name.strip(),
                last_name=last_name.strip(),
                role=role,
                school_id=school_id,
                is_active=True,
                is_verified=not generated,
                must_change_password=generated,
                student_profile=student,
                staff_profile=staff,
            )

        mode = 'provisioned' if generated else 'created'
        audit(
            self.context['request'],
            'account.created',
            f'{user.get_full_name()} ({user.email})',
            f'Role {role} account {mode}.',
        )

        data = AccountSerializer(user).data
        if generated:
            data['defaultCredentials'] = {
                'email': user.email,
                'password': password,
                'mustChangePassword': True,
            }
        return data


class AccountUpdateSerializer(serializers.Serializer):
    """Partial update for a school account (name, phone, role)."""

    fullName = serializers.CharField(required=False)
    phone = serializers.CharField(required=False, allow_blank=True)
    role = serializers.ChoiceField(
        choices=[c for c in User.Role.choices if c[0] not in _NON_PROVISIONABLE_ROLES],
        required=False,
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._allowed_roles = kwargs['context']['allowed_roles']
        self._school_id = kwargs['context']['school_id']
        self._target = kwargs['context']['target']

    def validate_phone(self, value):
        if not value:
            return value
        normalized = normalize_phone(value)
        if not normalized:
            raise serializers.ValidationError('Enter a valid phone number.')
        dup = User.objects.filter(phone=normalized).exclude(pk=self._target.pk).exists()
        if dup:
            raise serializers.ValidationError('Another account already uses this phone number.')
        return normalized

    def validate_role(self, value):
        if value not in self._allowed_roles:
            raise serializers.ValidationError(
                'Your role does not allow assigning this role.',
            )
        return value

    def validate(self, attrs):
        if self._target.pk == self.context['request'].user.pk and (
            attrs.get('role') and attrs['role'] != self._target.role
        ):
            raise serializers.ValidationError(
                {'role': 'You cannot change your own role.'},
            )
        return attrs
