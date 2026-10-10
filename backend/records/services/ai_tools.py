"""The AI assistant's tool layer (spec 62-68).

Design rules, in order of importance:

1. **The assistant has no data access of its own.** It never builds a queryset
   and never decides authorisation. Every answer comes from one of the read
   tools below, each of which is the *same* service the corresponding screen
   uses. There is no "AI endpoint" that can be talked into revealing something
   the user could not already see in the product.

2. **Permissions are inherited, never widened.** A tool declares the feature
   permission it needs (``finance.read``, ``results.read``, ...) plus the
   assistant permission (``ai.finance``, ...). Both must be held. A parent
   holds only ``ai.parent``, so the assistant gives them their own children and
   nothing else - and because they hold no ``finance.*`` permission, the
   assistant never quotes them a fee balance. A teacher is pinned to the classes
   on their staff record. A student's own role reaches only themselves.

3. **School isolation is structural.** A tool is only ever handed
   ``user.school``; tenant scoping lives in the queries inside the tools, not
   in prompt text a model could ignore.

4. **Writes are confirmed, not guessed.** A write returns a single-use,
   short-lived token describing exactly what will happen. Nothing changes until
   the caller echoes that token back, so a phrasing quirk cannot spend money or
   approve a registration.
"""
from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from typing import Callable

from django.db.models import Count, Q, Sum
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError

from accounts.permissions import has_permission

from . import announcements as announcement_service
from . import attendance as attendance_service
from . import billing, clearance
from . import enrollment as enrollment_service
from . import public_refs
from . import timetable as timetable_service
from ..models import (
    AttendanceRecord,
    Enrollment,
    Invoice,
    Payment,
    Registration,
    ResultEntry,
    ResultSheet,
    SchoolClass,
    StaffMember,
    Student,
)

#: Every assistant permission in the role matrix.
AI_PERMISSIONS = (
    'ai.platform', 'ai.academic', 'ai.finance', 'ai.teaching', 'ai.parent', 'ai.student',
)

SCOPE_SCHOOL = 'school'
SCOPE_OWN_CHILDREN = 'own_children'


# --- scope resolution ------------------------------------------------------

def children_of(user) -> list[Student]:
    """Students a parent account may reach, or the student's own record.

    Read from `User.linked_students` - the explicit link an administrator sets -
    and never from a name, phone number or anything a caller supplies. The
    school filter is applied even though the link is explicit, so a
    misconfigured cross-school link still cannot leak.
    """
    if user.role == 'parent':
        return list(Student.objects.filter(
            school_id=user.school_id, guardian_accounts=user,
        ))
    if user.role == 'student':
        profile = getattr(user, 'student_profile', None)
        if profile is None:
            return []
        return list(Student.objects.filter(school_id=user.school_id, pk=profile.pk))
    return []


def teacher_class_names(user) -> set[str]:
    """Class names on the teacher's staff record. Empty means "no assignment"."""
    staff = StaffMember.objects.filter(
        school_id=user.school_id, email__iexact=user.email,
        status=StaffMember.Status.ACTIVE,
    ).first()
    if staff is None or not staff.classes:
        return set()
    return set(staff.classes)


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise PermissionDenied(message)


def _parse_date(raw: str) -> date:
    try:
        return date.fromisoformat(str(raw))
    except (TypeError, ValueError):
        raise ValidationError({'date': 'Use the YYYY-MM-DD format.'})


def _current_session(user):
    from . import academic as academic_service
    return academic_service.current_session(user.school)


def _class_or_throw(user, class_name: str) -> SchoolClass:
    class_obj = SchoolClass.objects.filter(
        school_id=user.school_id, name=str(class_name), is_active=True,
    ).first()
    if class_obj is None:
        raise ValidationError({'className': 'No such class in this school.'})
    return class_obj


# --- read tools ------------------------------------------------------------
# Each takes (user, **arguments) and returns JSON-safe data.

