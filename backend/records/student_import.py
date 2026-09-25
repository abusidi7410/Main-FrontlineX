from __future__ import annotations

import codecs
import csv
import io
import re
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from django.conf import settings
from django.db.models import Q
from django.utils.dateparse import parse_date

from schools.models import SchoolSubscription

from .models import Student


REQUIRED_COLUMNS = (
    'first_name',
    'last_name',
    'admission_number',
    'class',
    'guardian_phone',
)
OPTIONAL_COLUMNS = (
    'gender',
    'date_of_birth',
    'arm',
    'guardian_name',
)
HEADER_ALIASES = {'class_name': 'class'}
DEFAULT_MAX_FILE_SIZE = 5 * 1024 * 1024
DEFAULT_MAX_ROWS = 10000
DEFAULT_CAPACITY = 100
ADMISSION_NUMBER_PATTERN = re.compile(r'^[A-Za-z0-9/_-]+$')
SPACE_PATTERN = re.compile(r'\s+')
HEADER_SPACE_PATTERN = re.compile(r'\s+')


class StudentImportError(ValueError):
    pass


@dataclass
class ImportRow:
    row_number: int
    first_name: str
    last_name: str
    admission_number: str
    class_name: str
    guardian_phone: str
    gender: str
    date_of_birth: date | None
    arm: str
    guardian_name: str
    issues: list[str] = field(default_factory=list)
    missing_field_count: int = 0
    admission_number_usable: bool = True


@dataclass
class ParsedImport:
    file_name: str
    rows: list[ImportRow]


@dataclass
class ImportAnalysis:
    file_name: str
    rows: list[ImportRow]
    duplicate_count: int
    missing_field_count: int
    capacity: dict[str, int | bool]

    @property
    def total(self) -> int:
        return len(self.rows)

    @property
    def valid_rows(self) -> list[ImportRow]:
        return [row for row in self.rows if not row.issues]

    @property
    def valid(self) -> int:
        return len(self.valid_rows)

    @property
    def rejected(self) -> int:
        return self.total - self.valid

    @property
    def invalid(self) -> int:
        return max(self.rejected - self.duplicate_count, 0)

    def as_dict(self) -> dict[str, Any]:
        return {
            'fileName': self.file_name,
            'total': self.total,
            'valid': self.valid,
            'duplicates': self.duplicate_count,
            'missingFields': self.missing_field_count,
            'rows': [_public_row(row) for row in self.rows],
            'capacity': self.capacity,
        }


def _max_file_size() -> int:
    return int(getattr(settings, 'STUDENT_IMPORT_MAX_FILE_SIZE', DEFAULT_MAX_FILE_SIZE))


def _max_rows() -> int:
    return max(int(getattr(settings, 'STUDENT_IMPORT_MAX_ROWS', DEFAULT_MAX_ROWS)), 1)


def _clean(value: str | None) -> str:
    return (value or '').strip()


def _has_control_characters(value: str) -> bool:
    return any(ord(character) < 32 for character in value)


def _normalise_header(value: str) -> str:
    value = value.lstrip('\ufeff').strip().lower()
    return HEADER_SPACE_PATTERN.sub('_', value)


def _normalise_admission_number(value: str) -> str:
    return SPACE_PATTERN.sub('', value.strip())


def _admission_key(value: str) -> str:
    return _normalise_admission_number(value).casefold()


def _file_name(uploaded_file: Any) -> str:
    name = str(getattr(uploaded_file, 'name', '') or '').strip()
    return name.replace('\\', '/').rsplit('/', 1)[-1]


def _file_size(uploaded_file: Any) -> int | None:
    size = getattr(uploaded_file, 'size', None)
    if size is not None:
        return int(size)
    try:
        position = uploaded_file.tell()
        uploaded_file.seek(0, io.SEEK_END)
        size = uploaded_file.tell()
        uploaded_file.seek(position)
        return int(size)
    except (AttributeError, OSError, ValueError):
        return None


def _validate_upload(uploaded_file: Any) -> str:
    if uploaded_file is None:
        raise StudentImportError('Upload a CSV file.')

    file_name = _file_name(uploaded_file)
    if not file_name:
        raise StudentImportError('The uploaded file must have a name.')
    if not file_name.lower().endswith('.csv'):
        raise StudentImportError('Only CSV files are supported.')

    size = _file_size(uploaded_file)
    if size is not None and size > _max_file_size():
        raise StudentImportError(
            f'The CSV file must be smaller than {_max_file_size() // (1024 * 1024)} MB.',
        )

    content_type = str(getattr(uploaded_file, 'content_type', '') or '').lower()
    allowed_content_types = {
        '',
        'application/csv',
        'application/octet-stream',
        'application/vnd.ms-excel',
        'text/csv',
        'text/plain',
    }
    if content_type not in allowed_content_types:
        raise StudentImportError('The uploaded file must be a CSV file.')

    try:
        uploaded_file.seek(0)
        prefix = uploaded_file.read(4)
        uploaded_file.seek(0)
    except (AttributeError, OSError, ValueError) as exc:
        raise StudentImportError('The uploaded CSV could not be read.') from exc

    if prefix.startswith((codecs.BOM_UTF16_LE, codecs.BOM_UTF16_BE)):
        return 'utf-16'
    if prefix.startswith(codecs.BOM_UTF8):
        return 'utf-8-sig'
    return 'utf-8'


