"""Admission workflow: validation, submission, review and approval.

Approval deliberately does not re-implement registration. It calls the same
`records` services the existing "Add student" screen uses, in the same order:

    Student (PENDING_PAYMENT)
      → wallet-funded access (₦/student/month)
      → registration invoice from the configured Payment Structure
      → Registration row
      → parent login
      → Enrollment (when the registration fee is already settled)

Consequently an applicant approved here is indistinguishable from a student
added by hand, and there is exactly one billing path to maintain.
"""
from __future__ import annotations

import datetime
import hashlib
import os

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from accounts.utils import DEFAULT_TEMPORARY_PASSWORD  # noqa: F401  (documented coupling)
from accounts.validators import normalize_phone
from billing import services as wallet_billing
from records.models import AcademicSession, SchoolClass, Student
from records.services import academic as academic_service
from records.services import admission as admission_service
from records.services import registration as registration_service

from . import storage
from .models import AdmissionApplication, AdmissionDocument, AdmissionSettings

#: Fields required before an application may be submitted. Keys are the API's
#: camelCase names so the form can attach each message to the right input.
SUBMIT_REQUIRED_TEXT = {
    'firstName': 'First name',
    'lastName': 'Surname',
    'guardianName': 'Parent / guardian name',
    'guardianPhone': 'Parent / guardian phone',
    'guardianAddress': 'Home address',
}
SUBMIT_REQUIRED_OBJECTS = {
    'classId': 'Class applied for',
    'academicSessionId': 'Academic session',
}

MAX_FILENAME_LENGTH = 255


def get_settings(school) -> AdmissionSettings:
    settings_obj, _ = AdmissionSettings.objects.get_or_create(school=school)
    return settings_obj


# ── Submission ──────────────────────────────────────────────────────────────

def _phone_error(value: str) -> str | None:
    normalised = normalize_phone(value)
    digits = normalised.replace('+', '')
    if not digits.isdigit() or not 10 <= len(digits) <= 15:
        return 'Enter a valid phone number.'
    return None


def validate_for_submission(application: AdmissionApplication) -> None:
    """Reject an incomplete application with per-field messages.

    Drafts are allowed to be partial, so this runs only on submit (and again on
    approval, because a school can change its settings in between).
    """
    errors: dict[str, str] = {}
    for field, label in SUBMIT_REQUIRED_TEXT.items():
        model_field = {
            'firstName': 'first_name',
            'lastName': 'last_name',
            'guardianName': 'guardian_name',
            'guardianPhone': 'guardian_phone',
            'guardianAddress': 'guardian_address',
        }[field]
        if not str(getattr(application, model_field) or '').strip():
            errors[field] = f'{label} is required.'

    if not application.gender:
        errors['gender'] = 'Select the applicant’s gender.'
    elif application.gender not in AdmissionApplication.Gender.values:
        errors['gender'] = 'Gender must be male or female.'

    if application.date_of_birth is None:
        errors['dateOfBirth'] = 'Date of birth is required.'
    elif application.date_of_birth > datetime.date.today():
        errors['dateOfBirth'] = 'Date of birth cannot be in the future.'

    if application.class_applied_id is None:
        errors['classId'] = SUBMIT_REQUIRED_OBJECTS['classId'] + ' is required.'
    elif application.class_applied.school_id != application.school_id:
        errors['classId'] = 'That class does not belong to your school.'

    if application.academic_session_id is None:
        errors['academicSessionId'] = (
            SUBMIT_REQUIRED_OBJECTS['academicSessionId'] + ' is required.'
        )
    elif application.academic_session.school_id != application.school_id:
        errors['academicSessionId'] = 'That session does not belong to your school.'

    phone_error = _phone_error(application.guardian_phone)
    if phone_error and 'guardianPhone' not in errors:
        errors['guardianPhone'] = phone_error
    if application.guardian_email and '@' not in application.guardian_email:
        errors['guardianEmail'] = 'Enter a valid email address.'

    if application.applicant_type == AdmissionApplication.ApplicantType.TRANSFER:
        settings_obj = get_settings(application.school)
        if settings_obj.require_previous_school_for_transfer:
            if not application.previous_school_name.strip():
                errors['previousSchoolName'] = (
                    'The previous school is required for a transfer applicant.'
                )
            if not application.last_class_completed.strip():
                errors['lastClassCompleted'] = (
                    'The last class completed is required for a transfer applicant.'
                )

    settings_obj = get_settings(application.school)
    if settings_obj.referee_required:
        if not application.referee_name.strip():
            errors['refereeName'] = 'Referee name is required.'
        if not application.referee_phone.strip():
            errors['refereePhone'] = 'Referee phone is required.'

    if not application.declared_by.strip():
        errors['declaredBy'] = 'Type the guardian’s name to sign the declaration.'

    if errors:
        raise ValidationError(errors)


