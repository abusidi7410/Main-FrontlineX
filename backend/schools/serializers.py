from datetime import timedelta

from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework import serializers
from .models import School, SchoolSubscription, SubscriptionPayment, SubscriptionPlan

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
        # Coordinates are optional (a school may register before it can get a
        # GPS fix) but must arrive as a pair.
        has_lat = value.get('latitude') is not None
        has_lng = value.get('longitude') is not None
        if has_lat != has_lng:
            raise serializers.ValidationError(
                'Provide both latitude and longitude, or neither.'
            )
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
        from django.conf import settings
        from django.db import transaction

        school_data = validated_data['school']
        admin_data = validated_data['admin']
        tier_id = validated_data.get('tierId') or 't400'
        trial_days = getattr(settings, 'REGISTRATION_TRIAL_DAYS', 7)

        plan = None
        tier = (tier_id or '').strip()
        if tier:
            plan = SubscriptionPlan.objects.filter(code=tier).first()
        if plan is None and tier.startswith('t'):
            index = int(tier[1:]) if tier[1:].isdigit() else None
            if index is not None:
                plan = SubscriptionPlan.objects.filter(
                    is_active=True,
                    min_students__lte=index,
                ).order_by('-min_students').first()
        if plan is None:
            plan = (
                SubscriptionPlan.objects.filter(is_active=True)
                .order_by('sort_order', 'min_students')
                .first()
            )

        now = timezone.now()
        trial_ends_at = now + timedelta(days=trial_days)

        with transaction.atomic():
            latitude = school_data.get('latitude')
            longitude = school_data.get('longitude')
            has_location = latitude is not None and longitude is not None
            school = School.objects.create(
                name=school_data['name'],
                school_type=school_data['type'],
                address=school_data['address'],
                state=school_data['state'],
                lga=school_data['lga'],
                phone=school_data['phone'],
                email=school_data['email'],
                website=school_data.get('website', ''),
                # A new school starts on a free trial: it is switched on
                # immediately so the administrator can set it up, and its
                # subscription lapses on its own when the trial window closes.
                is_active=True,
                latitude=latitude if has_location else None,
                longitude=longitude if has_location else None,
                gps_accuracy=school_data.get('gpsAccuracy') if has_location else None,
                timezone=(school_data.get('timezone') or '').strip() or 'Africa/Lagos',
                location_set_at=now if has_location else None,
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
                # The administrator can sign in straight away — the details
                # they registered with are the only proof of ownership needed.
                is_active=True,
                is_verified=True,
            )
            admin.save()

            SchoolSubscription.objects.create(
                school=school,
                plan=plan,
                status=SchoolSubscription.Status.TRIAL,
                starts_at=now,
                expires_at=trial_ends_at,
            )

        return {
            'schoolId': str(school.pk),
            'paymentRef': f'FN-{school.slug.upper()}',
            'trial': True,
            'trialEndsAt': trial_ends_at.isoformat(),
            'trialDays': trial_days,
            'planName': plan.name if plan else '',
        }


