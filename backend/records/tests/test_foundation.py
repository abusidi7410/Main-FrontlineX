"""Phase 1 foundation: school code, levels, sessions, admission numbering.

Covers spec §20–§29 (admission numbers), §21 (explicit levels), §27/§28 (school
code) and §5–§8 (payment structure resolution and invoice snapshots).
"""
from __future__ import annotations

from decimal import Decimal
from threading import Barrier, Thread

from django.db import connection, connections
from django.test import TransactionTestCase, skipUnlessDBFeature

from accounts.models import User
from records.models import (
    AdmissionSequence,
    FeeStructure,
    Level,
    Registration,
    SchoolClass,
    Student,
)
from records.services import admission, academic, billing
from schools.models import School

from .base import SchoolTestCase


class SchoolCodeTests(SchoolTestCase):
    def test_suggest_code_skips_filler_words(self):
        self.assertEqual(School.suggest_code('Success Academy'), 'SA')
        self.assertEqual(School.suggest_code('The Success Academy'), 'SA')
        self.assertEqual(School.suggest_code('Bright Hope International School'), 'BHI')

    def test_code_is_stored_and_survives_a_rename(self):
        self.school.name = 'Success Academy International School'
        self.school.save(update_fields=['name'])
        self.school.refresh_from_db()
        self.assertEqual(self.school.code, 'SUA')

    def test_ensure_school_code_derives_once_then_freezes(self):
        school = School.objects.create(
            name='Greenfield School', slug='greenfield',
            address='x', state='Kano', lga='Kano', phone='1', email='g@example.com',
        )
        self.assertEqual(academic.ensure_school_code(school), 'GS')
        school.name = 'Renamed Completely'
        school.save(update_fields=['name'])
        self.assertEqual(academic.ensure_school_code(school), 'GS')


class LevelTests(SchoolTestCase):
    def test_class_level_is_explicit_not_parsed_from_name(self):
        odd = SchoolClass.objects.create(
            school=self.school, level=self.jss_level, name='Basic 7',
        )
        self.assertEqual(odd.level.code, 'JSS')

    def test_ensure_class_uses_explicit_level_code_over_name(self):
        created = academic.ensure_class(self.school, 'Senior 1', level_code=Level.SENIOR_SECONDARY)
        self.assertEqual(created.level.code, 'SSS')
        self.assertEqual(created.name, 'Senior 1')

    def test_ensure_class_is_idempotent(self):
        first = academic.ensure_class(self.school, 'JSS 3')
        second = academic.ensure_class(self.school, 'JSS 3')
        self.assertEqual(first.pk, second.pk)

    def test_ensure_class_without_a_resolvable_level_is_rejected(self):
        from rest_framework.exceptions import ValidationError

        with self.assertRaises(ValidationError):
            academic.ensure_class(self.school, 'Band 7')


class SessionTests(SchoolTestCase):
    def test_parse_session_name(self):
        self.assertEqual(academic.parse_session_name('2026/2027'), (2026, 2027))
        self.assertEqual(academic.parse_session_name('2026-2027'), (2026, 2027))
        self.assertEqual(academic.parse_session_name(' 2026 / 2027 '), (2026, 2027))

    def test_invalid_session_name_is_rejected(self):
        from rest_framework.exceptions import ValidationError

        with self.assertRaises(ValidationError):
            academic.parse_session_name('twenty twenty six')

    def test_ensure_session_follows_the_school_setting(self):
        session = academic.ensure_session(self.school)
        self.assertEqual(session.name, '2026/2027')
        self.assertEqual(session.start_year, 2026)


