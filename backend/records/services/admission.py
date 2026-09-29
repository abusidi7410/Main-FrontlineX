"""Admission number generation (spec §20–§29).

Format: ``{SCHOOL_CODE}/{LEVEL}/{YEAR}/{SERIAL:06d}`` — e.g. ``SUA/JSS/2026/000001``.

Two hard rules shape this module:

1. **Concurrency safety.** The serial is never derived from
   ``max(admission_number) + 1``. Each ``school + level + year`` combination owns
   an ``AdmissionSequence`` row that is locked with ``select_for_update`` and
   advanced in place, so simultaneous registrations cannot mint the same number.
2. **Permanence.** An admission number is written once, on the student row, and
   is never recomputed — not on promotion, not on a school rename, not when the
   fee structure changes. Only missing numbers are ever generated (spec §29).
"""
from __future__ import annotations

from dataclasses import dataclass

from django.db import DatabaseError, transaction
from rest_framework.exceptions import ValidationError

from schools.models import School

from ..models import AdmissionSequence, Level, Student

SERIAL_WIDTH = 6
# A school code + 3-char level + 4-digit year + separators must fit the column.
ADMISSION_NUMBER_MAX_LENGTH = 30


@dataclass(frozen=True)
class Allocation:
    """A contiguous block of serials reserved for one sequence."""

    first: int
    last: int

    def __iter__(self):
        yield from range(self.first, self.last + 1)

    def __len__(self) -> int:
        return self.last - self.first + 1


class MissingSchoolCodeError(ValidationError):
    """Raised when admission numbers are requested before a code is confirmed."""

    def __init__(self):
        super().__init__(
            {'schoolCode': 'Confirm the school code before issuing admission numbers.'},
        )


def format_admission_number(code: str, level_code: str, year: int, serial: int) -> str:
    number = f'{code}/{level_code}/{year}/{serial:0{SERIAL_WIDTH}d}'
    if len(number) > ADMISSION_NUMBER_MAX_LENGTH:
        raise ValidationError({
            'admissionNumber': 'The school code is too long to build an admission number.',
        })
    return number


def resolve_school_code(school: School) -> str:
    code = (school.code or '').strip().upper()
    if not code:
        raise MissingSchoolCodeError()
    return code


def _lock_sequence(school: School, level: Level, year: int) -> AdmissionSequence:
    """Get-or-create the sequence row and hold a row lock on it.

    The lock is released at the end of the surrounding transaction. Creating
    the row races with a concurrent creator, so IntegrityError is swallowed and
    the row re-read (now lockable) instead of surfacing as a 500.
    """
    try:
        with transaction.atomic():
            sequence, _ = AdmissionSequence.objects.get_or_create(
                school=school, level=level, year=year,
                defaults={'last_serial': 0},
            )
    except DatabaseError:
        sequence = AdmissionSequence.objects.get(school=school, level=level, year=year)

    return AdmissionSequence.objects.select_for_update().get(pk=sequence.pk)


def _advance(sequence: AdmissionSequence, count: int) -> Allocation:
    first = sequence.last_serial + 1
    last = first + count - 1
    sequence.last_serial = last
    sequence.save(update_fields=['last_serial'])
    return Allocation(first=first, last=last)


def allocate_admission_numbers(
    school: School,
    level: Level,
    year: int,
    count: int = 1,
) -> list[str]:
    """Reserve `count` consecutive serials and return the formatted numbers.

    Must be called inside a transaction (a plain function call is not atomic on
    its own). For a single number use :func:`generate_admission_number`, which
    wraps this in its own transaction.
    """
    if count < 1:
        return []
    code = resolve_school_code(school)
    sequence = _lock_sequence(school, level, year)
    allocation = _advance(sequence, count)
    return [
        format_admission_number(code, level.code, year, serial) for serial in allocation
    ]


def generate_admission_number(school: School, level: Level, year: int) -> str:
    """Issue one admission number, atomically.

    `year` is the *admission* year, not the current calendar year: new students
    use their registration session's start year (spec §22).
    """
    with transaction.atomic():
        return allocate_admission_numbers(school, level, year, 1)[0]


def generate_admission_number_block(
    school: School,
    level: Level,
    year: int,
    count: int,
) -> list[str]:
    """Issue `count` numbers in one locked reservation.

    Used by the bulk-migration workflow so importing 500 students does not
    take 500 separate locks (spec §25).
    """
    with transaction.atomic():
        return allocate_admission_numbers(school, level, year, count)


def admission_number_is_taken(school: School, admission_number: str) -> bool:
    return school.students.filter(admission_number=admission_number).exists()


def mark_imported(student: Student) -> Student:
    """Record that a student's admission number came from their old school."""
    student.admission_number_source = Student.AdmissionNumberSource.IMPORTED
    return student
