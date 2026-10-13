from django.urls import path

from . import platform_views, views

urlpatterns = [
    # School wallet
    path('wallet/', views.WalletView.as_view()),
    path('transactions/', views.WalletTransactionListView.as_view()),
    # Deposits (Paystack)
    path('deposits/', views.DepositCheckoutView.as_view()),
    path('deposits/verify/<str:reference>/', views.DepositVerifyView.as_view()),
    path('deposits/webhook/', views.DepositWebhookView.as_view()),
    # Student access
    path('students/', views.StudentAccessListView.as_view()),
    path('students/<str:pk>/activate/', views.StudentActivateView.as_view()),
    # SME alerts (school)
    path('messaging/', views.MessagingView.as_view()),
    path('alerts/', views.AlertSendView.as_view()),
    path('alerts/history/', views.AlertListView.as_view()),
    # Platform controls
    path('platform/pricing/', platform_views.PricingView.as_view()),
    path(
        'platform/schools/<str:pk>/messaging/',
        platform_views.SchoolMessagingView.as_view(),
    ),
    path('platform/messaging/', platform_views.MessagingOverviewView.as_view()),
    path('platform/adjustments/', platform_views.ManualAdjustmentView.as_view()),
    path('platform/complimentary/', platform_views.ComplimentaryAccessView.as_view()),
]
