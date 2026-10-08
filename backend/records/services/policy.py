"""Central policy/business-rule enforcement for the School OS.

Every protected operation must validate, in order:

    authenticated user -> permission -> school ownership ->
    resource relationship -> business rule -> action

Row-level school ownership stays inline at each call site via
``get_object_or_404(..., school_id=request.user.school_id)`` (the established
pattern across views.py): querysets confined that way can never leak another
tenant however the client crafts its IDs.

This module hosts the *relationship and business* rules that more than one
view needs, so the same rule is not reimplemented in unrelated places:

- parent -> student links (every parent endpoint answers 404, never 403, so
  a parent cannot learn whether an id exists at all);
- teacher -> class scope for result sheets (mirrors the attendance
  class-teacher rule, but for result entry the subject teacher's taught-class
  list counts too);
- financial history guards (money that has moved is history and cannot be
  rewritten).

When a rule already lives in a domain service (attendance submission,
enrollment, admission numbers, result lifecycle), this module reuses it
instead of competing with it.
"""

from django.http import Http404
from rest_framework.exceptions import PermissionDenied, ValidationError

from ..models import ClassTeacherAssignment
from . import billing as billing_service
from . import parent_portal as parent_portal_service


def require_linked_child(user, student_id):
    """The parent's linked student, or 404.

    The single gate for every parent child endpoint. An unlinked id and a
    cross-school id both read as "not there": the response must never confirm
    that the student exists.
    """
    student = parent_portal_service.linked_child(user, student_id)
    if student is None:
        raise Http404
    return student


def require_teacher_class_scope(*, user, school, class_obj, session, action='work on'):
    """Teachers may only enter results for classes in their academic context.

    A school administrator always passes (the same override the attendance
    register grants them). A teacher passes when the class is on their staff
    record's taught-class list or they hold the class-teacher designation for
    the sheet's session. Anything else is refused loudly so the teacher knows
    to ask an administrator for the assignment rather than failing silently.
    """
    if user.role == 'school_admin':
        return
    staff_id = getattr(user, 'staff_profile_id', None)
    if user.role == 'teacher' and staff_id is not None:
        staff = getattr(user, 'staff_profile', None)
        taught = set(getattr(staff, 'classes', None) or [])
        if class_obj.name in taught:
            return
        designated = ClassTeacherAssignment.objects.filter(
            school=school,
            class_obj=class_obj,
            staff_id=staff_id,
            academic_session=session,
        ).exists()
        if designated:
            return
        raise PermissionDenied(
            f'You are not assigned to teach {class_obj.name}, so you cannot {action} '
            'its result sheet. Ask your administrator to assign your classes.',
        )
    raise PermissionDenied(
        f'You do not have permission to {action} this result sheet.',
    )


def assert_invoice_rewritable(invoice, description='This invoice'):
    """An invoice with verified money movement is history, not a draft.

    Re-issuing (overwrite) re-syncs charges from the current Payment Structure,
    which is legitimate for an untouched invoice but must never rewrite amounts
    a family has already paid against. Paid invoices therefore fail loudly here
    instead of being silently rewritten.
    """
    if billing_service.verified_paid_total(invoice.id) > 0:
        raise ValidationError({
            'overwrite': (
                f'{description} already has recorded payments, so its charged '
                'amounts are now history and cannot be rewritten.'
            ),
        })
