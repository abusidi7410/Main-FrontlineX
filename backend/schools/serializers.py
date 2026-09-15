from django.contrib.auth import get_user_model
from rest_framework import serializers
from .models import School, SubscriptionPlan, SchoolSubscription

User = get_user_model()

_SCHOOL_TYPE_CHOICES = ['nursery', 'primary', 'secondary', 'mixed']


class SchoolRegistrationSerializer(serializers.Serializer):
    """Frontend OnboardingPayload: nested school + admin + tierId.

    ```json
    { "school": {...}, "admin": {fullName, phone, email, password}, "tierId": "t400" }
    ```
    Returns ``{schoolId, paymentRef}``.
    """

    school = serializers.DictField()
    admin = serializers.DictField()
    tierId = serializers.CharField(required=False, allow_blank=True)

    def validate_school(self, value):
        required = ['name', 'type', 'address', 'state', 'lga', 'phone', 'email']
        missing = [f for f in required if not value.get(f)]
        if missing:
            raise serializers.ValidationError(
                f'Missing school fields: {", ".join(missing)}.'
            )
        if School.objects.filter(email=value.get('email')).exists():
            raise serializers.ValidationError(
                'A school with this email already exists.'
            )
        if value.get('type') not in _SCHOOL_TYPE_CHOICES:
            raise serializers.ValidationError('Unsupported school type.')
        return value

    def validate_admin(self, value):
        required = ['fullName', 'email', 'password']
        missing = [f for f in required if not value.get(f)]
        if missing:
            raise serializers.ValidationError(
                f'Missing admin fields: {", ".join(missing)}.'
            )
        if User.objects.filter(email=value.get('email')).exists():
            raise serializers.ValidationError(
                'A user with this email already exists.'
            )
        return value

    def create(self, validated_data):
        from django.db import transaction

        school_data = validated_data['school']
        admin_data = validated_data['admin']
        tier_id = validated_data.get('tierId') or 't400'

        plan = None
        if tier_id.startswith('t'):
            try:
                index = int(tier_id[1:]) if tier_id[1:].isdigit() else None
                if index is not None:
                    plan = SubscriptionPlan.objects.filter(
                        min_students__lte=index
                    ).order_by('-min_students').first()
            except ValueError:
                plan = None
        if plan is None:
            plan = SubscriptionPlan.objects.first()

        with transaction.atomic():
            school = School.objects.create(
                name=school_data['name'],
                school_type=school_data['type'],
                address=school_data['address'],
                state=school_data['state'],
                lga=school_data['lga'],
                phone=school_data['phone'],
                email=school_data['email'],
                website=school_data.get('website', ''),
                is_active=True,
            )

            full_name = admin_data.get('fullName', '')
            parts = full_name.split(' ', 1)
            first_name = parts[0] if parts else ''
            last_name = parts[1] if len(parts) > 1 else ''

            admin = User.objects.create_user(
                email=admin_data['email'].strip().lower(),
                phone=admin_data.get('phone') or None,
                password=admin_data['password'],
                first_name=first_name,
                last_name=last_name,
                role=User.Role.SCHOOL_ADMIN,
                school=school,
                is_verified=True,
            )
            admin.save()

            SchoolSubscription.objects.create(
                school=school,
                plan=plan,
                status=SchoolSubscription.Status.ACTIVE,
                starts_at=school.created_at,
            )

        return {
            'schoolId': str(school.pk),
            'paymentRef': f'FN-{school.slug.upper()}',
        }


class SchoolSessionSerializer(serializers.ModelSerializer):
    """Frontend ``School`` shape: camelCase IDs, derived status/counts/branding."""

    id = serializers.SerializerMethodField()
    logoUrl = serializers.SerializerMethodField()
    status = serializers.SerializerMethodField()
    branding = serializers.SerializerMethodField()
    studentCount = serializers.SerializerMethodField()
    staffCount = serializers.SerializerMethodField()

    class Meta:
        model = School
        fields = [
            'id', 'name', 'slug', 'logoUrl', 'status', 'address', 'state',
            'lga', 'phone', 'email', 'current_session', 'current_term',
            'branding', 'studentCount', 'staffCount',
        ]
        read_only_fields = fields

    def get_id(self, obj):
        return str(obj.pk)

    def get_logoUrl(self, obj):
        if obj.logo:
            return obj.logo.url
        return None

    def get_status(self, obj):
        sub = getattr(obj, 'subscription', None)
        if sub is None:
            return 'active' if obj.is_active else 'pending_payment'
        mapping = {
            SchoolSubscription.Status.ACTIVE: 'active',
            SchoolSubscription.Status.PENDING: 'pending_payment',
            SchoolSubscription.Status.EXPIRED: 'grace',
            SchoolSubscription.Status.SUSPENDED: 'suspended',
        }
        return mapping.get(sub.status, 'active' if obj.is_active else 'pending_payment')

    def get_branding(self, obj):
        return {'primary': obj.primary_color, 'secondary': obj.secondary_color}

    def get_studentCount(self, obj):
        return obj.users.filter(role='student').count()

    def get_staffCount(self, obj):
        from django.contrib.auth import get_user_model
        return obj.users.exclude(role__in=['student', 'parent']).count()


class SchoolSerializer(serializers.ModelSerializer):
    class Meta:
        model = School
        fields = [
            'id', 'name', 'slug', 'school_type', 'address', 'state', 'lga',
            'phone', 'email', 'logo', 'website',
            'primary_color', 'secondary_color',
            'is_active', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'slug', 'is_active', 'created_at', 'updated_at']


class SubscriptionPlanSerializer(serializers.ModelSerializer):
    class Meta:
        model = SubscriptionPlan
        fields = [
            'id', 'name', 'min_students', 'max_students',
            'monthly_price', 'ai_credits', 'features', 'is_active',
        ]
        read_only_fields = fields


class SchoolSubscriptionSerializer(serializers.ModelSerializer):
    plan = SubscriptionPlanSerializer(read_only=True)

    class Meta:
        model = SchoolSubscription
        fields = ['id', 'school', 'plan', 'status', 'starts_at', 'expires_at', 'created_at']
        read_only_fields = fields