def get_school_summary(user) -> dict:
    students = Student.objects.filter(school_id=user.school_id)
    by_status = students.values('status').annotate(total=Count('pk'))
    return {
        'school': user.school.name,
        'currentSession': user.school.current_session,
        'currentTerm': user.school.current_term,
        'studentCounts': {row['status']: row['total'] for row in by_status},
        'students': students.count(),
        'teachers': StaffMember.objects.filter(
            school_id=user.school_id, role='teacher', status=StaffMember.Status.ACTIVE,
        ).count(),
        'classes': SchoolClass.objects.filter(school_id=user.school_id, is_active=True).count(),
    }


def search_students(user, *, search: str = '', limit: int = 25) -> dict:
    queryset = Student.objects.filter(school_id=user.school_id)
    if search:
        queryset = queryset.filter(
            Q(first_name__icontains=search)
            | Q(last_name__icontains=search)
            | Q(admission_number__icontains=search)
        )
    return {
        'students': [
            {
                'id': str(student.public_id),
                'name': f'{student.last_name}, {student.first_name}',
                'admissionNumber': student.admission_number,
                'className': student.class_name,
                'status': student.status,
            }
            for student in queryset.order_by('last_name', 'first_name')[:limit]
        ],
    }


def get_student(user, *, student_id) -> dict:
    student = _student_or_throw(user, student_id)
    session = _current_session(user)
    enrollment = enrollment_service.get_active_enrollment(student, session) if session else None
    return {
        'id': str(student.public_id),
        'name': f'{student.last_name}, {student.first_name}',
        'admissionNumber': student.admission_number,
        # Enrollment is the source of truth; class_name is only a mirror.
        'className': enrollment.class_obj.name if enrollment else student.class_name,
        'status': student.status,
        'guardianName': student.guardian_name,
        'guardianPhone': student.guardian_phone,
    }


def get_student_attendance(user, *, student_id, days: int = 30) -> dict:
    student = _student_or_throw(user, student_id)
    since = _parse_date(str(_today() - timedelta(days=int(days))))
    counts = AttendanceRecord.objects.filter(
        student=student, date__gte=since,
    ).aggregate(
        present=Count('pk', filter=Q(
            status__in=[AttendanceRecord.Status.PRESENT, AttendanceRecord.Status.LATE],
        )),
        total=Count('pk'),
    )
    return {
        'student': f'{student.last_name}, {student.first_name}',
        'days': days,
        'records': counts['total'],
        'attendanceRate': (
            round(counts['present'] * 100 / counts['total'], 1) if counts['total'] else None
        ),
    }


def get_class_attendance(user, *, class_name: str, day: str) -> dict:
    class_obj = _class_or_throw(user, class_name)
    on = _parse_date(day)
    counts = AttendanceRecord.objects.filter(
        school_id=user.school_id, class_obj=class_obj, date=on,
    ).aggregate(
        present=Count('pk', filter=Q(
            status__in=[AttendanceRecord.Status.PRESENT, AttendanceRecord.Status.LATE],
        )),
        total=Count('pk'),
    )
    return {
        'className': class_obj.name,
        'date': on.isoformat(),
        'marked': counts['total'],
        'present': counts['present'],
    }


# --- daily attendance ------------------------------------------------------
# Attendance is taken once per school day for a whole class. These three tools
# answer the questions a class teacher or an administrator actually asks at the
# end of a day or the start of one.


