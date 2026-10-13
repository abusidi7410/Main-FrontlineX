from django.utils.decorators import method_decorator
from django.views.decorators.cache import cache_page
from rest_framework import status, viewsets
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.permissions import HasSchool, IsSuperAdmin, require_permissions
from accounts.utils import audit
from .geocoding import reverse_geocode
from .models import School, SubscriptionPlan
from .serializers import (
    PlatformPlanSerializer,
    PublicPlanSerializer,
    SchoolRegistrationSerializer,
    SchoolSerializer,
    SchoolSessionSerializer,
    SubscriptionPlanSerializer,
)


class SchoolViewSet(viewsets.ModelViewSet):
    """Schools are managed by the platform superadmin only.

    Regular users must never be able to enumerate other tenants.
    """
    queryset = School.objects.all()
    serializer_class = SchoolSerializer
    permission_classes = [IsSuperAdmin]

@method_decorator(cache_page(60 * 5), name='list')
class SubscriptionPlanViewSet(viewsets.ModelViewSet):
    """Retired catalogue: fixed subscription plans are replaced by the wallet.

    Reads return an empty list; writes are gone. Rows are preserved for
    historical payments.
    """

    queryset = SubscriptionPlan.objects.none()
    serializer_class = SubscriptionPlanSerializer

    def get_permissions(self):
        if self.action in ('list', 'retrieve'):
            return [AllowAny()]
        return [IsSuperAdmin()]

    def get_serializer_class(self):
        if self.action in ('list', 'retrieve'):
            return PublicPlanSerializer
        return PlatformPlanSerializer

    def get_queryset(self):
        return SubscriptionPlan.objects.none()


class SchoolProfileView(APIView):
    """GET/PATCH the caller's own school profile (the Settings screen).

    The school always comes from ``request.user.school_id``. An ``id``,
    ``school`` or ``schoolId`` in the body is refused rather than ignored, so a
    payload can never move the profile onto another tenant. The logo rides the
    application's normal storage field, never base64 in the database.
    """

    def get_permissions(self):
        if self.request.method == 'GET':
            return [IsAuthenticated(), HasSchool(), require_permissions('settings.read')()]
        return [IsAuthenticated(), HasSchool(), require_permissions('settings.write')()]

    def get(self, request):
        return Response(SchoolSessionSerializer(request.user.school).data)

    def patch(self, request):
        for key in ('id', 'school', 'schoolId', 'school_id'):
            if key in request.data:
                raise ValidationError({
                    key: 'This is your own school profile and cannot be reassigned here.',
                })
        school = request.user.school
        tracked = ('name', 'address', 'phone', 'email', 'school_type')
        before = {key: str(getattr(school, key) or '') for key in tracked}
        before['logo'] = str(school.logo or '')
        serializer = SchoolSerializer(school, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        updated = serializer.save()
        after = {key: str(getattr(updated, key) or '') for key in tracked}
        after['logo'] = str(updated.logo or '')
        changed = {
            key: {'before': before[key], 'after': after[key]}
            for key in after if before[key] != after[key]
        }
        if changed:
            audit(
                request, 'school.profile.updated', updated.name,
                'School profile updated', entity='school', entity_id=str(updated.pk),
                after=changed,
            )
        # The session shape, not the raw model serializer: the frontend merges
        # this straight back into its stored school.
        return Response(SchoolSessionSerializer(updated).data)


class ReverseGeocodeView(APIView):
    """GET /schools/reverse-geocode/?lat=&lng= → a human-readable place.

    Proxied through the backend so the browser never calls a third-party
    geocoder directly (no third-party script, no vendor keys, one place to add
    caching). Any authenticated member of a school may use it: a teacher
    checking in needs to see the campus label. It reads and writes no tenant
    data, so it does not require a granular permission.
    """

    permission_classes = [IsAuthenticated, HasSchool]

    def get(self, request):
        raw_lat = (request.query_params.get('lat') or '').strip()
        raw_lng = (request.query_params.get('lng') or '').strip()
        try:
            latitude = float(raw_lat)
            longitude = float(raw_lng)
        except (TypeError, ValueError):
            raise ValidationError({
                'lat': 'Provide numeric lat and lng query parameters.',
            })
        if not (-90 <= latitude <= 90) or not (-180 <= longitude <= 180):
            raise ValidationError({'lat': 'Coordinates are out of range.'})
        return Response({'location': reverse_geocode(latitude, longitude)})


class SchoolRegisterView(APIView):
    """POST /schools/register/  → {schoolId, paymentRef}

    Accepts the frontend's nested OnboardingPayload.
    """
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = SchoolRegistrationSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                {
                    'detail': 'Could not register this school. Check the highlighted fields.',
                    'errors': serializer.errors,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        result = serializer.save()
        return Response(result, status=status.HTTP_201_CREATED)


class PaymentVerifyView(APIView):
    """GET /payments/{reference}/verify/  → {status}

    Until a trusted payment gateway is integrated, payment status remains
    pending. A client-supplied reference is not proof of payment.
    """
    permission_classes = [AllowAny]

    def get(self, request, reference):
        return Response({'status': 'pending'})
