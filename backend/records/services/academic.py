"""School academic structure: levels, classes, sections, sessions, school code.

The admission-number level segment (NUR/PRI/JSS/SSS) comes from the explicit
``Level`` a class belongs to — never from parsing the class name (spec §21).
This module owns creating and resolving that structure.
"""
from __future__ import annotations

import re

from django.db import transaction
from rest_framework.exceptions import ValidationError

from schools.models import School

from ..models import AcademicSession, Level, SchoolClass, Section

# Explicit level catalogue. `order` drives sort_order so rosters and fee
# overrides present levels in the order a Nigerian school would list them.
LEVEL_CATALOGUE = (
    (Level.NURSERY, 'Nursery', 10),
    (Level.PRIMARY, 'Primary', 20),
    (Level.JUNIOR_SECONDARY, 'Junior Secondary', 30),
    (Level.SENIOR_SECONDARY, 'Senior Secondary', 40),
)

# Class names the platform seeds for a new school, mapped to their level code.
# The mapping is a *seed* convenience only: once a SchoolClass row exists its
# Level FK is authoritative, so schools may rename or add classes freely.
DEFAULT_CLASSES = (
    ('Nursery 1', Level.NURSERY),
    ('Nursery 2', Level.NURSERY),
    ('Primary 1', Level.PRIMARY),
    ('Primary 2', Level.PRIMARY),
    ('Primary 3', Level.PRIMARY),
    ('Primary 4', Level.PRIMARY),
    ('Primary 5', Level.PRIMARY),
    ('Primary 6', Level.PRIMARY),
    ('JSS 1', Level.JUNIOR_SECONDARY),
    ('JSS 2', Level.JUNIOR_SECONDARY),
    ('JSS 3', Level.JUNIOR_SECONDARY),
    ('SS 1', Level.SENIOR_SECONDARY),
    ('SS 2', Level.SENIOR_SECONDARY),
    ('SS 3', Level.SENIOR_SECONDARY),
)

# Only used to map a school-supplied class name onto a level the first time a
# class is created. `SchoolClass.level` remains the source of truth afterwards.
_NAME_TO_LEVEL = (
    (re.compile(r'^(nur|nursery|kg)\b', re.I), Level.NURSERY),
    (re.compile(r'^(pri|primary|p)\b', re.I), Level.PRIMARY),
    (re.compile(r'^(jss|junior|js)\b', re.I), Level.JUNIOR_SECONDARY),
    (re.compile(r'^(sss?|senior|se)\b', re.I), Level.SENIOR_SECONDARY),
)

SESSION_PATTERN = re.compile(r'^(\d{4})\s*[/—-]\s*(\d{4})$')


def guess_level_code(name: str) -> str | None:
    """Best-effort level for a *newly configured* class name.

    This only ever feeds class creation. It is never consulted when issuing an
    admission number (spec §21) — that reads ``SchoolClass.level``.
    """
    cleaned = (name or '').strip()
    for pattern, code in _NAME_TO_LEVEL:
        if pattern.search(cleaned):
            return code
    return None


def parse_session_name(name: str) -> tuple[int, int]:
    """Turn "2026/2027" (also "2026-2027", "2026—2027") into (2026, 2027)."""
    match = SESSION_PATTERN.match((name or '').strip())
    if not match:
        raise ValidationError({'session': f'"{name}" is not a valid academic session (e.g. 2026/2027).'})
    start, end = int(match.group(1)), int(match.group(2))
    if end < start:
        raise ValidationError({'session': 'The session end year cannot be before the start year.'})
    return start, end


def get_school(code_owner: int | School) -> School:
    school = code_owner if isinstance(code_owner, School) else School.objects.get(pk=code_owner)
    return school


def ensure_levels(school: School) -> dict[str, Level]:
    """Create the four canonical levels for a school if they are missing."""
    existing = {level.code: level for level in school.levels.all()}
    missing = [
        (code, name, sort_order) for code, name, sort_order in LEVEL_CATALOGUE
        if code not in existing
    ]
    if missing:
        Level.objects.bulk_create(
            [
                Level(
                    school=school, code=code, name=name, sort_order=sort_order,
                )
                for code, name, sort_order in missing
            ],
            ignore_conflicts=True,
        )
        # Re-query rather than touching `school.levels`: that reverse manager
        # has no refresh_from_db().
        existing = {level.code: level for level in school.levels.all()}
    return existing