class AdmissionNumberTests(SchoolTestCase):
    def test_format_is_code_level_year_six_digit_serial(self):
        self.assertEqual(
            admission.format_admission_number('SUA', 'JSS', 2026, 1),
            'SUA/JSS/2026/000001',
        )
        self.assertEqual(
            admission.format_admission_number('SUA', 'JSS', 2026, 1234567)[-6:],
            '234567',
        )

    def test_each_level_has_an_independent_sequence(self):
        first = admission.generate_admission_number(self.school, self.jss_level, 2026)
        second = admission.generate_admission_number(self.school, self.pri_level, 2026)
        third = admission.generate_admission_number(self.school, self.sss_level, 2026)
        self.assertEqual(first, 'SUA/JSS/2026/000001')
        self.assertEqual(second, 'SUA/PRI/2026/000001')
        self.assertEqual(third, 'SUA/SSS/2026/000001')

    def test_each_year_restarts_its_own_sequence(self):
        self.assertEqual(
            admission.generate_admission_number(self.school, self.jss_level, 2025),
            'SUA/JSS/2025/000001',
        )
        self.assertEqual(
            admission.generate_admission_number(self.school, self.jss_level, 2026),
            'SUA/JSS/2026/000001',
        )

    def test_serials_increment_within_a_sequence(self):
        numbers = [
            admission.generate_admission_number(self.school, self.jss_level, 2026)
            for _ in range(3)
        ]
        self.assertEqual(numbers, [
            'SUA/JSS/2026/000001', 'SUA/JSS/2026/000002', 'SUA/JSS/2026/000003',
        ])

    def test_block_allocation_returns_a_contiguous_range(self):
        numbers = admission.generate_admission_number_block(
            self.school, self.jss_level, 2024, 500,
        )
        self.assertEqual(len(numbers), 500)
        self.assertEqual(numbers[0], 'SUA/JSS/2024/000001')
        self.assertEqual(numbers[-1], 'SUA/JSS/2024/000500')
        # The next single allocation continues from the reserved block.
        self.assertEqual(
            admission.generate_admission_number(self.school, self.jss_level, 2024),
            'SUA/JSS/2024/000501',
        )

    def test_sequences_are_scoped_per_school(self):
        other_jss = SchoolClass.objects.create(
            school=self.other_school,
            level=Level.objects.create(
                school=self.other_school, code=Level.JUNIOR_SECONDARY, name='JSS',
            ),
            name='JSS 1',
        )
        self.assertEqual(
            admission.generate_admission_number(self.school, self.jss_level, 2026),
            'SUA/JSS/2026/000001',
        )
        self.assertEqual(
            admission.generate_admission_number(
                self.other_school, other_jss.level, 2026,
            ),
            'RVC/JSS/2026/000001',
        )

    def test_missing_school_code_blocks_number_issuance(self):
        self.school.code = ''
        self.school.save(update_fields=['code'])
        from rest_framework.exceptions import ValidationError

        with self.assertRaises(ValidationError):
            admission.generate_admission_number(self.school, self.jss_level, 2026)

    @skipUnlessDBFeature('has_select_for_update')
    def test_admission_number_is_unique_within_a_school(self):
        from django.db import IntegrityError, transaction

        self.make_student(admission_number='SUA/JSS/2026/000001')
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                self.make_student(admission_number='SUA/JSS/2026/000001')

    def test_same_number_may_exist_in_a_different_school(self):
        self.make_student(admission_number='SHARED/1')
        other = Student.objects.create(
            school=self.other_school, admission_number='SHARED/1',
            first_name='Other', last_name='School', gender='male', class_name='JSS 1',
        )
        self.assertIsNotNone(other.pk)

    def test_migration_source_is_recorded(self):
        student = self.make_student(admission_number='LEGACY/2020/1')
        admission.mark_imported(student)
        self.assertEqual(
            student.admission_number_source, Student.AdmissionNumberSource.IMPORTED,
        )


class AdmissionNumberConcurrencyTests(TransactionTestCase):
    """Real threads on separate connections, racing on the same sequence.

    Runs as a TransactionTestCase so the fixture rows are committed and visible
    to the worker connections' foreign-key checks. Skipped on SQLite, which has
    no row-level locking: `select_for_update` is a no-op there, so the guarantee
    this test asserts cannot be exercised.
    """

    @skipUnlessDBFeature('has_select_for_update')
    def test_concurrent_generation_never_repeats_a_number(self):
        school = School.objects.create(
            name='Race Academy', slug='race-academy', code='RCA',
            address='1 Race Way', state='Kano', lga='Kano Municipal',
            phone='+2348000000011', email='race@example.com', is_active=True,
            current_session='2026/2027', current_term='First Term',
        )
        level = Level.objects.create(
            school=school, code=Level.JUNIOR_SECONDARY,
            name='Junior Secondary', sort_order=30,
        )
        school_class = SchoolClass.objects.create(
            school=school, level=level, name='JSS 1', sort_order=30,
        )
        threads_count = 8
        barrier = Barrier(threads_count)
        results: list[str] = []
        errors: list[Exception] = []

        def worker():
            try:
                barrier.wait(timeout=20)
                number = admission.generate_admission_number(school, level, 2026)
                results.append(number)
            except Exception as exc:  # pragma: no cover - surfaced via assertion
                errors.append(exc)
            finally:
                connections.close_all()

        threads = [Thread(target=worker) for _ in range(threads_count)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=40)

        self.assertEqual(errors, [], f'worker errors: {errors}')
        self.assertEqual(len(results), threads_count)
        self.assertEqual(len(set(results)), threads_count, 'duplicate admission numbers issued')
        self.assertEqual(
            AdmissionSequence.objects.get(
                school=school, level=level, year=2026,
            ).last_serial,
            threads_count,
        )
        self.assertIsNotNone(school_class.pk)