def _daily_classes(user, class_name: str | None = None):
    """The `SchoolClass` rows this user may see attendance for.

    A teacher is narrowed to the classes they are responsible for. Without this,
    a tool whose `class_name` argument is optional (`get_absent_students`) would
    silently return school-wide data to a teacher, because `_check_scope` only
    confines a call when it can see a `class_name` or `student_id` argument.

    Reuses the REST scope helper rather than re-deriving the rule, so the
    assistant and the attendance screens cannot drift apart. That helper also
    unions the designated-class-teacher assignment with the staff record's class
    list, which matters here: a teacher promoted to class teacher has a register
    to run even if nothing was ever added to their class list.
    """
    allowed = attendance_service.teacher_visible_class_ids(
        user.school, user, _current_session(user),
    )
    classes = SchoolClass.objects.filter(school_id=user.school_id, is_active=True)
    if class_name:
        return classes.filter(name=str(class_name))
    if allowed is not None:
        classes = classes.filter(pk__in=allowed)
    return classes


def get_absent_students(user, *, day: str, class_name: str | None = None) -> dict:
    """Who was absent (or late) on a given day."""
    on = _parse_date(day)
    classes = _daily_classes(user, class_name)
    rows = AttendanceRecord.objects.filter(
        school_id=user.school_id,
        class_obj__in=classes,
        date=on,
        status__in=[AttendanceRecord.Status.ABSENT, AttendanceRecord.Status.LATE],
    ).select_related('student', 'class_obj').order_by('class_obj__name', 'student__first_name')

    absent = [
        {
            'studentId': str(record.student.public_id),
            'student': f'{record.student.last_name}, {record.student.first_name}',
            'admissionNumber': record.student.admission_number,
            'className': record.class_name,
            'status': record.status,
        }
        for record in rows
    ]
    return {
        'date': on.isoformat(),
        'className': str(class_name) if class_name else None,
        'count': len(absent),
        'absent': absent,
    }


def get_attendance_submission_status(user, *, day: str) -> dict:
    """Which classes have taken their register for a day, and which have not."""
    on = _parse_date(day)
    school = user.school
    rows = attendance_service.overview_for(school, on, class_objs=_daily_classes(user))
    not_taken = [row['className'] for row in rows if row['submitted'] == 0]
    return {
        'date': on.isoformat(),
        'isSchoolDay': attendance_service.is_school_day(school, on),
        'classes': rows,
        'submittedCount': sum(1 for row in rows if row['submitted'] > 0),
        'totalClasses': len(rows),
        'notSubmitted': not_taken,
    }


def get_chronic_absence(user, *, minimum_absences: int = 5, days: int = 30) -> dict:
    """Students absent on at least N days within the last N days."""
    since = _parse_date(str(_today() - timedelta(days=int(days))))
    floor = max(1, int(minimum_absences))
    classes = _daily_classes(user)
    rows = (
        AttendanceRecord.objects.filter(
            school_id=user.school_id,
            class_obj__in=classes,
            date__gte=since,
            status=AttendanceRecord.Status.ABSENT,
        )
        .values('student_id', 'student__public_id', 'student__first_name',
                'student__last_name', 'student__admission_number')
        .annotate(absences=Count('pk'))
        .filter(absences__gte=floor)
        .order_by('-absences')
    )
    students = [
        {
            'studentId': str(row['student__public_id']),
            'student': f'{row["student__last_name"]}, {row["student__first_name"]}',
            'admissionNumber': row['student__admission_number'],
            'absences': row['absences'],
        }
        for row in rows
    ]
    return {
        'since': since.isoformat(),
        'days': days,
        'minimumAbsences': floor,
        'count': len(students),
        'students': students,
    }


def get_student_results(user, *, student_id) -> dict:
    student = _student_or_throw(user, student_id)
    sheets = ResultSheet.objects.filter(
        school_id=user.school_id, entries__student=student,
    ).select_related('class_obj', 'academic_session').distinct()
    return {
        'student': f'{student.last_name}, {student.first_name}',
        'results': [
            {
                'sheetId': sheet.id,
                'className': sheet.class_obj.name,
                'subject': sheet.subject,
                'assessment': sheet.assessment,
                'status': sheet.status,
                # Only a published or locked sheet is a result a family can rely
                # on; anything earlier is still being entered or checked.
                'published': sheet.status in (
                    ResultSheet.Status.PUBLISHED, ResultSheet.Status.LOCKED,
                ),
            }
            for sheet in sheets
        ],
    }


