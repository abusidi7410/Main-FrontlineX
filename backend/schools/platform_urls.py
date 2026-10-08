from django.urls import path

from . import platform_views

urlpatterns = [
    path('overview/', platform_views.PlatformOverviewView.as_view()),
    path('schools/', platform_views.PlatformSchoolListView.as_view()),
    path('profit/', platform_views.PlatformProfitView.as_view()),
    path('schools/<str:pk>/status/', platform_views.PlatformSchoolStatusView.as_view()),
    path('schools/<str:pk>/', platform_views.PlatformSchoolDetailView.as_view()),
    path('support/tickets/', platform_views.PlatformSupportTicketListView.as_view()),
    path('support/tickets/<str:pk>/status/', platform_views.PlatformSupportTicketStatusView.as_view()),
    path('support/announcements/', platform_views.PlatformAnnouncementListView.as_view()),
    path('audit/', platform_views.PlatformAuditListView.as_view()),
]