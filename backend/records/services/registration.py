"""New-student registration (spec §19, §46).

One call produces the whole opening state, atomically::

    Student (with generated admission number)
      + Registration PENDING
      + Enrollment NOT_ENROLLED (no row yet)
      + Invoice with its immutable line-item snapshot

The student is deliberately *not* in any class roster at this point: a
registration that has not been approved (or fully paid) has no active
enrollment, and no active enrollment means no roster visibility (spec §19, §35).
"""
from __future__ import annotations

import datetime
from decimal import Decimal

from django.db import transaction
from rest_framework.exceptions import ValidationError

from . import admission, billing
from ..models import Invoice, Registration, Student
from .academic import ensure_class, ensure_section, ensure_session

INVOICE_DUE_DAYS = 30


def _gender(value: str) -> str:
    normalised = (value or '').strip().lower()
    if normalised not in Student.Gender.values:
        raise ValidationError({'gender': 'Gender must be male or female.'})
    return normalised


def _parse_date(value, field: str):
    if not value:
        return None
    if isinstance(value, datetime.date):
        return value
    try:
        return datetime.date.fromisoformat(str(value)[:10])
    except ValueError as exc:
        raise ValidationError({field: f'{field} must be a valid date (YYYY-MM-DD).'}) from exc


def register_student(
    *,
    school,
    first_name: str,
    last_name: str,
    gender: str,
    class_name: str,
    academic_session: str = '',
    section_name: str = '',
    middle_name: str = '',
    date_of_birth=None,
    guardian_name: str = '',
    guardian_phone: str = '',
    address: str = '',
    email: str = '',
    admission_number: str = '',
    admission_year: int | None = None,
    created_by=None,
) -> dict:
    """Register a new student and issue their admission number + invoice.

    `admission_number` may be supplied by the school (a school that already
    runs its own numbering); when blank the backend generates
    ``CODE/LEVEL/YEAR/SERIAL``. Either way the value is written once and never
    recomputed (spec §20, §29).
    """
    first_name = (first_name or '').strip()
    last_name = (last_name or '').strip()
    if not first_name:
        raise ValidationError({'firstName': 'First name is required.'})
    if not last_name:
        raise ValidationError({'lastName': 'Surname is required.'})

    # Resolve (or create) the academic structure *before* opening the
    # transaction: it may create rows, and no external call happens here, but
    # keeping it outside keeps the admission transaction as short as possible.
    session = ensure_session(school, academic_session or None)
    school_class = ensure_class(school, class_name)
    section = ensure_section(school, school_class, section_name)

    # Admission year: the registration session's start year for new students
    # (§22). An explicitly supplied year is honoured so a school admitting a
    # backlog keeps the identifiers it already used.
    year = admission_year or session.start_year

    with transaction.atomic():
        if admission_number:
            admission_number = admission_number.strip()
            if school.students.filter(admission_number=admission_number).exists():
                raise ValidationError({
                    'admissionNumber': 'That admission number is already in use.',
                })
            source = Student.AdmissionNumberSource.SCHOOL_ASSIGNED
        else:
            admission_number = admission.generate_admission_number(
                school, school_class.level, year,
            )
            source = Student.AdmissionNumberSource.SYSTEM_GENERATED

        student = Student.objects.create(
            school=school,
            admission_number=admission_number,
            admission_number_source=source,
            admission_year=year,
            admission_date=datetime.date.today(),
            first_name=first_name,
            middle_name=(middle_name or '').strip(),
            last_name=last_name,
            gender=_gender(gender),
            date_of_birth=_parse_date(date_of_birth, 'dateOfBirth'),
            # Denormalised mirrors of the *intended* class. The student is not
            # enrolled; rosters read Enrollment, never this column.
            class_name=school_class.name,
            arm=section.name if section else '',
            guardian_name=(guardian_name or '').strip(),
            guardian_phone=(guardian_phone or '').strip(),
            address=(address or '').strip(),
            email=(email or '').strip(),
            status=Student.Status.ACTIVE,
        )

        invoice = billing.create_invoice_for_student(
            school=school,
            student=student,
            session=session,
            school_class=school_class,
            term='',
            source=Invoice.Source.ADMISSION,
            due_date=billing.default_due_date(session, days=INVOICE_DUE_DAYS),
        )

        registration = Registration.objects.create(
            school=school,
            student=student,
            academic_session=session,
            intended_class=school_class,
            intended_section=section,
            invoice=invoice,
            status=Registration.Status.PENDING,
            created_by=created_by if getattr(created_by, 'school_id', None) else None,
        )

        ensure_parent_account(
            school=school,
            student=student,
            guardian_name=guardian_name,
            guardian_phone=student.guardian_phone,
        )

    return {
        'student': student,
        'registration': registration,
        'invoice': invoice,
        'session': session,
        'class': school_class,
        'section': section,
    }


def ensure_parent_account(*, school, student, guardian_name: str = '', guardian_phone: str = ''):
    """Provision (or reuse) the parent login account for a student.

    One parent account serves many children: the first student recorded with a
    guardian phone creates the account, and every later student carrying that
    same phone is linked to *that* account rather than a second one being
    created. The parent signs in with the phone number and the default password
    from `accounts.utils`, which forces a password change on first login.

    The phone is the source of truth for the link, so a parent whose number is
    changed on the student record is unlinked - the account stays, it simply
    stops seeing a child the school has moved to another guardian.

    Deliberately tolerant, because this runs on every student
    create/update/import and must never be the reason a student is lost:
    `User.phone` is unique platform-wide, so a number already owned by some
    other account (a staff login, a parent of another school) cannot be taken
    over. Nothing is provisioned in that case and no error is raised.
    """
    from accounts.models import User
    from accounts.utils import DEFAULT_TEMPORARY_PASSWORD
    from accounts.validators import normalize_phone

    phone = normalize_phone((guardian_phone or '').strip())
    if not phone:
        return None

    parent = User.objects.filter(
        school=school, role=User.Role.PARENT, phone=phone,
    ).first()

    # Only a parent login of *this* school may hold the link: `linked_students`
    # is the boundary the parent portal authorises against, so a cross-school
    # account must never acquire it.
    for stale in User.objects.filter(
        school=school, role=User.Role.PARENT, linked_students=student,
    ).exclude(phone=phone):
        stale.linked_students.remove(student)

    if parent is not None:
        parent.linked_students.add(student)
        return parent

    if User.objects.filter(phone=phone).exists():
        return None

    parts = (guardian_name or '').strip().split(None, 1)
    first = parts[0] if parts else 'Parent'
    last = parts[1] if len(parts) > 1 else ''
    parent = User.objects.create_user(
        email=None,
        password=DEFAULT_TEMPORARY_PASSWORD,
        first_name=first,
        last_name=last,
        role=User.Role.PARENT,
        school=school,
        phone=phone,
        is_active=True,
        must_change_password=True,
    )
    parent.linked_students.add(student)
    return parent


def registration_state(registration: Registration) -> dict:
    """The three independent states the UI must show separately (spec §79)."""
    invoice: Invoice | None = registration.invoice
    from .services.enrollment import get_active_enrollment

    enrollment = get_active_enrollment(registration.student, registration.academic_session)
    return {
        'registration': registration.status,
        'invoice': invoice.status if invoice is not None else None,
        'enrollment': enrollment.status if enrollment is not None else 'not_enrolled',
        'invoiceTotal': invoice.total if invoice is not None else Decimal('0'),
        'verifiedPaid': invoice.verified_paid if invoice is not None else Decimal('0'),
        'outstanding': invoice.outstanding if invoice is not None else Decimal('0'),
    }
