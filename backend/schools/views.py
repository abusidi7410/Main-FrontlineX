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
    """Plans are readable by anyone so the onboarding flow can show pricing.

    The list is cached in Redis for 5 minutes since plans change rarely.

    Only the platform superadmin may change pricing. This used to be a plain
    `AllowAny` on a full ModelViewSet, which let an anonymous caller create,
    rewrite and delete the commercial plan data.
    """

    queryset = SubscriptionPlan.objects.filter(is_active=True)
    serializer_class = SubscriptionPlanSerializer

    def get_permissions(self):
        if self.action in ('list', 'retrieve'):
            return [AllowAny()]
        return [IsSuperAdmin()]


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

    Until a trusted payment gateway is integrated, payment status remains
    pending. A client-supplied reference is not proof of payment.
    """
    permission_classes = [AllowAny]

    def get(self, request, reference):
        return Response({'status': 'pending'})
