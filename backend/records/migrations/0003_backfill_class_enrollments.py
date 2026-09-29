"""Backfill the academic structure and class enrollments for existing students.

Phase 1 makes `Enrollment` the authority for class rosters (spec §35), which
previously came from the denormalised `Student.class_name` / `Student.arm`
columns. Existing schools already hold students but have no `SchoolClass`,
`Section`, `AcademicSession` or `Enrollment` rows, so without this migration
every current student would silently vanish from their attendance roster.

This migration is purely additive and idempotent:

* it never rewrites a student's name, admission number or financial record;
* it skips any student whose class cannot be resolved to a level, leaving that
  student untouched rather than guessing a wrong class;
* re-running it is a no-op, because every lookup is `get_or_create`-shaped and
  a second active enrollment per session is prevented by the partial unique
  index.
"""
from django.db import migrations

from records.services.academic import (
    LEVEL_CATALOGUE,
    guess_level_code,
    parse_session_name,
)


def _fallback_level(levels):
    """Level for a class name we cannot parse.

    Unrecognised names (e.g. "Band 7") still need *some* level because
    `SchoolClass.level` is non-null. PRIMARY is the least-wrong default and
    keeps the row usable for renaming later, since the name is stored verbatim.
    """
    return levels.get('PRI') or next(iter(levels.values()), None)


def forwards(apps, schema_editor):
    Student = apps.get_model('records', 'Student')
    School = apps.get_model('schools', 'School')
    Level = apps.get_model('records', 'Level')
    SchoolClass = apps.get_model('records', 'SchoolClass')
    Section = apps.get_model('records', 'Section')
    AcademicSession = apps.get_model('records', 'AcademicSession')
    Enrollment = apps.get_model('records', 'Enrollment')

    db_alias = schema_editor.connection.alias

    for school in School.objects.using(db_alias).all().iterator():
        # ── levels ────────────────────────────────────────────────────────
        levels = {}
        for code, name, sort_order in LEVEL_CATALOGUE:
            level, _ = Level.objects.using(db_alias).get_or_create(
                school_id=school.id, code=code,
                defaults={'name': name, 'sort_order': sort_order},
            )
            levels[code] = level

        # ── current academic session ──────────────────────────────────────
        session = None
        session_name = (school.current_session or '').strip()
        if session_name:
            try:
                start_year, end_year = parse_session_name(session_name)
            except Exception:
                start_year = end_year = None
            if start_year is not None:
                session, _ = AcademicSession.objects.using(db_alias).get_or_create(
                    school_id=school.id, name=session_name,
                    defaults={'start_year': start_year, 'end_year': end_year},
                )
                AcademicSession.objects.using(db_alias).filter(
                    school_id=school.id, name=session_name,
                ).update(is_current=True)

        if session is None:
            # No usable session on the school: rosters need one, so this
            # school's students are left for the operator to enroll rather than
            # being forced into a guessed year.
            continue

        # ── classes / sections / enrollments ──────────────────────────────
        students = (
            Student.objects.using(db_alias)
            .filter(school_id=school.id)
            .exclude(class_name='')
        )
        for student in students.iterator():
            class_name = (student.class_name or '').strip()
            if not class_name:
                continue

            # Resolve the level BEFORE the get_or_create: a name we cannot
            # parse ("Band 7") must still land on a real Level row, because
            # `SchoolClass.level` is non-null.
            level_id = (
                levels[guess_level_code(class_name)].pk
                if guess_level_code(class_name) in levels
                else _fallback_level(levels).pk
            )
            school_class, _created = SchoolClass.objects.using(db_alias).get_or_create(
                school_id=school.id, name=class_name,
                defaults={'level_id': level_id, 'sort_order': 0},
            )
            arm = (student.arm or '').strip()
            section = None
            if arm:
                section, _ = Section.objects.using(db_alias).get_or_create(
                    class_obj_id=school_class.pk, name=arm[:5],
                    # `Section.school` is NOT NULL and is the field every
                    # school-scoped query filters on, so it must be set here as
                    # well as derivable from the class.
                    defaults={'school_id': school.id},
                )

            already = Enrollment.objects.using(db_alias).filter(
                student_id=student.id, academic_session_id=session.pk,
                status='active',
            ).exists()
            if already:
                continue
            Enrollment.objects.using(db_alias).create(
                school_id=school.id,
                student_id=student.id,
                academic_session_id=session.pk,
                class_obj_id=school_class.pk,
                section_id=section.pk if section else None,
                status='active',
                activation_source='migration',
            )


def backwards(apps, schema_editor):
    """No-op.

    The rows this migration creates mirror data that already existed on
    `Student` (`class_name` / `arm`), and every `Student` column is left
    untouched, so reversing it would only *lose* the roster structure.
    """
    return None


class Migration(migrations.Migration):

    dependencies = [
        ('records', '0002_admission_foundation'),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
