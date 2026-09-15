from rest_framework.permissions import BasePermission


# Mirrors the frontend role→permission matrix (src/permissions/index.ts).
# The API is the authority; this is used to populate AuthUser.permissions
# in serializer output.
ROLE_PERMISSIONS = {
    'platform_manager': [
        'platform.manage', 'subscription.read', 'subscription.write',
        'audit.read', 'reports.read', 'ai.platform',
        'settings.read', 'settings.write',
    ],
    'school_admin': [
        'students.read', 'students.write', 'students.import',
        'staff.read', 'staff.write',
        'academics.read', 'academics.write',
        'attendance.read', 'attendance.write',
        'results.read', 'results.write', 'results.approve', 'results.publish',
        'finance.read', 'finance.write', 'finance.verify',
        'timetable.read', 'timetable.write',
        'lessonplans.read', 'lessonplans.write',
        'communication.read', 'communication.write',
        'reports.read', 'subscription.read', 'subscription.write',
        'settings.read', 'settings.write', 'audit.read',
        'ai.academic', 'ai.finance', 'ai.teaching',
    ],
    'principal': [
        'students.read', 'students.write', 'staff.read', 'staff.write',
        'academics.read', 'academics.write',
        'attendance.read', 'results.read', 'results.approve',
        'timetable.read', 'lessonplans.read',
        'communication.read', 'communication.write',
        'reports.read', 'settings.read', 'ai.academic',
    ],
    'teacher': [
        'students.read', 'attendance.read', 'attendance.write',
        'results.read', 'results.write',
        'timetable.read', 'lessonplans.read', 'lessonplans.write',
        'communication.read', 'ai.teaching',
    ],
    'accountant': [
        'students.read', 'finance.read', 'finance.write', 'finance.verify',
        'reports.read', 'ai.finance',
    ],
    'secretary': [
        'students.read', 'students.write',
        'attendance.read', 'communication.read', 'communication.write',
    ],
    'parent': ['ai.parent'],
    'student': ['ai.student'],
}


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