def get_class_results(user, *, class_name: str) -> dict:
    class_obj = _class_or_throw(user, class_name)
    return {
        'className': class_obj.name,
        'sheets': [
            {
                'id': sheet.id,
                'subject': sheet.subject,
                'assessment': sheet.assessment,
                'status': sheet.status,
                'isLocked': sheet.is_locked,
            }
            for sheet in ResultSheet.objects.filter(
                school_id=user.school_id, class_obj=class_obj,
            ).select_related('class_obj')
        ],
    }


def get_pending_results(user, *, limit: int = 25) -> dict:
    queryset = ResultSheet.objects.filter(
        school_id=user.school_id,
        status__in=[ResultSheet.Status.SUBMITTED, ResultSheet.Status.UNDER_REVIEW],
    ).select_related('class_obj')
    return {
        'sheets': [
            {
                'id': sheet.id,
                'className': sheet.class_obj.name,
                'subject': sheet.subject,
                'assessment': sheet.assessment,
                'status': sheet.status,
            }
            for sheet in queryset[:limit]
        ],
    }


def get_fee_balance(user, *, student_id) -> dict:
    student = _student_or_throw(user, student_id)
    position = clearance.financial_clearance(student)
    return {
        'student': f'{student.last_name}, {student.first_name}',
        'outstanding': str(position['outstanding']),
        'cleared': position['cleared'],
        'requiresFullSettlement': position['requiresFullSettlement'],
    }


def get_financial_summary(user) -> dict:
    totals = Invoice.objects.filter(
        school_id=user.school_id, is_cancelled=False,
    ).aggregate(billed=Sum('total'), paid=Sum('paid'))
    billed = Decimal(totals['billed'] or 0)
    paid = Decimal(totals['paid'] or 0)
    return {
        'billed': str(billed),
        'collected': str(paid),
        'outstanding': str(billed - paid),
    }


def get_outstanding_fees(user, *, limit: int = 25) -> dict:
    invoices = Invoice.objects.filter(
        school_id=user.school_id, is_cancelled=False,
    ).exclude(status=Invoice.Status.PAID).select_related('student').order_by('due_date')
    return {
        'invoices': [
            {
                'invoiceId': invoice.id,
                'student': f'{invoice.student.last_name}, {invoice.student.first_name}',
                'total': str(invoice.total),
                'paid': str(invoice.paid),
                'outstanding': str(
                    billing.snapshot_total(invoice) - Decimal(invoice.paid)
                ),
            }
            for invoice in invoices[:limit]
        ],
    }


def get_teacher_schedule(user) -> dict:
    """The teacher's real week (spec §22).

    Resolved through the timetable module rather than the staff record's class
    list, so what the assistant says the teacher is teaching is the same thing
    the timetable screen shows them.
    """
    schedule = timetable_service.teacher_week(user)
    return {
        'teacher': schedule['teacher'],
        'assignedClasses': sorted(teacher_class_names(user)),
        'days': schedule['days'],
        'lessonCount': schedule['lessonCount'],
    }


def get_class_timetable(user, *, class_name: str) -> dict:
    class_obj = _class_or_throw(user, class_name)
    week = timetable_service.class_week(user.school_id, class_obj)
    return {
        'className': week['className'],
        # Grouped by day so the model can answer "what happens on Wednesday?"
        # without reshaping a flat list. `entries` stays as the flat view for
        # any caller that wants one lesson per row.
        'days': week['days'],
        'entries': [
            lesson
            for day in week['days']
            for lesson in day['lessons']
        ],
        'lessonCount': week['lessonCount'],
    }