def find_duplicate_application(application: AdmissionApplication):
    """An existing live application for the same child, if there is one.

    Name matching is case-insensitive and date of birth is exact: two siblings
    can share a surname, but not a surname + first name + date of birth.
    """
    if not (application.first_name and application.last_name and application.date_of_birth):
        return None
    return (
        AdmissionApplication.objects.filter(
            school_id=application.school_id,
            first_name__iexact=application.first_name.strip(),
            last_name__iexact=application.last_name.strip(),
            date_of_birth=application.date_of_birth,
        )
        .exclude(pk=application.pk)
        .exclude(status__in=[
            AdmissionApplication.Status.REJECTED,
            AdmissionApplication.Status.WITHDRAWN,
        ])
        .order_by('-created_at')
        .first()
    )


def find_existing_student(application: AdmissionApplication):
    if not (application.first_name and application.last_name and application.date_of_birth):
        return None
    return (
        Student.objects.filter(
            school_id=application.school_id,
            first_name__iexact=application.first_name.strip(),
            last_name__iexact=application.last_name.strip(),
            date_of_birth=application.date_of_birth,
        )
        .exclude(status__in=[
            Student.Status.WITHDRAWN,
            Student.Status.TRANSFERRED,
            Student.Status.EXPELLED,
        ])
        .first()
    )


def submit_application(application: AdmissionApplication, *, allow_duplicate: bool = False):
    if application.status != AdmissionApplication.Status.DRAFT:
        raise ValidationError({'detail': 'Only a draft application can be submitted.'})
    validate_for_submission(application)
    duplicate = find_duplicate_application(application)
    existing_student = find_existing_student(application)
    if not allow_duplicate and (duplicate is not None or existing_student is not None):
        raise ValidationError({
            'detail': (
                'A matching application or student record already exists for this '
                'child. Confirm that this is a separate application to continue.'
            ),
            'duplicateApplicationId': str(duplicate.public_id) if duplicate else '',
            'duplicateStudentId': str(existing_student.public_id) if existing_student else '',
        })
    if duplicate is not None:
        application.duplicate_of = duplicate
    application.status = AdmissionApplication.Status.SUBMITTED
    application.submitted_at = timezone.now()
    application.declared_at = application.declared_at or timezone.now()
    application.save(update_fields=[
        'status', 'submitted_at', 'declared_at', 'duplicate_of', 'last_saved_at',
    ])
    return application


def start_review(application: AdmissionApplication) -> AdmissionApplication:
    if application.status != AdmissionApplication.Status.SUBMITTED:
        raise ValidationError({'detail': 'Only a submitted application can be reviewed.'})
    application.status = AdmissionApplication.Status.UNDER_REVIEW
    application.save(update_fields=['status', 'last_saved_at'])
    return application


# ── Documents ───────────────────────────────────────────────────────────────

def missing_required_documents(application: AdmissionApplication) -> list[str]:
    settings_obj = get_settings(application.school)
    if not settings_obj.required_documents:
        return []
    verified = set(
        application.documents.filter(
            status=AdmissionDocument.Status.VERIFIED,
        ).values_list('category', flat=True)
    )
    return [
        category for category in settings_obj.required_documents
        if category in AdmissionDocument.Category.values and category not in verified
    ]


def _safe_filename(filename: str) -> str:
    name = os.path.basename((filename or '').replace('\\', '/')).strip()
    name = ''.join(ch for ch in name if ch.isprintable())
    return (name or 'document')[:MAX_FILENAME_LENGTH]


