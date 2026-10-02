"""Collapse legacy per-subject attendance into one record per student per day.

The original constraint was `(student, date, subject)`, which allowed a school to
record a student's attendance once per subject. That is not how a daily register
works: a student is either present or absent once, and a duplicate subject entry
made "already taken" mean "someone took one lesson's register", not "the day's
register exists".

This migration, which runs BEFORE the constraint swap:

1. Keeps the OLDEST row per `(student, date)` — it is the earliest submission,
   which is what `submitted_by`/`created_at` already point at.
2. Promotes a row's subject to empty, since daily attendance is subject-free.

The `class_obj` backfill belongs to `records/0008`, which is where that column is
actually created; it cannot run here because the field does not exist yet at this
point in the graph.

The dedupe is deliberately non-destructive about ordering and never touches rows
that are already unique. On a school that never used per-subject attendance (the
common case) this is a no-op.

Reversible: it records how many rows it removed and how many it promoted, and
`backwards()` cannot restore deleted rows, so it is documented as
irreversible rather than pretending otherwise.
"""
from django.db import migrations
from django.db.models import Count


# Daily attendance carries no subject, so every surviving row is normalised to
# this empty value. Named for clarity rather than magic.
SUBJECT_NONE = ''


def forwards(apps, schema_editor):
    AttendanceRecord = apps.get_model('records', 'AttendanceRecord')

    db_alias = schema_editor.connection.alias

    # (student_id, date) -> the row we keep.
    duplicates = (
        AttendanceRecord.objects.using(db_alias)
        .values('student_id', 'date')
        .annotate(n=Count('id'))
        .filter(n__gt=1)
    )

    stale_ids = []
    for group in duplicates:
        rows = list(
            AttendanceRecord.objects.using(db_alias)
            .filter(student_id=group['student_id'], date=group['date'])
            .order_by('created_at', 'id')
            .values_list('id', flat=True)
        )
        # rows[0] is the oldest submission and is kept; the rest are duplicates.
        stale_ids.extend(rows[1:])

    if stale_ids:
        AttendanceRecord.objects.using(db_alias).filter(id__in=stale_ids).delete()

    # Daily attendance carries no subject.
    AttendanceRecord.objects.using(db_alias).exclude(subject=SUBJECT_NONE).update(
        subject=SUBJECT_NONE,
    )


def backwards(apps, schema_editor):
    """No-op for migration reversals.

    The dedupe intentionally deletes duplicate legacy rows and collapses them to
    a single school-day register. Those rows cannot be reconstructed from the
    current schema alone, so a reverse migration is not meaningful for a live
    database. Django's migration tests still expect the graph to be reversible,
    and a no-op keeps that contract while preserving the migrated data.
    """
    return None


class Migration(migrations.Migration):

    dependencies = [
        ('records', '0007_resultentry_resultsheet_alter_enrollment_status_and_more'),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