def get_admission_summary(user) -> dict:
    registrations = Registration.objects.filter(school_id=user.school_id)
    return {
        'pending': registrations.filter(status=Registration.Status.PENDING).count(),
        'approved': registrations.filter(status=Registration.Status.APPROVED).count(),
        'rejected': registrations.filter(status=Registration.Status.REJECTED).count(),
    }


def get_enrollment_summary(user) -> dict:
    enrollments = Enrollment.objects.filter(school_id=user.school_id)
    return {
        'activeEnrollments': enrollments.filter(status=Enrollment.Status.ACTIVE).count(),
        'transferred': enrollments.filter(status=Enrollment.Status.TRANSFERRED).count(),
        'withdrawn': enrollments.filter(status=Enrollment.Status.WITHDRAWN).count(),
    }


def get_announcements(user, *, limit: int = 10) -> dict:
    """Recent announcements the caller is actually entitled to read.

    Goes through the same audience rules as the announcements screen, so the
    assistant cannot be used as a way around a staff-only notice: a parent
    asking the assistant for announcements gets the parents' notices and no
    others.
    """
    return {
        'announcements': [
            {
                'title': item.title,
                'body': item.body,
                'audience': announcement_service.normalise_audience(item.audience),
                'pinned': item.is_pinned,
                'publishedAt': item.created_at.isoformat(),
            }
            for item in announcement_service.visible_to(user)[:limit]
        ],
    }


def get_my_children(user) -> dict:
    """A parent's own scope: the students linked to this account."""
    return {
        'children': [
            {
                'id': str(student.public_id),
                'name': f'{student.last_name}, {student.first_name}',
                'className': student.class_name,
                'status': student.status,
            }
            for student in children_of(user)
        ],
    }


def get_my_profile(user) -> dict:
    """A student's own record. The only student the role ever reaches."""
    profile = getattr(user, 'student_profile', None)
    if profile is None or profile.school_id != user.school_id:
        raise ValidationError({
            'profile': 'This login is not linked to a student record in this school.',
        })
    session = _current_session(user)
    enrollment = enrollment_service.get_active_enrollment(profile, session) if session else None
    return {
        'id': str(profile.public_id),
        'name': f'{profile.last_name}, {profile.first_name}',
        'admissionNumber': profile.admission_number,
        # Enrollment, not the mirror column, is the class of record.
        'className': enrollment.class_obj.name if enrollment else profile.class_name,
        'status': profile.status,
    }


def _today() -> date:
    return timezone.now().date()


def _student_or_throw(user, student_id) -> Student:
    public_id = public_refs.parse_public_id(student_id)
    student = (
        Student.objects.filter(school_id=user.school_id, public_id=public_id).first()
        if public_id is not None else None
    )
    if student is None:
        raise ValidationError({'studentId': 'No such student in this school.'})
    return student


# --- the tool catalogue ----------------------------------------------------

@dataclass(frozen=True)
class Tool:
    """One assistant capability, with the permissions it inherits."""

    name: str
    call: Callable
    description: str
    #: Assistant permissions that reach this tool. A set, not a single value:
    #: a teacher's assistant permission is `ai.teaching`, but they must still be
    #: able to read results for the class they are assigned to.
    ai_permissions: tuple[str, ...]
    #: The feature permission the *screen* would require. ``None`` means the
    #: tool is self-service and is bounded by its scope instead.
    domain_permission: str | None
    scope: str
    #: Argument names the scope check needs, e.g. ``('student_id',)``.
    scope_arguments: tuple[str, ...] = ()

    def permits(self, user) -> bool:
        if not any(has_permission(user.role, p) for p in self.ai_permissions):
            return False
        if self.domain_permission and not has_permission(user.role, self.domain_permission):
            return False
        return True