class SchoolSessionSerializer(serializers.ModelSerializer):
    """Frontend ``School`` shape: camelCase IDs, derived status/counts/branding."""

    id = serializers.SerializerMethodField()
    logoUrl = serializers.SerializerMethodField()
    status = serializers.SerializerMethodField()
    branding = serializers.SerializerMethodField()
    studentCount = serializers.SerializerMethodField()
    staffCount = serializers.SerializerMethodField()
    latitude = serializers.SerializerMethodField()
    longitude = serializers.SerializerMethodField()
    gpsAccuracy = serializers.FloatField(source='gps_accuracy', allow_null=True)
    attendanceRadius = serializers.IntegerField(source='attendance_radius')
    locationSetAt = serializers.DateTimeField(source='location_set_at', allow_null=True)
    locationConfirmedAt = serializers.DateTimeField(source='location_confirmed_at', allow_null=True)

    class Meta:
        model = School
        fields = [
            'id', 'name', 'slug', 'logoUrl', 'status', 'address', 'state',
            'lga', 'phone', 'email', 'current_session', 'current_term',
            'branding', 'studentCount', 'staffCount',
            'latitude', 'longitude', 'gpsAccuracy', 'attendanceRadius',
            'timezone', 'locationSetAt', 'locationConfirmedAt',
        ]
        read_only_fields = fields

    def get_id(self, obj):
        return str(obj.pk)

    def get_latitude(self, obj):
        return float(obj.latitude) if obj.latitude is not None else None

    def get_longitude(self, obj):
        return float(obj.longitude) if obj.longitude is not None else None


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
            SchoolSubscription.Status.TRIAL: 'trial',
            SchoolSubscription.Status.PENDING: 'pending_payment',
            SchoolSubscription.Status.EXPIRED: 'grace',
            SchoolSubscription.Status.SUSPENDED: 'suspended',
        }
        if sub.override_current:
            return 'active'
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
            'latitude', 'longitude', 'gps_accuracy', 'attendance_radius',
            'timezone', 'location_set_at', 'location_confirmed_at',
            'is_active', 'created_at', 'updated_at',
        ]
        read_only_fields = [
            'id', 'slug', 'is_active', 'created_at', 'updated_at',
            'location_set_at', 'location_confirmed_at',
        ]

    def validate(self, attrs):
        # The location is stored on Settings as a pair; a partial PATCH that
        # names only one half is refused rather than producing a half-moved
        # campus. An explicit null pair clears it.
        if not self.partial:
            return attrs
        instance = self.instance
        lat = attrs.get('latitude', instance.latitude if instance else None)
        lng = attrs.get('longitude', instance.longitude if instance else None)
        if (lat is None) != (lng is None):
            raise serializers.ValidationError(
                'Provide both latitude and longitude, or neither.'
            )
        return attrs

    def update(self, instance, validated_data):
        location_changed = False
        if 'latitude' in validated_data or 'longitude' in validated_data:
            location_changed = True
        school = super().update(instance, validated_data)
        if location_changed:
            school.location_set_at = timezone.now()
            school.location_confirmed_at = timezone.now()
            school.save(update_fields=['location_set_at', 'location_confirmed_at'])
        return school



class SubscriptionPlanSerializer(serializers.ModelSerializer):
    class Meta:
        model = SubscriptionPlan
        fields = [
            'id', 'code', 'name', 'min_students', 'max_students',
            'monthly_price', 'ai_credits', 'storage_gb',
            'monthly_sms_allowance', 'monthly_otp_allowance', 'monthly_ai_allowance',
            'sms_cost_per_unit', 'otp_cost_per_unit', 'ai_cost_per_credit',
            'features', 'is_active', 'sort_order',
        ]
        read_only_fields = fields


class PublicPlanSerializer(serializers.ModelSerializer):
    """The plan shape the pricing table and onboarding consume (camelCase).

    `id` is the plan's stable `code` (falling back to its name), because the
    frontend stores and re-sends it as the tier identifier. Prices are emitted
    as numbers, not decimal strings, so the client can format them directly.
    """

    id = serializers.SerializerMethodField()
    label = serializers.CharField(source='name')
    minStudents = serializers.IntegerField(source='min_students')
    maxStudents = serializers.SerializerMethodField()
    monthlyPrice = serializers.SerializerMethodField()
    aiCredits = serializers.IntegerField(source='ai_credits')
    storageGb = serializers.IntegerField(source='storage_gb')
    smsAllowance = serializers.IntegerField(source='monthly_sms_allowance')
    otpAllowance = serializers.IntegerField(source='monthly_otp_allowance')
    aiAllowance = serializers.IntegerField(source='monthly_ai_allowance')

    class Meta:
        model = SubscriptionPlan
        fields = [
            'id', 'label', 'minStudents', 'maxStudents', 'monthlyPrice',
            'aiCredits', 'storageGb', 'smsAllowance', 'otpAllowance',
            'aiAllowance', 'features',
        ]

    def get_id(self, obj):
        return obj.code or obj.name

    def get_maxStudents(self, obj):
        return obj.max_students

    def get_monthlyPrice(self, obj):
        return float(obj.monthly_price)


