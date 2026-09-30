"""Copy the legacy school-wide fee list into the relational `FeeStructure` table.

The per-level Payment Structure editor writes `FeeStructure` rows, but every
school that configured fees before this change only has the flat JSON list on
`School.fee_structure`. Without this migration those schools would resolve no
relational fees, fall through to the JSON fallback, and carry on working - but
the moment they opened Settings > Payment Structure they would be shown empty
levels and could conclude their prices had vanished.

So each legacy row is mirrored into a SCHOOL-scope `FeeStructure` row for the
current session, preserving the original JSON untouched:

* the school-wide rows (`className: "*"`) become SCHOOL-scope rows, which is
  what the JSON already meant;
* a row naming a specific class becomes a CLASS-scope row on that `SchoolClass`,
  so the more specific fee still shadows the school default exactly as the JSON
  resolver did;
* the fee type is inferred from the label so the registration fee, tuition,
  uniform etc. are distinguishable, and anything unrecognised becomes `other`.

Idempotent: every write is `get_or_create`-shaped against the same key the
conflict constraint enforces, so re-running it changes nothing. Schools with no
configured fees are skipped entirely.

Reversible, and narrowly so: the reverse is fenced by the epoch marker *and* the
`created_by` NULL that only this migration leaves behind, so a row an admin
later edited in the editor is never removed. See `backwards()`.
"""
from decimal import Decimal, InvalidOperation

from django.db import migrations

# Labels that appear in real schools, mapped onto the FeeType vocabulary. The
# match is on a lowercased substring so "Tuition (Term 1)" still resolves.
_LABEL_TO_FEE_TYPE = (
    ('registration', 'registration'),
    ('admission', 'registration'),
    ('tuition', 'tuition'),
    ('school fees', 'tuition'),
    ('development', 'development'),
    ('ict', 'ict'),
    ('computer', 'ict'),
    ('uniform', 'uniform'),
    ('exam', 'exam'),
    ('examination', 'exam'),
    ('transport', 'transport'),
    ('meal', 'meals'),
)

# The nested `Scope` / `FeeType` choice classes are not carried onto historical
# models, so a data migration has to spell the stored values out. These match
# `FeeStructure.Scope` / `FeeStructure.FeeType` in models.py; if either
# vocabulary changes there it must change here too.
_SCOPE_SCHOOL = 'school'
_SCOPE_CLASS = 'class'


def _fee_type_for(label):
    """Best-effort fee type for a legacy label, defaulting to `other`.

    Registration is checked first because a label like "Registration and
    Tuition" should bill as a registration fee at admission.
    """
    text = (label or '').strip().lower()
    for needle, fee_type in _LABEL_TO_FEE_TYPE:
        if needle in text:
            return fee_type
    return 'other'


def forwards(apps, schema_editor):
    School = apps.get_model('schools', 'School')
    FeeStructure = apps.get_model('records', 'FeeStructure')
    SchoolClass = apps.get_model('records', 'SchoolClass')
    AcademicSession = apps.get_model('records', 'AcademicSession')

    epoch = FeeStructure._meta.get_field('effective_from').default

    for school in School.objects.all():
        items = school.fee_structure or []
        if not items:
            continue

        session = (
            AcademicSession.objects
            .filter(school=school, is_current=True, is_active=True)
            .order_by('-start_year')
            .first()
        ) or AcademicSession.objects.filter(school=school).order_by('-start_year').first()
        if session is None:
            # No session to anchor fees to. The school keeps billing from the
            # JSON, which is exactly the pre-existing behaviour.
            continue

        for item in items:
            label = str(item.get('label') or '').strip()
            if not label:
                continue
            try:
                amount = Decimal(str(item.get('amount')))
            except (TypeError, ValueError, InvalidOperation):
                continue
            if amount <= 0:
                continue

            fee_type = _fee_type_for(label)
            class_name = str(item.get('className') or '*').strip()
            school_class = None
            level = None
            scope = _SCOPE_SCHOOL
            scope_key = '*'

            if class_name and class_name != '*':
                school_class = SchoolClass.objects.filter(
                    school=school, name=class_name,
                ).first()
                if school_class is None:
                    # The JSON named a class that no longer exists. Skipping is
                    # safe: the JSON row stays where it is, and the school keeps
                    # billing from it until the level is priced in the editor.
                    continue
                scope = _SCOPE_CLASS
                scope_key = str(school_class.pk)
                level = school_class.level
            else:
                level = None

            FeeStructure.objects.get_or_create(
                school_id=school.pk,
                academic_session_id=session.pk,
                term='',
                scope=scope,
                scope_key=scope_key,
                fee_type=fee_type,
                effective_from=epoch,
                defaults={
                    'level_id': level.pk if level is not None else None,
                    'school_class_id': school_class.pk if school_class is not None else None,
                    'label': label,
                    'amount': amount,
                    'is_required': True,
                    'is_active': True,
                    'created_by': None,
                },
            )


def backwards(apps, schema_editor):
    """Remove only the rows this migration wrote.

    `created_by IS NULL` alone would be too broad - a row imported by an admin
    script carries the same shape - so the delete is additionally fenced by the
    epoch marker, which only this migration stamps, and by the whole-session
    `term`. A row an admin has since saved through the editor carries their user
    id, so it survives.

    No live invoice is affected: invoices carry a frozen snapshot of the fee
    lines, not a reference to the row that produced them.
    """
    FeeStructure = apps.get_model('records', 'FeeStructure')
    epoch = FeeStructure._meta.get_field('effective_from').default
    FeeStructure.objects.filter(
        created_by__isnull=True,
        effective_from=epoch,
        term='',
    ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('records', '0005_remove_invoice_unique_invoice_per_student_session_term_and_more'),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
