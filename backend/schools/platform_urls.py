from django.urls import path

from . import platform_views, subscription_views

urlpatterns = [
    path('overview/', platform_views.PlatformOverviewView.as_view()),
    path('schools/', platform_views.PlatformSchoolListView.as_view()),
    path('profit/', platform_views.PlatformProfitView.as_view()),
    # Subscription controls: the plan editor, per-school subscription, and the
    # transactions ledger.
    path('plans/', subscription_views.PlatformPlanListCreateView.as_view()),
    path('plans/<int:pk>/', subscription_views.PlatformPlanDetailView.as_view()),
    path('subscriptions/payments/', subscription_views.PlatformPaymentListView.as_view()),
    path('schools/<str:pk>/subscription/', subscription_views.PlatformSchoolSubscriptionView.as_view()),
    path('schools/<str:pk>/impersonate/', platform_views.PlatformImpersonationView.as_view()),
    path('schools/<str:pk>/users/', platform_views.PlatformSchoolUsersView.as_view()),
    path('users/<str:pk>/', platform_views.PlatformUserDetailView.as_view()),
    path('schools/<str:pk>/status/', platform_views.PlatformSchoolStatusView.as_view()),
    path('schools/<str:pk>/', platform_views.PlatformSchoolDetailView.as_view()),
    path('support/tickets/', platform_views.PlatformSupportTicketListView.as_view()),
    path('support/tickets/<str:pk>/status/', platform_views.PlatformSupportTicketStatusView.as_view()),
    path('support/announcements/', platform_views.PlatformAnnouncementListView.as_view()),
    path('audit/', platform_views.PlatformAuditListView.as_view()),
]