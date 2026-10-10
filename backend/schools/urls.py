from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import subscription_views, views

router = DefaultRouter()
router.register('schools', views.SchoolViewSet)
router.register('plans', views.SubscriptionPlanViewSet)

urlpatterns = [
    path('register/', views.SchoolRegisterView.as_view(), name='register'),
    path('payments/<str:reference>/verify/', views.PaymentVerifyView.as_view(), name='payment-verify'),
    # Subscription payments (Paystack): start a checkout, confirm it, and the
    # signed server callback.
    path('subscriptions/checkout/', subscription_views.SubscriptionCheckoutView.as_view(), name='subscription-checkout'),
    path('subscriptions/verify/<str:reference>/', subscription_views.SubscriptionVerifyView.as_view(), name='subscription-verify'),
    path('subscriptions/webhook/', subscription_views.SubscriptionWebhookView.as_view(), name='subscription-webhook'),
    # Declared before the router so `profile` is not swallowed by `schools/<pk>/`.
    path('profile/', views.SchoolProfileView.as_view(), name='school-profile'),
    path('schools/profile/', views.SchoolProfileView.as_view(), name='school-profile-alt'),
    path('reverse-geocode/', views.ReverseGeocodeView.as_view(), name='reverse-geocode'),
    path('', include(router.urls)),
]
