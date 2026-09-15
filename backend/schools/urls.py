from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

router = DefaultRouter()
router.register('schools', views.SchoolViewSet)
router.register('plans', views.SubscriptionPlanViewSet)

urlpatterns = [
    path('register/', views.SchoolRegisterView.as_view(), name='register'),
    path('payments/<str:reference>/verify/', views.PaymentVerifyView.as_view(), name='payment-verify'),
    path('', include(router.urls)),
]