class PlatformPlanSerializer(serializers.ModelSerializer):
    """Read/write shape for the platform manager's plan editor (camelCase)."""

    id = serializers.CharField(source='code', required=False, allow_blank=True, allow_null=True)
    label = serializers.CharField(source='name')
    minStudents = serializers.IntegerField(source='min_students', min_value=0)
    maxStudents = serializers.IntegerField(
        source='max_students', required=False, allow_null=True, min_value=0,
    )
    monthlyPrice = serializers.DecimalField(
        source='monthly_price', max_digits=10, decimal_places=2, min_value=0,
    )
    aiCredits = serializers.IntegerField(source='ai_credits', required=False, default=0)
    storageGb = serializers.IntegerField(source='storage_gb', required=False, default=0)
    smsAllowance = serializers.IntegerField(
        source='monthly_sms_allowance', required=False, default=0,
    )
    otpAllowance = serializers.IntegerField(
        source='monthly_otp_allowance', required=False, default=0,
    )
    aiAllowance = serializers.IntegerField(
        source='monthly_ai_allowance', required=False, default=0,
    )
    smsCostPerUnit = serializers.IntegerField(
        source='sms_cost_per_unit', required=False, default=0,
    )
    otpCostPerUnit = serializers.IntegerField(
        source='otp_cost_per_unit', required=False, default=0,
    )
    aiCostPerCredit = serializers.IntegerField(
        source='ai_cost_per_credit', required=False, default=0,
    )
    sortOrder = serializers.IntegerField(source='sort_order', required=False, default=0)
    isActive = serializers.BooleanField(source='is_active', required=False, default=True)
    features = serializers.ListField(
        child=serializers.CharField(allow_blank=True), required=False,
    )

    class Meta:
        model = SubscriptionPlan
        fields = [
            'id', 'label', 'minStudents', 'maxStudents', 'monthlyPrice',
            'aiCredits', 'storageGb', 'smsAllowance', 'otpAllowance',
            'aiAllowance', 'smsCostPerUnit', 'otpCostPerUnit', 'aiCostPerCredit',
            'sortOrder', 'isActive', 'features',
        ]


class SubscriptionPaymentSerializer(serializers.ModelSerializer):
    id = serializers.SerializerMethodField()
    schoolId = serializers.SerializerMethodField()
    schoolName = serializers.SerializerMethodField()
    planId = serializers.SerializerMethodField()
    planName = serializers.SerializerMethodField()
    amount = serializers.SerializerMethodField()
    amountKobo = serializers.IntegerField(source='amount_kobo')
    paystackReference = serializers.CharField(source='paystack_reference')
    paidAt = serializers.DateTimeField(source='paid_at', allow_null=True)
    createdAt = serializers.DateTimeField(source='created_at')

    class Meta:
        model = SubscriptionPayment
        fields = [
            'id', 'schoolId', 'schoolName', 'planId', 'planName',
            'reference', 'amount', 'amountKobo', 'currency', 'status', 'purpose',
            'channel', 'paystackReference', 'paidAt', 'createdAt',
        ]

    def get_id(self, obj):
        return str(obj.pk)

    def get_schoolId(self, obj):
        return str(obj.school_id)

    def get_schoolName(self, obj):
        return obj.school.name if obj.school_id else ''

    def get_planId(self, obj):
        return (obj.plan.code or obj.plan.name) if obj.plan_id else None

    def get_planName(self, obj):
        return obj.plan.name if obj.plan_id else ''

    def get_amount(self, obj):
        return float(obj.amount_kobo) / 100


class SchoolSubscriptionSerializer(serializers.ModelSerializer):
    plan = SubscriptionPlanSerializer(read_only=True)

    class Meta:
        model = SchoolSubscription
        fields = ['id', 'school', 'plan', 'status', 'starts_at', 'expires_at', 'created_at']
        read_only_fields = fields
