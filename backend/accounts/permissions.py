from rest_framework.permissions import BasePermission


# Mirrors the frontend role→permission matrix (src/permissions/index.ts).
# The API is the authority; this is used to populate AuthUser.permissions
# in serializer output.
#
# Admission/finance permissions (spec §39) are deliberately granular: a role
# that may register a student does NOT thereby gain the right to approve that
# student's registration, record a payment, or verify a payment.
#   students.register     — create a new-student registration
#   students.approve      — approve a pending registration (activates enrolment)
#   students.import       — bulk upload / migrate existing students (ADMIN ONLY)
#   enrollment.manage     — directly manage enrolments
#   finance.structure     — configure the Payment Structure
#   finance.invoice       — create / manage invoices
#   finance.payment       — record a payment
#   finance.verify        — verify / reverse a payment
#   finance.read          — view financial records
ROLE_PERMISSIONS = {
    'platform_manager': [
        'platform.manage', 'subscription.read', 'subscription.write',
        'audit.read', 'reports.read', 'ai.platform',
        'settings.read', 'settings.write',
    ],
    'school_admin': [
        'students.read', 'students.write', 'students.register', 'students.approve',
        'students.import', 'enrollment.manage',
        'staff.read', 'staff.write',
        'accounts.read', 'accounts.write',
        'academics.read', 'academics.write',
        'attendance.read', 'attendance.write', 'attendance.correct',
        'results.read', 'results.write', 'results.approve', 'results.publish',
        'finance.read', 'finance.write', 'finance.verify',
        'finance.structure', 'finance.invoice', 'finance.payment',
        'timetable.read', 'timetable.write',
        'lessonplans.read', 'lessonplans.write',
        'communication.read', 'communication.write',
        'reports.read', 'subscription.read', 'subscription.write',
        'settings.read', 'settings.write', 'audit.read',
        'ai.academic', 'ai.finance', 'ai.teaching',
    ],
    'principal': [
        'students.read', 'students.write', 'students.register',         'students.approve',
        'staff.read', 'staff.write',
        'accounts.read', 'accounts.write',
        'academics.read', 'academics.write',
        'attendance.read', 'attendance.correct',
        'results.read', 'results.approve',
        'timetable.read', 'lessonplans.read',
        'communication.read', 'communication.write',
        # Read-only view of the money: a principal signs off on fees but does
        # not reprice the school, so `finance.read` without `finance.structure`.
        'finance.read',
        'reports.read', 'settings.read', 'ai.academic',
    ],
    'teacher': [
        'students.read', 'attendance.read', 'attendance.write',
        'results.read', 'results.write',
        'timetable.read', 'lessonplans.read', 'lessonplans.write',
        'communication.read', 'ai.teaching', 'class.read', 'class.write'
    ],
    'accountant': [
        'students.read', 'finance.read', 'finance.write', 'finance.verify',
        'finance.structure', 'finance.invoice', 'finance.payment',
        'reports.read', 'ai.finance',
    ],
    'secretary': [
        'students.read', 'students.write', 'students.register',
        'accounts.read', 'accounts.write',
        'attendance.read', 'communication.read', 'communication.write',
    ],
    'parent': ['ai.parent', 'attendance.read'],
    'student': ['ai.student', 'attendance.read'],
}


def has_permission(role, permission):
    """Single source of truth for the role→permission matrix.

    Permission classes, the `/me/` payload and the tests all read this, so the
    matrix can never drift between them.
    """
    return permission in ROLE_PERMISSIONS.get(role or '', ())


def require_permissions(*permissions):
    """Factory: DRF permission class allowing roles that hold *every* permission.

    Prefer this over `require_roles` for new endpoints: it keeps authorisation
    expressed in business terms (spec §39) rather than role names, and a
    student's own role can never accidentally satisfy a finance permission.
    """

    class _PermissionPermission(BasePermission):
        def has_permission(self, request, view):
            return bool(
                request.user
                and request.user.is_authenticated
                and all(
                    has_permission(request.user.role, permission)
                    for permission in permissions
                )
            )

        def __repr__(self):
            return f'<RequirePermissions {permissions}>'

    return _PermissionPermission


def require_roles(*roles):
    """Factory: returns a DRF permission class that allows the given roles."""

    class _RolePermission(BasePermission):
        def has_permission(self, request, view):
            return bool(
                request.user
                and request.user.is_authenticated
                and request.user.role in roles
            )

        def __repr__(self):
            return f'<RequireRole {roles}>'

    return _RolePermission


class IsSuperAdmin(BasePermission):
    """Platform manager only (no school association)."""

    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.role == 'platform_manager'
        )


class IsSchoolAdmin(BasePermission):
    """School administrator (must have a school)."""

    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.role == 'school_admin'
            and request.user.school_id is not None
        )


class HasSchool(BasePermission):
    """Any authenticated user assigned to a school."""

    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.school_id is not None
        )


class IsSchoolScoped(BasePermission):
    """Object-level check: user can only access objects belonging to their school.

    Expects the target object to have a `school` or `school_id` field.
    """

    def has_object_permission(self, request, view, obj):
        if request.user.role == 'platform_manager':
            return True
        obj_school_id = getattr(obj, 'school_id', None)
        return obj_school_id is not None and obj_school_id == request.user.school_id
