"""Rebuild `School.classes` from the `SchoolClass` rows.

`SchoolClass` is what rosters, enrollments and the class-teacher assignment
resolve against. `School.classes` is only the list every class dropdown renders.
Where the two disagreed, a school with real classes showed an EMPTY dropdown, so
nobody could pick a class to take a register - while the register endpoint
correctly resolved those same classes. The dropdown was the broken half.

This rebuilds the mirror from the authoritative rows, in the same order
(`sort_order`, then name) the read path uses. It is idempotent, and it only
writes to schools whose stored list actually differs, so re-running it is a
no-op. Schools with no `SchoolClass` rows are left alone: inventing classes for
them would be fabricating data, and an administrator can add real ones through
the academics screen.

Reverse is a no-op: the previous value was the broken one, and there is nothing
sensible to reconstruct it from.
"""
from django.db import migrations


def rebuild_class_mirror(apps, schema_editor):
    School = apps.get_model('schools', 'School')
    SchoolClass = apps.get_model('records', 'SchoolClass')

    db_alias = schema_editor.connection.alias
    for school in School.objects.using(db_alias).all().iterator():
        names = list(
            SchoolClass.objects.using(db_alias)
            .filter(school_id=school.id, is_active=True)
            .order_by('sort_order', 'name')
            .values_list('name', flat=True)
        )
        if school.classes != names:
            school.classes = names
            school.save(update_fields=['classes'])


class Migration(migrations.Migration):

    dependencies = [
        ('schools', '0013_auditlog_merge_duplicate_indexes'),
        ('records', '0008_attendance_daily_register'),
    ]

    operations = [
        migrations.RunPython(rebuild_class_mirror, migrations.RunPython.noop),
    ]
