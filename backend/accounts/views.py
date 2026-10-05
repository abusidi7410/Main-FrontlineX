import logging

from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.conf import settings
from django.db import DatabaseError
from django.utils import timezone
from django.utils.encoding import force_str
from django.utils.http import urlsafe_base64_decode
from rest_framework import status
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken, TokenError

from schools.serializers import SchoolSessionSerializer
from schools.status import SUSPENDED_DETAIL, is_suspended_school
from .email import send_password_reset_email, send_verification_email
from .serializers import (
    AuthUserSerializer,
    ChangePasswordSerializer,
    LoginSerializer,
    PasswordResetConfirmSerializer,
    PasswordResetRequestSerializer,
    ProfilePhotoUploadSerializer,
    SchoolRegistrationSerializer,
    UserSerializer,
    VerifyEmailConfirmSerializer,
    VerifyEmailRequestSerializer,
)
from .services import profile_photos
from .validators import normalize_phone

User = get_user_model()
logger = logging.getLogger(__name__)

_REFRESH_COOKIE_PATH = '/api/v1/auth/'


def _set_refresh_cookie(response, refresh_token):
    response.set_cookie(
        'refresh_token',
        str(refresh_token),
        httponly=True,
        secure=not settings.DEBUG,
        samesite='Lax',
        max_age=settings.SIMPLE_JWT['REFRESH_TOKEN_LIFETIME'].total_seconds(),
        path=_REFRESH_COOKIE_PATH,
    )
    return response


def _issue_tokens(user):
    refresh = RefreshToken.for_user(user)
    return str(refresh.access_token), refresh


def _client_ip(request):
    """The caller's address, honouring the proxy header Railway and friends set.

    The left-most entry is the original client; the rest are proxies we added.
    """
    forwarded = request.META.get('HTTP_X_FORWARDED_FOR')
    if forwarded:
        return forwarded.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR') or ''


def _record_login(request, user):
    """Stamp this sign-in and tell the account if it came from somewhere new.

    `last_login` is maintained by hand because this endpoint authenticates a JWT
    directly and never calls `django.contrib.auth.login()`, so nothing else would
    update it. A `security` notification is raised only when a *previous* address
    is on record and differs — the first ever sign-in from a device is the normal
    case, and warning about it would train people to ignore the warning.
    """
    address = _client_ip(request)
    previous = user.last_login_ip
    user.last_login = timezone.now()
    if address:
        user.last_login_ip = address
    user.save(update_fields=['last_login', 'last_login_ip'])

    if previous and address and previous != address:
        # Imported here rather than at module scope: records.services imports
        # accounts.services, so a top-level import would be circular.
        from records.services import events as event_service
        event_service.new_login(user, ip=address, previous_ip=previous)


def _session_payload(user, access_token):
    """Frontend Session shape: {user, school, token}."""
    return {
        'token': access_token,
        'user': AuthUserSerializer(user).data,
        'school': (
            SchoolSessionSerializer(user.school).data
            if user.school_id else None
        ),
    }


# ── Registration ──────────────────────────────────────────────────────────────

class SchoolRegistrationView(APIView):
    """POST /auth/school/register/
    Creates a pending School + first Admin. Access is enabled only after
    payment is confirmed through a trusted gateway.
    """
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = SchoolRegistrationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        _, school = serializer.save()

        return Response({
            'detail': 'School registration received. Payment confirmation is pending.',
            'school': {'id': school.id, 'name': school.name, 'slug': school.slug},
            'status': 'pending',
        }, status=status.HTTP_201_CREATED)


# ── Login / Logout / Refresh ─────────────────────────────────────────────────