READ_TOOLS: dict[str, Tool] = {
    tool.name: tool for tool in [
        Tool(
            'get_school_summary', get_school_summary,
            'Headline school numbers: students by status, teachers, classes.',
            ('ai.academic', 'ai.teaching'), 'students.read', SCOPE_SCHOOL,
        ),
        Tool(
            'search_students', search_students,
            'Find a student by name or admission number.',
            ('ai.academic', 'ai.teaching'), 'students.read', SCOPE_SCHOOL,
        ),
        Tool(
            'get_student', get_student,
            'One student record, including their real class from the enrollment.',
            ('ai.academic', 'ai.teaching'), 'students.read', SCOPE_SCHOOL, ('student_id',),
        ),
        Tool(
            'get_student_attendance', get_student_attendance,
            "A student's attendance rate over the last N days.",
            ('ai.academic', 'ai.teaching'), 'attendance.read', SCOPE_SCHOOL, ('student_id',),
        ),
        Tool(
            'get_class_attendance', get_class_attendance,
            "How many of a class were present on a given day.",
            ('ai.academic', 'ai.teaching'), 'attendance.read', SCOPE_SCHOOL, ('class_name',),
        ),
        Tool(
            'get_absent_students', get_absent_students,
            'Who was absent or late on a given day, optionally for one class.',
            ('ai.academic', 'ai.teaching'), 'attendance.read', SCOPE_SCHOOL, ('class_name',),
        ),
        Tool(
            'get_attendance_submission_status', get_attendance_submission_status,
            'Which classes have taken their register for a day, and which have not.',
            ('ai.academic', 'ai.teaching'), 'attendance.read', SCOPE_SCHOOL,
        ),
        Tool(
            'get_chronic_absence', get_chronic_absence,
            'Students absent on at least N days in the last N days.',
            ('ai.academic', 'ai.teaching'), 'attendance.read', SCOPE_SCHOOL,
        ),
        Tool(
            'get_student_results', get_student_results,
            "A student's result sheets, marking whether each is published.",
            ('ai.academic', 'ai.teaching'), 'results.read', SCOPE_SCHOOL, ('student_id',),
        ),
        Tool(
            'get_class_results', get_class_results,
            'Every result sheet for a class and its state.',
            ('ai.academic', 'ai.teaching'), 'results.read', SCOPE_SCHOOL, ('class_name',),
        ),
        Tool(
            'get_pending_results', get_pending_results,
            'Sheets waiting for review or approval.',
            ('ai.academic', 'ai.teaching'), 'results.read', SCOPE_SCHOOL,
        ),
        Tool(
            'get_fee_balance', get_fee_balance,
            "A student's outstanding balance and whether they are financially cleared.",
            ('ai.finance',), 'finance.read', SCOPE_SCHOOL, ('student_id',),
        ),
        Tool(
            'get_financial_summary', get_financial_summary,
            'Billed, collected and outstanding for the school.',
            ('ai.finance',), 'finance.read', SCOPE_SCHOOL,
        ),
        Tool(
            'get_outstanding_fees', get_outstanding_fees,
            'Invoices with money still outstanding.',
            ('ai.finance',), 'finance.read', SCOPE_SCHOOL,
        ),
        Tool(
            'get_teacher_schedule', get_teacher_schedule,
            "A teacher's full teaching week, day by day, from the school timetable.",
            ('ai.teaching',), 'timetable.read', SCOPE_SCHOOL,
        ),
        Tool(
            'get_class_timetable', get_class_timetable,
            'A class timetable: every lesson by day, period, subject, teacher and room.',
            ('ai.teaching', 'ai.academic'), 'timetable.read', SCOPE_SCHOOL, ('class_name',),
        ),
        Tool(
            'get_admission_summary', get_admission_summary,
            'Registration queue counts.',
            ('ai.academic',), 'students.register', SCOPE_SCHOOL,
        ),
        Tool(
            'get_enrollment_summary', get_enrollment_summary,
            'Active, transferred and withdrawn enrollment counts.',
            ('ai.academic', 'ai.teaching'), 'students.read', SCOPE_SCHOOL,
        ),
        Tool(
            'get_announcements', get_announcements,
            'Recent school announcements.',
            ('ai.academic', 'ai.teaching'), 'academics.read', SCOPE_SCHOOL,
        ),
        # A parent's assistant reaches their own children and nothing else. No
        # `students.read`: that permission governs the whole roster.
        Tool(
            'get_my_children', get_my_children,
            'The children linked to your account.',
            ('ai.parent',), None, SCOPE_OWN_CHILDREN,
        ),
        Tool(
            'get_my_child_attendance', get_student_attendance,
            "Your child's attendance rate.",
            ('ai.parent',), None, SCOPE_OWN_CHILDREN, ('student_id',),
        ),
        Tool(
            'get_my_child_results', get_student_results,
            "Your child's result sheets.",
            ('ai.parent',), None, SCOPE_OWN_CHILDREN, ('student_id',),
        ),
        Tool(
            'get_my_child_profile', get_student,
            "Your child's profile and class.",
            ('ai.parent',), None, SCOPE_OWN_CHILDREN, ('student_id',),
        ),
        Tool(
            'get_my_profile', get_my_profile,
            'Your own student record and class.',
            ('ai.student',), None, SCOPE_OWN_CHILDREN,
        ),
    ]
}

