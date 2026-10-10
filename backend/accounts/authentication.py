from rest_framework.exceptions import AuthenticationFailed, PermissionDenied
from rest_framework.permissions import SAFE_METHODS
from rest_framework_simplejwt.authentication import JWTAuthentication

from schools.status import SUSPENDED_CODE, SUSPENDED_DETAIL, is_suspended_school


class SchoolAccessJWTAuthentication(JWTAuthentication):
    """Access tokens become worthless the moment the school is suspended.

    Sign-in and refresh are gated separately; this is what stops a token that
    was issued *before* the suspension from still working for the rest of its
    lifetime. Platform staff have no school and are unaffected, so they can
    always suspend and reinstate one.

    The same hook enforces read-only impersonation: a token a platform manager
    minted to *look at* a school carries an ``imp`` claim, and any write with
    such a token is refused here rather than trusted to each view.
    """

    def get_user(self, validated_token):
        user = super().get_user(validated_token)
        if user is not None and is_suspended_school(getattr(user, 'school_id', None)):
            raise AuthenticationFailed(SUSPENDED_DETAIL, code=SUSPENDED_CODE)
        return user

    def authenticate(self, request):
        result = super().authenticate(request)
        if result is None:
            return None
        user, token = result
        impersonated_by = token.get('imp')
        if impersonated_by:
            if request.method not in SAFE_METHODS:
                raise PermissionDenied(
                    'This is a read-only view of the school and cannot be changed.'
                )
            user._impersonated_by = impersonated_by
            user._impersonation_read_only = bool(token.get('ro'))
        return user, token