def _is_blank_row(cells: list[str]) -> bool:
    return not cells or all(not _clean(cell) for cell in cells)


def _value_for(cells: list[str], indexes: dict[str, int], name: str) -> str:
    index = indexes.get(name)
    if index is None or index >= len(cells):
        return ''
    return _clean(cells[index])


def _add_field_constraints(row: ImportRow) -> None:
    fields = (
        ('first name', row.first_name, 150),
        ('last name', row.last_name, 150),
        ('class', row.class_name, 50),
        ('guardian phone', row.guardian_phone, 20),
        ('arm', row.arm, 5),
        ('guardian name', row.guardian_name, 200),
    )
    for label, value, maximum in fields:
        if len(value) > maximum:
            row.issues.append(f'{label.capitalize()} exceeds {maximum} characters')
        if _has_control_characters(value):
            row.issues.append(f'{label.capitalize()} contains an invalid character')

    if row.admission_number_usable and not ADMISSION_NUMBER_PATTERN.fullmatch(row.admission_number):
        row.issues.append('Admission number contains invalid characters')
        row.admission_number_usable = False


def _build_row(cells: list[str], row_number: int, indexes: dict[str, int], column_count: int) -> ImportRow:
    raw_admission_number = _value_for(cells, indexes, 'admission_number')
    admission_number = _normalise_admission_number(raw_admission_number)
    row = ImportRow(
        row_number=row_number,
        first_name=_value_for(cells, indexes, 'first_name'),
        last_name=_value_for(cells, indexes, 'last_name'),
        admission_number=admission_number,
        class_name=_value_for(cells, indexes, 'class'),
        guardian_phone=_value_for(cells, indexes, 'guardian_phone'),
        gender=_value_for(cells, indexes, 'gender').lower() or Student.Gender.MALE,
        date_of_birth=None,
        arm=_value_for(cells, indexes, 'arm'),
        guardian_name=_value_for(cells, indexes, 'guardian_name'),
    )

    if len(cells) != column_count:
        row.issues.append(
            f'Row has {len(cells)} columns; expected {column_count}',
        )

    required_values = (
        ('first name', row.first_name),
        ('last name', row.last_name),
        ('admission number', row.admission_number),
        ('class', row.class_name),
    )
    for label, value in required_values:
        if not value:
            row.issues.append(f'Missing {label}')
            row.missing_field_count += 1

    if not admission_number:
        row.admission_number_usable = False
    elif len(admission_number) > 30:
        row.issues.append('Admission number exceeds 30 characters')
        row.admission_number_usable = False

    if row.gender not in Student.Gender.values:
        row.issues.append('Gender must be male or female')
        row.gender = Student.Gender.MALE

    raw_date_of_birth = _value_for(cells, indexes, 'date_of_birth')
    if raw_date_of_birth:
        try:
            row.date_of_birth = parse_date(raw_date_of_birth)
        except ValueError:
            row.date_of_birth = None
        if row.date_of_birth is None:
            row.issues.append('Date of birth must be a valid date')

    _add_field_constraints(row)
    return row


def _read_rows(uploaded_file: Any, encoding: str) -> tuple[str, list[ImportRow]]:
    try:
        with io.TextIOWrapper(
            uploaded_file,
            encoding=encoding,
            errors='strict',
            newline='',
        ) as text_file:
            reader = csv.reader(text_file, strict=True)
            header_cells = None
            for cells in reader:
                if not _is_blank_row(cells):
                    header_cells = cells
                    break
            if header_cells is None:
                raise StudentImportError('The CSV file is empty.')

            raw_headers = [_normalise_header(cell) for cell in header_cells]
            if any(not header for header in raw_headers):
                raise StudentImportError('Every CSV column must have a name.')
            headers = [HEADER_ALIASES.get(header, header) for header in raw_headers]
            if len(set(headers)) != len(headers):
                raise StudentImportError('CSV column names must be unique.')
            known_columns = set(REQUIRED_COLUMNS) | set(OPTIONAL_COLUMNS) | set(HEADER_ALIASES)
            unknown_columns = [header for header in headers if header not in known_columns]
            if unknown_columns:
                raise StudentImportError(
                    'Unsupported CSV columns: ' + ', '.join(unknown_columns) + '.',
                )
            missing_columns = [column for column in REQUIRED_COLUMNS if column not in headers]
            if missing_columns:
                raise StudentImportError(
                    'Missing required columns: ' + ', '.join(missing_columns) + '.',
                )
            indexes = {header: index for index, header in enumerate(headers)}
            rows = []
            for cells in reader:
                if _is_blank_row(cells):
                    continue
                if len(rows) >= _max_rows():
                    raise StudentImportError(
                        f'The CSV file cannot contain more than {_max_rows()} student rows.',
                    )
                rows.append(_build_row(cells, reader.line_num, indexes, len(headers)))

            if not rows:
                raise StudentImportError('The CSV file does not contain any student rows.')
            return _file_name(uploaded_file), rows
    except StudentImportError:
        raise
    except (UnicodeDecodeError, csv.Error, OSError, ValueError) as exc:
        raise StudentImportError('The uploaded file is not valid UTF-8 CSV.') from exc


