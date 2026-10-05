from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.authentication import JWTAuthentication

from schools.status import SUSPENDED_CODE, SUSPENDED_DETAIL, is_suspended_school


class SchoolAccessJWTAuthentication(JWTAuthentication):
    """Access tokens become worthless the moment the school is suspended.

    Sign-in and refresh are gated separately; this is what stops a token that
    was issued *before* the suspension from still working for the rest of its
    lifetime. Platform staff have no school and are unaffected, so they can
    always suspend and reinstate one.
    """

    def get_user(self, validated_token):
        user = super().get_user(validated_token)
        if user is not None and is_suspended_school(getattr(user, 'school_id', None)):
            raise AuthenticationFailed(SUSPENDED_DETAIL, code=SUSPENDED_CODE)
        return user
