from django.utils.decorators import method_decorator
from django.views.decorators.cache import cache_page
from rest_framework import status, viewsets
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.permissions import IsSuperAdmin
from .models import School, SubscriptionPlan
from .serializers import (
    SchoolRegistrationSerializer,
    SchoolSerializer,
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
    """Plans are public so the onboarding flow can read them.

    The list is cached in Redis for 5 minutes since plans change rarely.
    """
    queryset = SubscriptionPlan.objects.filter(is_active=True)
    serializer_class = SubscriptionPlanSerializer
    permission_classes = [AllowAny]


class SchoolRegisterView(APIView):
    """POST /schools/register/  → {schoolId, paymentRef}

    Accepts the frontend's nested OnboardingPayload.
    """
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = SchoolRegistrationSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({'errors': serializer.errors}, status=status.HTTP_400_BAD_REQUEST)
        result = serializer.save()
        return Response(result, status=status.HTTP_201_CREATED)


class PaymentVerifyView(APIView):
    """GET /payments/{reference}/verify/  → {status}

    A real gateway integration will confirm bank transfers. For now any
    reference that matches a registered school is considered verified.
    """
    permission_classes = [AllowAny]

    def get(self, request, reference):
        slug = reference.lower().lstrip('fn-') if reference else ''
        school = School.objects.filter(slug=slug).first()
        if school is None:
            return Response({'status': 'pending'})
        return Response({'status': 'verified'})
