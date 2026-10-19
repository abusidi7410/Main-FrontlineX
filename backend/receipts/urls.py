from django.urls import path

from . import views

urlpatterns = [
    path('', views.ReceiptListView.as_view()),
    path('issue/', views.ReceiptIssueView.as_view()),
    path('stats/', views.ReceiptStatsView.as_view()),
    path('settings/', views.ReceiptSettingsView.as_view()),
    path('<uuid:public_id>/', views.ReceiptDetailView.as_view()),
    path('<uuid:public_id>/reprint/', views.ReceiptReprintView.as_view()),
    path('<uuid:public_id>/void/', views.ReceiptVoidView.as_view()),
    path('<uuid:public_id>/download/', views.ReceiptDownloadView.as_view()),
]