class FeeStructureResolutionTests(SchoolTestCase):
    def test_class_scope_overrides_level_overrides_school(self):
        self.make_fee(amount=80000, scope=FeeStructure.Scope.SCHOOL)
        self.make_fee(
            amount=85000, scope=FeeStructure.Scope.LEVEL, level=self.jss_level,
        )
        self.make_fee(
            amount=90000, scope=FeeStructure.Scope.CLASS, school_class=self.jss1,
        )
        rows = billing.resolve_fee_structure(
            self.school, self.session, self.jss1, '',
        )
        tuition = [r for r in rows if r.fee_type == FeeStructure.FeeType.TUITION]
        self.assertEqual(len(tuition), 1)
        self.assertEqual(Decimal(tuition[0].amount), Decimal('90000'))

    def test_distinct_fee_types_from_different_scopes_all_apply(self):
        self.make_fee(
            amount=80000, scope=FeeStructure.Scope.SCHOOL,
            fee_type=FeeStructure.FeeType.TUITION,
        )
        self.make_fee(
            amount=10000, scope=FeeStructure.Scope.CLASS, school_class=self.jss1,
            fee_type=FeeStructure.FeeType.REGISTRATION, label='Registration',
        )
        rows = billing.resolve_fee_structure(self.school, self.session, self.jss1, '')
        amounts = {r.fee_type: Decimal(r.amount) for r in rows}
        self.assertEqual(amounts[FeeStructure.FeeType.TUITION], Decimal('80000'))
        self.assertEqual(amounts[FeeStructure.FeeType.REGISTRATION], Decimal('10000'))

    def test_level_row_does_not_leak_to_another_level(self):
        self.make_fee(
            amount=90000, scope=FeeStructure.Scope.LEVEL, level=self.jss_level,
        )
        self.assertEqual(
            billing.resolve_fee_structure(self.school, self.session, self.sss1, ''), [],
        )

    def test_inactive_fees_are_excluded(self):
        self.make_fee(amount=80000, is_active=False)
        self.assertEqual(
            billing.resolve_fee_structure(self.school, self.session, self.jss1, ''), [],
        )

    def test_term_scoped_fee_only_applies_to_its_term(self):
        self.make_fee(
            amount=30000, term='First Term',
            fee_type=FeeStructure.FeeType.TUITION, label='Term 1 Tuition',
        )
        self.assertEqual(len(
            billing.resolve_fee_structure(self.school, self.session, self.jss1, 'First Term'),
        ), 1)
        self.assertEqual(
            billing.resolve_fee_structure(self.school, self.session, self.jss1, 'Second Term'),
            [],
        )

    def test_annual_fee_applies_in_every_term(self):
        self.make_fee(
            amount=10000, term='',
            fee_type=FeeStructure.FeeType.REGISTRATION, label='Registration',
        )
        for term in ('First Term', 'Second Term', 'Third Term'):
            self.assertEqual(len(
                billing.resolve_fee_structure(self.school, self.session, self.jss1, term),
            ), 1, term)

    def test_conflicting_definitions_at_one_scope_are_rejected_by_the_database(self):
        from django.db import IntegrityError, transaction

        self.make_fee(amount=1000, fee_type=FeeStructure.FeeType.TUITION)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                self.make_fee(
                    amount=2000, fee_type=FeeStructure.FeeType.TUITION, label='Clash',
                )

    def test_a_later_effective_from_row_is_the_explicit_version_marker(self):
        import datetime

        self.make_fee(amount=1000, fee_type=FeeStructure.FeeType.TUITION, label='v1')
        second = FeeStructure(
            school=self.school, academic_session=self.session, scope=FeeStructure.Scope.SCHOOL,
            fee_type=FeeStructure.FeeType.TUITION, label='v2', amount=Decimal('1500'),
            effective_from=datetime.date(2026, 9, 1),
        )
        second.save()
        self.assertEqual(FeeStructure.objects.filter(
            fee_type=FeeStructure.FeeType.TUITION,
        ).count(), 2)


class InvoiceSnapshotTests(SchoolTestCase):
    def test_total_comes_from_the_snapshot_not_todays_fees(self):
        self.make_fee(amount=100000, label='Tuition')
        invoice = billing.create_invoice_for_student(
            school=self.school, student=self.make_student(),
            session=self.session, school_class=self.jss1,
        )
        self.assertEqual(invoice.total, Decimal('100000'))

        # Changing the Payment Structure must not rewrite the issued invoice.
        FeeStructure.objects.update(amount=Decimal('999999'))
        invoice.refresh_from_db()
        self.assertEqual(invoice.total, Decimal('100000'))
        self.assertEqual(Decimal(invoice.items[0]['amount']), Decimal('100000'))

    def test_snapshot_records_the_scope_each_fee_came_from(self):
        self.make_fee(
            amount=10000, scope=FeeStructure.Scope.CLASS, school_class=self.jss1,
            fee_type=FeeStructure.FeeType.REGISTRATION, label='Registration',
        )
        invoice = billing.create_invoice_for_student(
            school=self.school, student=self.make_student(),
            session=self.session, school_class=self.jss1,
        )
        self.assertEqual(invoice.items[0]['scope'], FeeStructure.Scope.CLASS)
        self.assertEqual(invoice.items[0]['scopeKey'], str(self.jss1.pk))

    def test_creating_an_invoice_twice_for_the_same_scope_is_idempotent(self):
        self.make_fee(amount=100000)
        student = self.make_student()
        first = billing.create_invoice_for_student(
            school=self.school, student=student, session=self.session, term='',
        )
        second = billing.create_invoice_for_student(
            school=self.school, student=student, session=self.session, term='',
        )
        self.assertEqual(first.pk, second.pk)