def store_document(
    *,
    application: AdmissionApplication,
    category: str,
    filename: str,
    content: bytes,
    actor=None,
) -> AdmissionDocument:
    if application.status in (
        AdmissionApplication.Status.APPROVED,
        AdmissionApplication.Status.REJECTED,
        AdmissionApplication.Status.WITHDRAWN,
    ):
        raise ValidationError({
            'detail': 'Documents cannot be added to a closed application.',
        })
    if category not in AdmissionDocument.Category.values:
        raise ValidationError({'category': 'Choose a valid document type.'})

    limit = int(getattr(settings, 'PRIVATE_DOCUMENT_MAX_BYTES', 10 * 1024 * 1024))
    if not content:
        raise ValidationError({'file': 'The uploaded file is empty.'})
    if len(content) > limit:
        raise ValidationError({
            'file': f'The file is larger than the {limit // (1024 * 1024)} MB limit.',
        })

    content_type = storage.sniff_content_type(content[:16])
    if content_type not in storage.ALLOWED_CONTENT_TYPES:
        raise ValidationError({
            'file': 'Upload a PDF, JPEG, PNG or WebP file. The file contents could not be recognised.',
        })
    extension = storage.extension_for(content_type)
    key = storage.build_key(application.school_id)

    try:
        storage.save(key, content, extension)
    except storage.DocumentStorageError as exc:
        raise ValidationError({'file': str(exc)}) from exc

    try:
        with transaction.atomic():
            document = AdmissionDocument.objects.create(
                school_id=application.school_id,
                application=application,
                category=category,
                storage_key=key,
                original_filename=_safe_filename(filename),
                content_type=content_type,
                size_bytes=len(content),
                checksum=hashlib.sha256(content).hexdigest(),
                uploaded_by=actor if getattr(actor, 'school_id', None) else None,
            )
    except Exception:
        storage.delete(key)
        raise
    return document


def review_document(document: AdmissionDocument, *, status: str, actor=None, note=''):
    if status not in (AdmissionDocument.Status.VERIFIED, AdmissionDocument.Status.REJECTED):
        raise ValidationError({'status': 'Choose verified or rejected.'})
    document.status = status
    document.reviewed_by = actor if getattr(actor, 'school_id', None) else None
    document.reviewed_at = timezone.now()
    document.review_note = (note or '').strip()[:255]
    document.save(update_fields=['status', 'reviewed_by', 'reviewed_at', 'review_note'])
    return document


def delete_document(document: AdmissionDocument) -> None:
    key = document.storage_key
    document.delete()
    storage.delete(key)


# ── Approval / rejection ────────────────────────────────────────────────────

def _resolve_class(application: AdmissionApplication, class_id) -> SchoolClass:
    if class_id in (None, ''):
        school_class = application.class_applied
    else:
        school_class = SchoolClass.objects.filter(
            pk=class_id, school_id=application.school_id,
        ).first()
        if school_class is None:
            raise ValidationError({'classId': 'Select a class that belongs to your school.'})
    if school_class is None:
        raise ValidationError({'classId': 'Choose the class the applicant is joining.'})
    return school_class


def _resolve_session(application: AdmissionApplication) -> AcademicSession:
    session = application.academic_session
    if session is None:
        session = academic_service.current_session(application.school)
    if session is None:
        raise ValidationError({
            'academicSessionId': 'Set the school academic session before admitting students.',
        })
    if session.school_id != application.school_id:
        raise ValidationError({'academicSessionId': 'That session belongs to another school.'})
    return session