#: Tools that may eventually mutate data. Each inherits the same permission the
#: real action requires, so the assistant can never exceed the user's rights.
WRITE_TOOLS: dict[str, Tool] = {
    'verify_payment': Tool(
        'verify_payment', lambda user, **kwargs: kwargs,
        'Verify a recorded payment, which may clear a student for enrolment.',
        ('ai.finance',), 'finance.verify', SCOPE_SCHOOL, ('payment_id',),
    ),
}


# --- authorisation ---------------------------------------------------------

def assistant_permissions(user) -> list[str]:
    return [p for p in AI_PERMISSIONS if has_permission(user.role, p)]


def _assert_teacher_class(user, class_name) -> None:
    """A teacher may only reach the classes on their staff record.

    An empty assignment is treated as "no assignment recorded", not as "all
    classes": a teacher with no classes configured is refused rather than
    handed the whole school.
    """
    assigned = teacher_class_names(user)
    if not assigned or str(class_name) not in assigned:
        raise PermissionDenied('You are not assigned to that class.')


def _assert_teacher_student(user, student) -> None:
    """A teacher may only reach students on one of their assigned classes."""
    session = _current_session(user)
    enrollment = enrollment_service.get_active_enrollment(student, session) if session else None
    class_name = enrollment.class_obj.name if enrollment else student.class_name
    _assert_teacher_class(user, class_name)


def _check_scope(user, tool: Tool, arguments: dict) -> None:
    """Constrain a tool call to the rows this user is allowed to see.

    Enforced from the *arguments* as well as the tool's declared scope, so a
    school-scoped tool can still be narrowed to the rows this particular user
    is allowed to see. A tool that is reachable by a teacher or a parent has to
    be filtered per call, not once at the tool level.
    """
    arguments = arguments or {}

    if tool.scope == SCOPE_OWN_CHILDREN:
        allowed = {str(student.public_id) for student in children_of(user)}
        student_id = arguments.get('student_id')
        if student_id is not None and str(student_id) not in allowed:
            raise PermissionDenied('You can only ask about your own children.')
    elif user.role in ('parent', 'student'):
        # A parent or student never gets a school-wide tool, whatever
        # permissions their role happens to hold elsewhere.
        raise PermissionDenied('You can only ask about your own children.')

    if user.role == 'teacher':
        if arguments.get('class_name') is not None:
            _assert_teacher_class(user, arguments['class_name'])
        elif arguments.get('student_id') is not None:
            _assert_teacher_student(user, _student_or_throw(user, arguments['student_id']))