def parse_import_file(uploaded_file: Any) -> ParsedImport:
    encoding = _validate_upload(uploaded_file)
    file_name, rows = _read_rows(uploaded_file, encoding)
    return ParsedImport(file_name=file_name, rows=rows)


def _chunks(values: list[str], size: int = 250) -> list[list[str]]:
    return [values[index:index + size] for index in range(0, len(values), size)]


def _existing_admission_keys(
    school_id: int,
    admission_numbers: list[str],
    lock_existing: bool = False,
) -> set[str]:
    candidate_keys = {
        _admission_key(number) for number in admission_numbers if number
    }
    keys = set()
    unique_numbers = sorted({number for number in admission_numbers if number})
    queryset = Student.objects.filter(school_id=school_id)
    if lock_existing:
        queryset = queryset.select_for_update()
    for chunk in _chunks(unique_numbers):
        condition = Q()
        for number in chunk:
            condition |= Q(admission_number__iexact=number)
        if not condition:
            continue
        for stored_number in queryset.filter(condition).values_list('admission_number', flat=True):
            keys.add(_admission_key(stored_number))

    unresolved = candidate_keys - keys
    if unresolved:
        fallback_rows = Student.objects.filter(school_id=school_id).values_list(
            'id', 'admission_number',
        )
        matching_ids = [
            student_id
            for student_id, stored_number in fallback_rows
            if _admission_key(stored_number) in unresolved
        ]
        if matching_ids:
            if lock_existing:
                matching_numbers = Student.objects.select_for_update().filter(
                    id__in=matching_ids,
                ).values_list('admission_number', flat=True)
            else:
                matching_numbers = Student.objects.filter(
                    id__in=matching_ids,
                ).values_list('admission_number', flat=True)
            keys.update(_admission_key(number) for number in matching_numbers)
    return keys


def _capacity(school_id: int, valid_count: int) -> dict[str, int | bool]:
    active_students = Student.objects.filter(
        school_id=school_id,
        status=Student.Status.ACTIVE,
    ).count()
    subscription = (
        SchoolSubscription.objects
        .filter(school_id=school_id, status__in=[SchoolSubscription.Status.ACTIVE, SchoolSubscription.Status.PENDING])
        .select_related('plan')
        .first()
    )
    allowed = subscription.plan.max_students if subscription and subscription.plan else DEFAULT_CAPACITY
    after_import = active_students + valid_count
    return {
        'activeStudents': active_students,
        'allowed': allowed,
        'afterImport': after_import,
        'exceeds': after_import > allowed,
    }


def analyse_import(
    parsed: ParsedImport,
    school_id: int,
    lock_existing: bool = False,
) -> ImportAnalysis:
    admission_numbers = [
        row.admission_number for row in parsed.rows if row.admission_number_usable
    ]
    seen = _existing_admission_keys(school_id, admission_numbers, lock_existing=lock_existing)
    duplicate_count = 0
    for row in parsed.rows:
        if not row.admission_number_usable:
            continue
        key = _admission_key(row.admission_number)
        if key in seen:
            row.issues.append('Duplicate admission number')
            duplicate_count += 1
        else:
            seen.add(key)
    valid_count = sum(1 for row in parsed.rows if not row.issues)
    missing_field_count = sum(row.missing_field_count for row in parsed.rows)
    return ImportAnalysis(
        file_name=parsed.file_name,
        rows=parsed.rows,
        duplicate_count=duplicate_count,
        missing_field_count=missing_field_count,
        capacity=_capacity(school_id, valid_count),
    )


def _public_row(row: ImportRow) -> dict[str, Any]:
    return {
        'rowNumber': row.row_number,
        'firstName': row.first_name,
        'lastName': row.last_name,
        'admissionNumber': row.admission_number,
        'className': row.class_name,
        'guardianPhone': row.guardian_phone,
        'gender': row.gender,
        'dateOfBirth': row.date_of_birth.isoformat() if row.date_of_birth else None,
        'arm': row.arm,
        'guardianName': row.guardian_name,
        'issues': list(row.issues),
    }
