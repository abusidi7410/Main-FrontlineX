from django.contrib.auth.tokens import default_token_generator
from django.core.mail import send_mail
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

_DEFAULT_FROM = 'noreply@frontlinenexus.com'
_FRONTEND_BASE = 'http://localhost:5173'


def _build_url(base_url, uid, token, path_prefix):
    return f'{base_url}/{path_prefix}/{uid}/{token}/'


def send_verification_email(user, request=None):
    token = default_token_generator.make_token(user)
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    base = _get_base_url(request)
    url = _build_url(base, uid, token, 'auth/verify-email')

    send_mail(
        subject='Verify your Frontline Nexus account',
        message=(
            f'Hello {user.get_full_name()},\n\n'
            f'Click the link below to verify your account:\n\n'
            f'{url}\n\n'
            f'If you did not create this account, please ignore this email.\n\n'
            f'— Frontline Nexus Team'
        ),
        from_email=_DEFAULT_FROM,
        recipient_list=[user.email],
        fail_silently=True,
    )


def send_password_reset_email(user, request=None):
    """Sends a frontend-friendly reset link: /reset-password?token=<uid>.<token>"""
    token = default_token_generator.make_token(user)
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    combined = f'{uid}.{token}'
    url = f'{_FRONTEND_BASE}/reset-password?token={combined}'

    send_mail(
        subject='Reset your Frontline Nexus password',
        message=(
            f'Hello {user.get_full_name()},\n\n'
            f'Click the link below to reset your password:\n\n'
            f'{url}\n\n'
            f'If you did not request a password reset, please ignore this email.\n\n'
            f'— Frontline Nexus Team'
        ),
        from_email=_DEFAULT_FROM,
        recipient_list=[user.email],
        fail_silently=True,
    )


def _get_base_url(request):
    if request:
        scheme = 'https' if request.is_secure() else 'http'
        return f'{scheme}://{request.get_host()}'
    return _FRONTEND_BASE