def ensure_school_code(school: School) -> str:
    """Return the school's stable code, deriving a suggestion when unset.

    The code is written once and then never recomputed, so renaming a school
    cannot rewrite admission numbers already issued (spec §27/§28).
    """
    if school.code:
        return school.code
    code = School.suggest_code(school.name)
    if code:
        school.code = code
        school.save(update_fields=['code'])
    return code


def ensure_class(
    school: School,
    name: str,
    level_code: str | None = None,
    level: Level | None = None,
) -> SchoolClass:
    """Fetch or create a class, resolving its level explicitly.

    `level_code` (or an explicit `level`) wins. Only when neither is given does
    the name-matching fallback run, and it still writes the result onto the
    stored class so later lookups never re-guess.
    """
    name = (name or '').strip()
    if not name:
        raise ValidationError({'className': 'Select a class.'})

    existing = school.school_classes.filter(name=name).first()
    if existing is not None:
        if level is not None and existing.level_id != level.id:
            existing.level = level
            existing.save(update_fields=['level'])
        return existing

    levels = ensure_levels(school)
    resolved = level
    # Level codes are stored uppercase (NUR/PRI/JSS/SSS); a client sending "jss"
    # meant the same level, so casing is normalised rather than rejected.
    level_code = level_code.strip().upper() if level_code else ''
    if resolved is None and level_code:
        if level_code not in levels:
            raise ValidationError({'level': f'"{level_code}" is not a supported level.'})
        resolved = levels[level_code]
    if resolved is None:
        guessed = guess_level_code(name)
        if guessed is None:
            raise ValidationError({
                'level': f'Choose a level for "{name}" (NUR, PRI, JSS or SSS).',
            })
        resolved = levels[guessed]

    return SchoolClass.objects.create(
        school=school, level=resolved, name=name,
        sort_order=resolved.sort_order,
    )


def ensure_section(school: School, class_obj: SchoolClass, name: str) -> Section | None:
    """Fetch or create a section (arm) inside a class. Blank means "no section"."""
    name = (name or '').strip()
    if not name:
        return None
    section, _ = Section.objects.get_or_create(
        school=school, class_obj=class_obj, name=name,
    )
    return section


def ensure_session(
    school: School,
    name: str | None = None,
    start_year: int | None = None,
    end_year: int | None = None,
) -> AcademicSession:
    """Fetch or create the academic session a registration/invoice anchors to.

    Prefers the school's own `current_session` so the new academic structure
    stays in step with the existing session/term model (spec §7) instead of
    introducing a second one.
    """
    name = (name or school.current_session or '').strip()
    if not name:
        raise ValidationError({
            'academicSession': 'Set the school academic session before registering students.',
        })
    if start_year is None or end_year is None:
        start_year, end_year = parse_session_name(name)

    session, _ = AcademicSession.objects.get_or_create(
        school=school,
        name=name,
        defaults={'start_year': start_year, 'end_year': end_year},
    )
    return session


def current_session(school: School) -> AcademicSession | None:
    """The session marked current, falling back to the school's own setting."""
    session = school.sessions.filter(is_current=True, is_active=True).first()
    if session is not None:
        return session
    return school.sessions.filter(name=school.current_session, is_active=True).first()


def sync_school_class_names(school: School) -> list[str]:
    """Rebuild `School.classes` from the `SchoolClass` rows.

    `School.classes` is the value every class dropdown renders, while
    `SchoolClass` is what rosters and enrollments resolve against. When the two
    drift, a dropdown offers a class the roster then 404s on. `SchoolClass` is
    authoritative: this copies its active names back onto the school so the
    dropdown can only ever offer classes that actually exist.
    """
    names = list(
        school.school_classes.filter(is_active=True)
        .order_by('sort_order', 'name')
        .values_list('name', flat=True)
    )
    if school.classes != names:
        school.classes = names
        school.save(update_fields=['classes'])
    return names


def provision_school_structure(school: School) -> dict:
    """One-time academic setup for a school: code, levels, classes, session.

    Idempotent — safe to call on every school setup screen. Runs in a single
    transaction so a school is never left half-provisioned.
    """
    with transaction.atomic():
        ensure_school_code(school)
        ensure_levels(school)
        session = ensure_session(school)
        classes = [
            ensure_class(school, name, level_code=level_code)
            for name, level_code in DEFAULT_CLASSES
        ]
        sync_school_class_names(school)
    return {
        'schoolCode': school.code,
        'session': session,
        'classes': classes,
    }
