from django.urls import path

from . import account_views

urlpatterns = [
    path('users/', account_views.AccountListView.as_view()),
    path('users/stats/', account_views.AccountStatsView.as_view()),
    path('users/<str:pk>/', account_views.AccountDetailView.as_view()),
    path('users/<str:pk>/reset-password/', account_views.AccountPasswordResetView.as_view()),
    path(
        'users/<str:pk>/<str:action>/',
        account_views.AccountStatusView.as_view(),
    ),
]