class LoginView(APIView):
    """POST /auth/login/  → Session {user, school, token} + refresh cookie"""
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        identifier = serializer.validated_data['identifier']
        password = serializer.validated_data['password']

        user = authenticate_by_login(identifier, password)

        if user is None:
            return Response(
                {'detail': 'Invalid credentials.'},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        if not user.is_active:
            return Response(
                {'detail': 'Account is deactivated. Contact support.'},
                status=status.HTTP_403_FORBIDDEN,
            )

        # Suspension belongs to the school, so it blocks every account in it at
        # once. Checked before any token is minted: a suspended school must not
        # be able to obtain credentials at all, not merely find them refused
        # afterwards. Platform staff have no school and are never blocked.
        if is_suspended_school(user.school_id):
            return Response(
                {'detail': SUSPENDED_DETAIL},
                status=status.HTTP_403_FORBIDDEN,
            )

        access_token, refresh = _issue_tokens(user)
        _record_login(request, user)
        resp = Response(_session_payload(user, access_token))
        return _set_refresh_cookie(resp, refresh)


class LogoutView(APIView):
    """POST /auth/logout/  → blacklists refresh cookie"""
    permission_classes = [AllowAny]

    def post(self, request):
        refresh_token = request.COOKIES.get('refresh_token')

        resp = Response({'detail': 'Successfully logged out.'})
        resp.delete_cookie('refresh_token', path=_REFRESH_COOKIE_PATH)

        if refresh_token:
            try:
                RefreshToken(refresh_token).blacklist()
            except Exception:
                pass  # token already expired / blacklisted

        return resp


class CookieTokenRefreshView(APIView):
    """POST /auth/token/refresh/
    Reads the refresh token from the httpOnly cookie, returns a fresh access
    token, rotates the refresh token, and blacklists the old one.
    """
    permission_classes = [AllowAny]

    def post(self, request):
        raw = request.COOKIES.get('refresh_token')
        if not raw:
            return Response(
                {'detail': 'No refresh token provided.'},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        try:
            refresh = RefreshToken(raw)
            access_token = str(refresh.access_token)
        except TokenError:
            return Response(
                {'detail': 'Invalid or expired refresh token.'},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        # A suspended school must not refresh its way back in. The tokens this
        # would mint are refused on use anyway (accounts.authentication), but
        # refusing here too takes the cookie back instead of leaving it live
        # until it expires.
        claims = getattr(refresh, 'payload', None) or {}
        user_id = claims.get(settings.SIMPLE_JWT.get('USER_ID_CLAIM', 'user_id'))
        school_id = (
            User.objects.filter(pk=user_id).values_list('school_id', flat=True).first()
            if user_id is not None
            else None
        )
        if is_suspended_school(school_id):
            resp = Response(
                {'detail': SUSPENDED_DETAIL},
                status=status.HTTP_401_UNAUTHORIZED,
            )
            resp.delete_cookie('refresh_token', path=_REFRESH_COOKIE_PATH)
            return resp

        # Blacklist the OLD token first so a stolen/used refresh cannot be
        # replayed once it has been used to obtain a new pair.
        if settings.SIMPLE_JWT.get('BLACKLIST_AFTER_ROTATION', False):
            try:
                RefreshToken(raw).blacklist()
            except Exception:
                pass  # already blacklisted or expired

        # Rotate: give the refresh token a fresh jti / iat / exp.
        refresh.set_jti()
        refresh.set_iat()
        refresh.set_exp()
        new_refresh = str(refresh)

        resp = Response({'access': access_token})
        return _set_refresh_cookie(resp, new_refresh)


# ── Profile / password ───────────────────────────────────────────────────────

class MeView(APIView):
    """GET /auth/me/"""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = User.objects.select_related('school').get(pk=request.user.pk)
        return Response(_session_payload(user, ''))


class ProfileView(APIView):
    """PATCH /auth/profile/  {fullName, phone} → AuthUser"""
    permission_classes = [IsAuthenticated]

    def patch(self, request):
        full_name = request.data.get('fullName')
        phone = request.data.get('phone')
        user = User.objects.get(pk=request.user.pk)

        if full_name is not None:
            parts = full_name.split(' ', 1)
            user.first_name = parts[0] if parts else ''
            user.last_name = parts[1] if len(parts) > 1 else ''
        if phone is not None:
            user.phone = normalize_phone(phone) or None
        user.save(update_fields=['first_name', 'last_name', 'phone', 'updated_at'])

        return Response(AuthUserSerializer(user).data)


class ProfilePhotoView(APIView):
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request):
        serializer = ProfilePhotoUploadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = User.objects.get(pk=request.user.pk)
        previous_public_id = user.profile_photo_public_id

        try:
            public_id = profile_photos.upload_profile_photo(
                serializer.validated_data['photo'],
                user_id=user.pk,
            )
        except profile_photos.StorageNotConfigured as exc:
            return Response(
                {'detail': str(exc)},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        except profile_photos.StorageError:
            logger.exception('Profile photo upload failed for user %s.', user.pk)
            return Response(
                {'detail': 'The profile photo could not be uploaded. Please try again.'},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        user.profile_photo_public_id = public_id
        try:
            user.save(update_fields=['profile_photo_public_id', 'updated_at'])
        except DatabaseError:
            try:
                profile_photos.delete_profile_photo(public_id)
            except profile_photos.StorageError:
                logger.exception(
                    'Could not clean up profile photo %s after saving user %s failed.',
                    public_id, user.pk,
                )
            raise

        if previous_public_id:
            try:
                profile_photos.delete_profile_photo(previous_public_id)
            except profile_photos.StorageError:
                logger.exception(
                    'Could not remove replaced profile photo %s for user %s.',
                    previous_public_id, user.pk,
                )

        return Response(AuthUserSerializer(user).data)

    def delete(self, request):
        user = User.objects.get(pk=request.user.pk)
        previous_public_id = user.profile_photo_public_id
        if previous_public_id:
            user.profile_photo_public_id = ''
            user.save(update_fields=['profile_photo_public_id', 'updated_at'])
            try:
                profile_photos.delete_profile_photo(previous_public_id)
            except profile_photos.StorageError:
                logger.exception(
                    'Could not remove profile photo %s for user %s.',
                    previous_public_id, user.pk,
                )
        return Response(AuthUserSerializer(user).data)


class ChangePasswordView(APIView):
    """POST /auth/change-password/  {current, next} → {ok: true}"""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = ChangePasswordSerializer(
            data=request.data, context={'request': request},
        )
        serializer.is_valid(raise_exception=True)

        request.user.set_password(serializer.validated_data['next'])
        request.user.save(update_fields=['password'])
        # A password change is the one security event the account holder can act
        # on immediately, so it goes to their own inbox as proof of the change.
        from records.services import events as event_service
        event_service.password_changed(request.user)

        return Response({'ok': True, 'detail': 'Password changed successfully.'})


# ── Email verification ───────────────────────────────────────────────────────

class VerifyEmailRequestView(APIView):
    """POST /auth/verify-email/  → sends verification email"""
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = VerifyEmailRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            user = User.objects.get(email=serializer.validated_data['email'])
            send_verification_email(user, request)
        except User.DoesNotExist:
            pass  # never reveal whether the email exists

        return Response({
            'detail': 'If the email exists, a verification link has been sent.',
        })


class VerifyEmailConfirmView(APIView):
    """POST /auth/verify-email/confirm/  → validates uid+token, marks verified"""
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = VerifyEmailConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            uid = force_str(urlsafe_base64_decode(serializer.validated_data['uid']))
            user = User.objects.get(pk=uid)
        except (TypeError, ValueError, OverflowError, User.DoesNotExist):
            user = None

        if user is not None and default_token_generator.check_token(
            user, serializer.validated_data['token'],
        ):
            user.is_verified = True
            user.save(update_fields=['is_verified'])
            return Response({'detail': 'Email verified successfully.'})

        return Response(
            {'detail': 'Invalid or expired verification link.'},
            status=status.HTTP_400_BAD_REQUEST,
        )


# ── Password reset ───────────────────────────────────────────────────────────

class PasswordResetRequestView(APIView):
    """POST /auth/password-reset/  {email} → {sent: true}"""
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = PasswordResetRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            user = User.objects.get(email=serializer.validated_data['email'])
            send_password_reset_email(user, request)
        except User.DoesNotExist:
            pass

        return Response({'sent': True, 'detail': 'If the email exists, a reset link has been sent.'})


class PasswordResetConfirmView(APIView):
    """POST /auth/password-reset/confirm/  {token, password} → {ok: true}

    ``token`` is the combined ``<uid64>.<token>`` from the email link.
    """
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = PasswordResetConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        combined = serializer.validated_data['token']
        uid = None
        if '.' in combined:
            uid_b64, token = combined.split('.', 1)
            try:
                uid = force_str(urlsafe_base64_decode(uid_b64))
            except (TypeError, ValueError, OverflowError):
                uid = None
        else:
            token = combined

        user = None
        if uid:
            try:
                user = User.objects.get(pk=uid)
            except (TypeError, ValueError, OverflowError, User.DoesNotExist):
                user = None

        if user is not None and default_token_generator.check_token(user, token):
            user.set_password(serializer.validated_data['password'])
            user.save(update_fields=['password'])
            return Response({'ok': True, 'detail': 'Password reset successful. You can now log in.'})

        return Response(
            {'detail': 'Invalid or expired reset link.'},
            status=status.HTTP_400_BAD_REQUEST,
        )


# ── Helper ───────────────────────────────────────────────────────────────────

def authenticate_by_login(login_id, password):
    """Resolve a user by email or phone and verify the password directly.

    Uses the custom backend's lookup logic but avoids Django's
    ``authenticate()``, which only forwards ``USERNAME_FIELD`` (email)
    through the backend and therefore cannot match on phone.
    """
    login_id = login_id.strip()
    queryset = User.objects.select_related('school')
    if '@' in login_id:
        matches = list(queryset.filter(email__iexact=login_id)[:2])
    else:
        matches = list(queryset.filter(phone=normalize_phone(login_id))[:2])
    if len(matches) != 1:
        # Run the default password hasher once to reduce the timing
        # difference between existing and non-existing users, and refuse
        # ambiguous legacy email matches rather than selecting an account.
        User().set_password(password)
        return None
    user = matches[0]

    if user.check_password(password) and user.is_active:
        return user
    return None