def call_tool(user, name: str, arguments: dict | None = None) -> dict:
    """Authorise and run one assistant tool."""
    tool = READ_TOOLS.get(name)
    if tool is None:
        if name in WRITE_TOOLS:
            raise ValidationError({
                'tool': (
                    f'"{name}" changes data and must be confirmed. '
                    'Use the confirm action with a confirmation token.'
                ),
            })
        raise ValidationError({'tool': f'"{name}" is not an available assistant tool.'})
    if not assistant_permissions(user):
        raise PermissionDenied('Your role does not have access to the assistant.')
    if not tool.permits(user):
        raise PermissionDenied(
            f'Your role does not have access to "{name}".',
        )
    arguments = arguments or {}
    _check_scope(user, tool, arguments)
    return tool.call(user, **arguments)


def tool_catalogue(user) -> list[dict]:
    """Exactly the tools this user's role can reach.

    Derived from the same table the enforcement uses, so what the assistant
    advertises can never be wider than what it will actually run.
    """
    if not assistant_permissions(user):
        return []
    return [
        {'name': tool.name, 'description': tool.description}
        for tool in sorted(READ_TOOLS.values(), key=lambda t: t.name)
        if tool.permits(user)
    ]


# --- writes: propose, then confirm -----------------------------------------

# A confirmation is single-use and short-lived, so an approved proposal cannot
# be replayed later or reused for a different action.
TOKEN_TTL = timedelta(minutes=10)
_PENDING: dict[str, dict] = {}


def _now():
    return timezone.now()


def propose_write(user, action: str, arguments: dict | None = None) -> dict:
    """Return a confirmation token *instead of* performing the action."""
    tool = WRITE_TOOLS.get(action)
    if tool is None:
        raise ValidationError({'action': f'"{action}" is not an available assistant action.'})
    if not tool.permits(user):
        raise PermissionDenied(f'Your role cannot {action}.')
    arguments = arguments or {}
    _check_scope(user, tool, arguments)
    token = secrets.token_urlsafe(16)
    _PENDING[token] = {
        'user_id': user.id,
        'action': action,
        'arguments': arguments,
        'expires_at': _now() + TOKEN_TTL,
    }
    return {
        'confirmationRequired': True,
        'confirmationToken': token,
        'action': action,
        'description': tool.description,
        'arguments': arguments,
        'expiresAt': (_now() + TOKEN_TTL).isoformat(),
    }


def confirm_write(user, action: str, token: str) -> dict:
    """Perform a previously proposed write, if the token is still good."""
    tool = WRITE_TOOLS.get(action)
    if tool is None:
        raise ValidationError({'action': f'"{action}" is not an available assistant action.'})
    pending = _PENDING.pop(str(token), None)
    if pending is None:
        raise ValidationError({
            'confirmationToken': 'That confirmation has already been used, or never existed.',
        })
    if pending['expires_at'] < _now():
        raise ValidationError({'confirmationToken': 'That confirmation has expired.'})
    if pending['user_id'] != user.id or pending['action'] != action:
        raise PermissionDenied('That confirmation belongs to a different request.')
    if not tool.permits(user):
        raise PermissionDenied(f'Your role cannot {action}.')

    if action == 'verify_payment':
        from . import finance as finance_service
        payment = Payment.objects.filter(
            school_id=user.school_id, id=pending['arguments'].get('payment_id'),
        ).first()
        if payment is None:
            raise ValidationError({'paymentId': 'No such payment in this school.'})
        outcome = finance_service.apply_verified_payment(payment, actor=user)
        return {
            'paymentId': str(outcome['payment'].id),
            'paymentStatus': outcome['payment'].status,
            'invoiceStatus': outcome['invoice'].status,
            'autoApproved': outcome.get('autoApproved', False),
            # True when the invoice is paid but the school's clearance policy
            # wants more, so the assistant must not claim the student is clear.
            'awaitingFullSettlement': outcome.get('awaitingFullSettlement', False),
        }
    raise ValidationError({'action': f'"{action}" is not implemented.'})
