"""What a school's status means — the single definition both sides read.

`schools.platform_views` shows these statuses to the platform manager, and the
`accounts` auth stack uses them to decide whether anybody may sign in to the
school. If the two definitions ever drifted, the dashboard could report a school
as active while its staff were already locked out (or the reverse), so neither
side is allowed to spell the rules out for itself.
"""
from __future__ import annotations

from .models import SchoolSubscription

# Shown to anyone who authenticates to a school the platform has suspended.
# The credentials were valid, so there is nothing to hide here — the school,
# not the account, is what is blocked.
SUSPENDED_DETAIL = (
    'This school has been suspended. Contact your school administrator to have '
    'it reinstated.'
)
# Machine-readable counterpart, carried in the response `code` so the client can
# recognise this case without matching on the wording above.
SUSPENDED_CODE = 'school_suspended'


def school_status(school, subscription):
    """Platform-facing status for a school: active | trial | pending_payment | suspended."""
    if school.is_active:
        return 'active'
    if subscription:
        if subscription.status == SchoolSubscription.Status.SUSPENDED:
            return 'suspended'
        if subscription.status in (
            SchoolSubscription.Status.PENDING,
            SchoolSubscription.Status.EXPIRED,
        ):
            return 'pending_payment'
    return 'trial'


def is_suspended_school(school_id) -> bool:
    """True when nobody may sign in to this school, its tokens are worthless.

    Only the platform's explicit `suspended` state counts. A school that has
    simply not been switched on yet (`is_active=False` with a pending
    subscription) is ordinary onboarding: its staff still have to be able to log
    in to set the place up, so it is deliberately not blocked here.
    """
    if not school_id:
        return False
    return SchoolSubscription.objects.filter(
        school_id=school_id,
        status=SchoolSubscription.Status.SUSPENDED,
    ).exists()
