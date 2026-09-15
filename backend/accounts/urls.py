from django.urls import path
from . import views

urlpatterns = [
    path('school/register/', views.SchoolRegistrationView.as_view(), name='school-register'),
    path('login/', views.LoginView.as_view(), name='login'),
    path('logout/', views.LogoutView.as_view(), name='logout'),
    path('token/refresh/', views.CookieTokenRefreshView.as_view(), name='token-refresh'),
    path('me/', views.MeView.as_view(), name='me'),
    path('profile/', views.ProfileView.as_view(), name='profile'),
    path('change-password/', views.ChangePasswordView.as_view(), name='change-password'),
    path('verify-email/', views.VerifyEmailRequestView.as_view(), name='verify-email-request'),
    path('verify-email/confirm/', views.VerifyEmailConfirmView.as_view(), name='verify-email-confirm'),
    path('password-reset/', views.PasswordResetRequestView.as_view(), name='password-reset-request'),
    path('password-reset/confirm/', views.PasswordResetConfirmView.as_view(), name='password-reset-confirm'),
]