def approve_application(
    application: AdmissionApplication,
    *,
    actor=None,
    class_id=None,
    admission_number: str = '',
):
    """Approve an application and create the real student record.

    Returns a dict with the application, student, invoice and access receipt so
    the API can answer with everything the reviewer needs to see.
    """
    if application.status == AdmissionApplication.Status.APPROVED:
        raise ValidationError({'detail': 'This application is already approved.'})
    if application.status not in (
        AdmissionApplication.Status.SUBMITTED,
        AdmissionApplication.Status.UNDER_REVIEW,
    ):
        raise ValidationError({'detail': 'Submit the application before approving it.'})

    validate_for_submission(application)
    missing = missing_required_documents(application)
    if missing:
        labels = dict(AdmissionDocument.Category.choices)
        raise ValidationError({
            'documents': (
                'Verify the required documents before approving: '
                + ', '.join(labels.get(item, item) for item in missing)
                + '.'
            ),
        })

    school = application.school
    school_class = _resolve_class(application, class_id)
    session = _resolve_session(application)
    year = application.admission_year or session.start_year

    # Fail before creating anything when the wallet cannot fund the activation.
    wallet_billing.require_enrollment_funding(school, what='admitting students')

    supplied = (admission_number or '').strip()
    if supplied and admission_service.admission_number_is_taken(school, supplied):
        raise ValidationError({
            'admissionNumber': 'That admission number is already in use.',
        })

    with transaction.atomic():
        locked = (
            AdmissionApplication.objects.select_for_update()
            .select_related('school', 'class_applied')
            .get(pk=application.pk)
        )
        if locked.status not in (
            AdmissionApplication.Status.SUBMITTED,
            AdmissionApplication.Status.UNDER_REVIEW,
        ):
            raise ValidationError({'detail': 'This application has already been decided.'})

        if supplied:
            number = supplied
            source = Student.AdmissionNumberSource.SCHOOL_ASSIGNED
        else:
            number = admission_service.generate_admission_number(
                school, school_class.level, year,
            )
            source = Student.AdmissionNumberSource.SYSTEM_GENERATED

        try:
            with transaction.atomic():
                student = Student.objects.create(
                    school=school,
                    admission_number=number,
                    admission_number_source=source,
                    admission_year=year,
                    admission_date=datetime.date.today(),
                    first_name=locked.first_name.strip(),
                    middle_name=locked.middle_name.strip(),
                    last_name=locked.last_name.strip(),
                    gender=locked.gender,
                    date_of_birth=locked.date_of_birth,
                    class_name=school_class.name,
                    arm='',
                    status=Student.Status.PENDING_PAYMENT,
                    guardian_name=locked.guardian_name.strip(),
                    guardian_phone=locked.guardian_phone.strip(),
                    address=(locked.guardian_address or locked.mailing_address).strip(),
                    email=locked.guardian_email.strip(),
                )
        except IntegrityError as exc:
            raise ValidationError({
                'admissionNumber': 'That admission number has just been taken. Try again.',
            }) from exc

        pricing = wallet_billing.get_pricing()
        entitlement = None
        wallet = wallet_billing.get_wallet(school)
        if pricing.enforce_student_access:
            entitlement, _ = wallet_billing.activate_student(
                school, student, actor=actor,
            )
            wallet = wallet_billing.get_wallet(school)

        invoice = registration_service.finalize_admission(
            school=school, student=student, actor=actor,
        )

        locked.status = AdmissionApplication.Status.APPROVED
        locked.student = student
        locked.admission_number = number
        locked.class_applied = school_class
        locked.academic_session = session
        locked.applied_level_code = school_class.level.code
        locked.reviewed_by = actor if getattr(actor, 'school_id', None) else None
        locked.reviewed_at = timezone.now()
        locked.save(update_fields=[
            'status', 'student', 'admission_number', 'class_applied',
            'academic_session', 'applied_level_code', 'reviewed_by',
            'reviewed_at', 'last_saved_at',
        ])
        locked.documents.update(student=student)

    return {
        'application': locked,
        'student': student,
        'invoice': invoice,
        'entitlement': entitlement,
        'wallet': wallet,
    }


def reject_application(application: AdmissionApplication, *, reason: str, actor=None):
    if application.status in (
        AdmissionApplication.Status.APPROVED,
        AdmissionApplication.Status.REJECTED,
        AdmissionApplication.Status.WITHDRAWN,
    ):
        raise ValidationError({'detail': 'This application has already been decided.'})
    reason = (reason or '').strip()
    if not reason:
        raise ValidationError({'reason': 'Give a reason for the rejection.'})
    application.status = AdmissionApplication.Status.REJECTED
    application.decision_reason = reason[:255]
    application.reviewed_by = actor if getattr(actor, 'school_id', None) else None
    application.reviewed_at = timezone.now()
    application.save(update_fields=[
        'status', 'decision_reason', 'reviewed_by', 'reviewed_at', 'last_saved_at',
    ])
    return application


def withdraw_application(application: AdmissionApplication, *, reason: str = ''):
    if application.status in (
        AdmissionApplication.Status.APPROVED,
        AdmissionApplication.Status.REJECTED,
        AdmissionApplication.Status.WITHDRAWN,
    ):
        raise ValidationError({'detail': 'This application can no longer be withdrawn.'})
    application.status = AdmissionApplication.Status.WITHDRAWN
    application.decision_reason = (reason or '').strip()[:255]
    application.save(update_fields=['status', 'decision_reason', 'last_saved_at'])
    return application
