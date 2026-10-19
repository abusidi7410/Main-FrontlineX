from django.urls import path

from . import views

urlpatterns = [
    path('applications/', views.AdmissionApplicationListCreateView.as_view()),
    path('applications/<uuid:public_id>/', views.AdmissionApplicationDetailView.as_view()),
    path('applications/<uuid:public_id>/submit/', views.AdmissionSubmitView.as_view()),
    path(
        'applications/<uuid:public_id>/start-review/',
        views.AdmissionStartReviewView.as_view(),
    ),
    path('applications/<uuid:public_id>/approve/', views.AdmissionApproveView.as_view()),
    path('applications/<uuid:public_id>/reject/', views.AdmissionRejectView.as_view()),
    path('applications/<uuid:public_id>/withdraw/', views.AdmissionWithdrawView.as_view()),
    path(
        'applications/<uuid:public_id>/documents/',
        views.AdmissionDocumentListView.as_view(),
    ),
    path('documents/<uuid:public_id>/', views.AdmissionDocumentDetailView.as_view()),
    path(
        'documents/<uuid:public_id>/review/',
        views.AdmissionDocumentReviewView.as_view(),
    ),
    path(
        'documents/<uuid:public_id>/download/',
        views.AdmissionDocumentDownloadView.as_view(),
    ),
    path('stats/', views.AdmissionStatsView.as_view()),
    path('settings/', views.AdmissionSettingsView.as_view()),
]
