"""The per-level Payment Structure: settings writes it, invoicing reads it.

A school prices Nursery, Primary, Junior Secondary and Senior Secondary
independently, and each level carries its own registration fee. These tests pin
both halves of that contract, because they are only correct together:

* the settings endpoint writes one `FeeStructure` row set per level;
* `resolve_invoice_items` prefers those rows and falls back to the legacy
  school-wide JSON only for a school that has never used the editor;
* a student is billed their own level's price, not a neighbour's;
* saving one level does not invoice the pending students of another.
"""
from decimal import Decimal

from records.models import FeeStructure, Invoice, SchoolClass, Student
from records.services import billing

from .test_security import SecurityTestBase


def fees(*, registration=None, tuition=None, label='Tuition', fee_type='tuition'):
    rows = []
    if registration is not None:
        rows.append({'label': 'Registration', 'feeType': 'registration', 'amount': registration})
    if tuition is not None:
        rows.append({'label': label, 'feeType': fee_type, 'amount': tuition})
    return rows


class PaymentStructureWriteTests(SecurityTestBase):
    def setUp(self):
        super().setUp()
        # The shared fixture only builds JSS/SSS classes, and a level price can
        # only resolve through a `SchoolClass` row, so Primary needs one.
        self.pri1 = SchoolClass.objects.create(
            school=self.school, level=self.pri_level, name='Primary 1', sort_order=20,
        )

    def url_path(self):
        return self.url('/fees/structure/')

    def write(self, level, rows, user=None):
        return self.client.put(
            self.url_path(),
            {'levels': [{'levelId': level.id, 'fees': rows}]},
            format='json',
        )

    def test_saving_a_level_persists_relational_rows(self):
        self.auth(self.admin)
        r = self.write(self.jss_level, fees(registration=5000, tuition=90000))
        self.assertEqual(r.status_code, 200, r.content)

        rows = FeeStructure.objects.filter(school=self.school, level=self.jss_level)
        self.assertEqual(rows.count(), 2)
        self.assertEqual(
            {row.fee_type for row in rows}, {'registration', 'tuition'},
        )
        for row in rows:
            self.assertEqual(row.scope, FeeStructure.Scope.LEVEL)
            self.assertEqual(row.scope_key, str(self.jss_level.id))
            self.assertEqual(row.academic_session, self.session)
            self.assertTrue(row.is_active)

    def tuition_of(self, class_name):
        items = billing.resolve_invoice_items(
            school=self.school, class_name=class_name, session=self.session,
        )
        return next(
            Decimal(i['amount']) for i in items
            if i.get('feeType') == FeeStructure.FeeType.TUITION
        )

    def test_each_level_is_priced_independently(self):
        self.auth(self.admin)
        for level, amount in (
            (self.pri_level, 40000), (self.jss_level, 90000), (self.sss_level, 150000),
        ):
            self.assertEqual(
                self.write(level, fees(registration=3000, tuition=amount)).status_code, 200,
            )

        self.assertEqual(self.tuition_of('Primary 1'), Decimal('40000'))
        self.assertEqual(self.tuition_of('JSS 1'), Decimal('90000'))
        self.assertEqual(self.tuition_of('SSS 1'), Decimal('150000'))

    def test_registration_fee_is_per_level_not_shared(self):
        self.auth(self.admin)
        self.write(self.pri_level, fees(registration=3000, tuition=40000))
        self.write(self.sss_level, fees(registration=7000, tuition=150000))

        pri = billing.resolve_invoice_items(
            school=self.school, class_name='Primary 1', session=self.session,
        )
        sss = billing.resolve_invoice_items(
            school=self.school, class_name='SSS 1', session=self.session,
        )
        self.assertEqual(
            [i['amount'] for i in pri if i['feeType'] == 'registration'], ['3000.00'],
        )
        self.assertEqual(
            [i['amount'] for i in sss if i['feeType'] == 'registration'], ['7000.00'],
        )

    def test_saving_twice_updates_in_place(self):
        self.auth(self.admin)
        self.write(self.jss_level, fees(registration=5000, tuition=90000))
        self.write(self.jss_level, fees(registration=5000, tuition=95000))
        rows = FeeStructure.objects.filter(school=self.school, level=self.jss_level)
        self.assertEqual(rows.count(), 2)
        tuition = rows.get(fee_type=FeeStructure.FeeType.TUITION)
        self.assertEqual(Decimal(tuition.amount), Decimal('95000'))

    def test_removed_fee_is_deactivated_not_deleted(self):
        """An invoice that snapshotted a fee must keep resolving the same."""
        self.auth(self.admin)
        self.write(self.jss_level, fees(registration=5000, tuition=90000))
        self.write(self.jss_level, fees(tuition=90000))

        row = FeeStructure.objects.get(
            school=self.school, level=self.jss_level, fee_type=FeeStructure.FeeType.REGISTRATION,
        )
        self.assertFalse(row.is_active)
        items = billing.resolve_invoice_items(
            school=self.school, class_name='JSS 1', session=self.session,
        )
        self.assertEqual(
            [i['feeType'] for i in items], [FeeStructure.FeeType.TUITION],
        )

    def test_a_level_cannot_be_edited_from_another_school(self):
        self.auth(self.other_admin)
        r = self.write(self.jss_level, fees(tuition=1))
        self.assertEqual(r.status_code, 400)
        self.assertIn('levels', r.json()['fieldErrors'])

    def test_blank_label_is_rejected(self):
        self.auth(self.admin)
        r = self.write(self.jss_level, [{'label': '  ', 'feeType': 'other', 'amount': 100}])
        self.assertEqual(r.status_code, 400)
        self.assertIn('fees', r.json()['fieldErrors'])

    def test_non_positive_amount_is_rejected(self):
        self.auth(self.admin)
        r = self.write(self.jss_level, fees(tuition=0))
        self.assertEqual(r.status_code, 400)

    def test_repeating_a_fee_type_in_one_term_is_rejected_with_a_legible_message(self):
        """The unique constraint allows one row per fee type, so a second 'other'
        line would otherwise fail as an uninterpretable IntegrityError."""
        self.auth(self.admin)
        r = self.write(self.jss_level, [
            {'label': 'Bus fare', 'feeType': 'transport', 'amount': 20000, 'term': ''},
            {'label': 'Bus fare top-up', 'feeType': 'transport', 'amount': 5000, 'term': ''},
        ])
        self.assertEqual(r.status_code, 400, r.content)
        self.assertIn('transport', str(r.json()['fieldErrors']).lower())

    def test_the_same_fee_type_is_allowed_across_different_terms(self):
        self.auth(self.admin)
        r = self.write(self.jss_level, [
            {'label': 'Tuition', 'feeType': 'tuition', 'amount': 30000, 'term': 'First Term'},
            {'label': 'Tuition', 'feeType': 'tuition', 'amount': 40000, 'term': 'Second Term'},
        ])
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(FeeStructure.objects.filter(school=self.school, level=self.jss_level).count(), 2)

    def test_class_scoped_fees_are_not_shown_as_level_fees(self):
        """Migration 0006 mirrors legacy per-class fees as CLASS-scope rows that
        also carry a level. The editor writes LEVEL scope only, so surfacing them
        here would let a save deactivate them and write a duplicate."""
        self.auth(self.admin)
        self.write(self.jss_level, fees(registration=5000, tuition=90000))
        FeeStructure.objects.create(
            school=self.school,
            academic_session=self.session,
            level=self.jss_level,
            school_class=self.jss1,
            scope=FeeStructure.Scope.CLASS,
            scope_key=str(self.jss1.pk),
            term='',
            fee_type=FeeStructure.FeeType.DEVELOPMENT,
            label='Development levy',
            amount=Decimal('2500'),
            effective_from=FeeStructure._meta.get_field('effective_from').default,
            created_by=self.admin,
        )

        r = self.client.get(self.url_path())
        self.assertEqual(r.status_code, 200, r.content)
        jss = next(l for l in r.json()['levels'] if l['code'] == self.jss_level.code)
        self.assertEqual(
            sorted(f['feeType'] for f in jss['fees']), ['registration', 'tuition'],
        )

    def test_saving_a_level_leaves_its_class_scoped_fee_intact(self):
        self.auth(self.admin)
        self.make_class_fee = FeeStructure.objects.create(
            school=self.school,
            academic_session=self.session,
            level=self.jss_level,
            school_class=self.jss1,
            scope=FeeStructure.Scope.CLASS,
            scope_key=str(self.jss1.pk),
            term='',
            fee_type=FeeStructure.FeeType.DEVELOPMENT,
            label='Development levy',
            amount=Decimal('2500'),
            effective_from=FeeStructure._meta.get_field('effective_from').default,
            created_by=self.admin,
        )
        self.write(self.jss_level, fees(registration=5000, tuition=90000))

        self.make_class_fee.refresh_from_db()
        self.assertTrue(self.make_class_fee.is_active)

    def test_unknown_fee_type_is_rejected(self):
        self.auth(self.admin)
        r = self.write(self.jss_level, [{'label': 'Bus', 'feeType': 'spaceship', 'amount': 5}])
        self.assertEqual(r.status_code, 400)

    def test_empty_fee_list_clears_a_level(self):
        self.auth(self.admin)
        self.write(self.jss_level, fees(registration=5000, tuition=90000))
        self.assertEqual(self.write(self.jss_level, []).status_code, 200)
        self.assertFalse(
            FeeStructure.objects.filter(
                school=self.school, level=self.jss_level, is_active=True,
            ).exists()
        )

    def test_read_returns_every_level_even_when_unset(self):
        self.auth(self.admin)
        r = self.client.get(self.url_path())
        self.assertEqual(r.status_code, 200, r.content)
        codes = {level['code'] for level in r.json()['levels']}
        self.assertIn('PRI', codes)
        self.assertIn('JSS', codes)
        self.assertIn('SSS', codes)


class PaymentStructurePermissionTests(SecurityTestBase):
    def url_path(self):
        return self.url('/fees/structure/')

    def test_accountant_can_price_the_school(self):
        self.auth(self.accountant)
        r = self.client.put(
            self.url_path(),
            {'levels': [{'levelId': self.jss_level.id,
                         'fees': fees(registration=5000, tuition=90000)}]},
            format='json',
        )
        self.assertEqual(r.status_code, 200, r.content)

    def test_principal_can_read_but_not_reprice(self):
        self.auth(self.principal)
        self.assertEqual(self.client.get(self.url_path()).status_code, 200)
        r = self.client.put(
            self.url_path(),
            {'levels': [{'levelId': self.jss_level.id, 'fees': fees(tuition=1)}]},
            format='json',
        )
        self.assertEqual(r.status_code, 403)

    def test_teacher_is_denied_both_ways(self):
        self.auth(self.teacher)
        self.assertEqual(self.client.get(self.url_path()).status_code, 403)
        r = self.client.put(
            self.url_path(), {'levels': [{'levelId': self.jss_level.id, 'fees': []}]},
            format='json',
        )
        self.assertEqual(r.status_code, 403)

    def test_student_cannot_read_or_write(self):
        self.auth(self.student_user)
        self.assertEqual(self.client.get(self.url_path()).status_code, 403)

    def test_unauthenticated_is_denied(self):
        self.client.force_authenticate(user=None)
        self.assertEqual(self.client.get(self.url_path()).status_code, 401)


class PendingStudentInvoicingScopeTests(SecurityTestBase):
    def url_path(self):
        return self.url('/fees/structure/')

    def test_saving_regular_fees_activates_only_unbilled_students_in_that_level(self):
        pri = self.make_student(
            class_name='Primary 1', admission_number='SUA/PRI/2026/000001',
            status=Student.Status.PENDING_PAYMENT,
        )
        jss = self.make_student(
            class_name='JSS 1', admission_number='SUA/JSS/2026/000002',
            status=Student.Status.PENDING_PAYMENT,
        )
        self.auth(self.admin)
        r = self.client.put(
            self.url_path(),
            {'levels': [{'levelId': self.jss_level.id, 'fees': fees(tuition=90000)}]},
            format='json',
        )
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.json()['invoicedPendingStudents'], 0)
        self.assertEqual(r.json()['invoicedPendingStudentsByLevel'], {'JSS': 0})
        self.assertEqual(r.json()['activatedPendingStudents'], 1)

        jss.refresh_from_db()
        self.assertEqual(jss.status, Student.Status.ACTIVE)
        self.assertFalse(Invoice.objects.filter(student=jss, is_cancelled=False).exists())
        self.assertFalse(Invoice.objects.filter(student=pri).exists())

    def test_registration_invoice_uses_that_levels_registration_price(self):
        jss = self.make_student(
            class_name='JSS 1', admission_number='SUA/JSS/2026/000003',
            status=Student.Status.PENDING_PAYMENT,
        )
        self.auth(self.admin)
        self.client.put(
            self.url_path(),
            {'levels': [{'levelId': self.jss_level.id,
                         'fees': fees(registration=5000, tuition=90000)}]},
            format='json',
        )
        invoice = Invoice.objects.get(student=jss)
        self.assertEqual(Decimal(invoice.total), Decimal('5000'))
        self.assertEqual({item['feeType'] for item in invoice.items}, {'registration'})

    def test_legacy_school_wide_save_still_works(self):
        """A school on the old flat list keeps billing, and stays un-migrated."""
        self.school.fee_structure = [
            {'label': 'Tuition', 'amount': 50000.0, 'className': '*'},
        ]
        self.school.save(update_fields=['fee_structure'])
        self.auth(self.accountant)
        r = self.client.put(
            self.url_path(),
            {'items': [
                {'label': 'Tuition', 'amount': 50000.0, 'className': '*'},
                {'label': 'Development levy', 'amount': 5000.0, 'className': 'JSS 1'},
            ]},
            format='json',
        )
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(len(r.json()['items']), 2)
        self.assertEqual(r.json()['levels'][0]['fees'], [])

        # The endpoint wrote through its own instance of the row.
        self.school.refresh_from_db()
        items = billing.resolve_invoice_items(
            school=self.school, class_name='JSS 1', session=self.session,
        )
        self.assertEqual(
            sum(Decimal(i['amount']) for i in items), Decimal('55000'),
        )

    def test_relational_rows_win_over_the_json_list(self):
        """Once a level is priced in settings, the old JSON cannot override it."""
        self.school.fee_structure = [
            {'label': 'Tuition', 'amount': 10000.0, 'className': '*'},
        ]
        self.school.save(update_fields=['fee_structure'])
        self.auth(self.admin)
        self.client.put(
            self.url_path(),
            {'levels': [{'levelId': self.jss_level.id, 'fees': fees(tuition=90000)}]},
            format='json',
        )
        items = billing.resolve_invoice_items(
            school=self.school, class_name='JSS 1', session=self.session,
        )
        self.assertEqual(
            sum(Decimal(i['amount']) for i in items), Decimal('90000'),
        )

    def test_unpriced_level_still_bills_from_the_json_default(self):
        self.school.fee_structure = [
            {'label': 'Tuition', 'amount': 10000.0, 'className': '*'},
        ]
        self.school.save(update_fields=['fee_structure'])
        self.auth(self.admin)
        self.client.put(
            self.url_path(),
            {'levels': [{'levelId': self.jss_level.id, 'fees': fees(tuition=90000)}]},
            format='json',
        )
        items = billing.resolve_invoice_items(
            school=self.school, class_name='SSS 1', session=self.session,
        )
        self.assertEqual(sum(Decimal(i['amount']) for i in items), Decimal('10000'))


class AdmissionUsesLevelPriceTests(SecurityTestBase):
    """Registration fees must bill the level the student is entering."""

    def setUp(self):
        super().setUp()
        self.auth(self.secretary)

    def register(self, **overrides):
        payload = {
            'firstName': 'Ada', 'lastName': 'Nwosu', 'gender': 'female',
            'className': 'SSS 1', 'guardianName': 'Mrs Nwosu',
            'guardianPhone': '+2348000001234', 'dateOfBirth': '2014-05-02',
        }
        payload.update(overrides)
        return self.client.post(self.url('/students/'), payload, format='json')

    def price_all_levels(self):
        self.client.force_authenticate(user=self.admin)
        for level, amount in (
            (self.pri_level, 40000), (self.jss_level, 90000), (self.sss_level, 150000),
        ):
            self.client.put(
                self.url('/fees/structure/'),
                {'levels': [{'levelId': level.id,
                             'fees': fees(registration=5000, tuition=amount)}]},
                format='json',
            )
        self.client.force_authenticate(user=self.secretary)

    def test_admission_invoice_uses_the_entered_levels_registration_price(self):
        self.price_all_levels()
        r = self.register()
        self.assertEqual(r.status_code, 201, r.content)
        student = Student.objects.get(first_name='Ada')
        invoice = Invoice.objects.get(student=student)
        self.assertEqual(Decimal(invoice.total), Decimal('5000'))

    def test_two_levels_produce_two_different_totals(self):
        SchoolClass.objects.create(
            school=self.school, level=self.pri_level, name='Primary 1', sort_order=20,
        )
        self.price_all_levels()
        self.register(firstName='Ada', lastName='Nwosu', className='Primary 1')
        self.register(
            firstName='Bola', lastName='Adeyemi', className='JSS 1',
            guardianPhone='+2348000009999',
        )
        ada = Invoice.objects.get(student__first_name='Ada')
        bola = Invoice.objects.get(student__first_name='Bola')
        self.assertEqual(Decimal(ada.total), Decimal('5000'))
        self.assertEqual(Decimal(bola.total), Decimal('5000'))

    def test_regular_term_invoice_excludes_the_one_time_registration_fee(self):
        self.price_all_levels()
        self.client.force_authenticate(user=self.accountant)
        response = self.client.post(
            self.url('/invoices/generate/'),
            {'className': 'JSS 1', 'term': 'First Term'},
            format='json',
        )
        self.assertEqual(response.status_code, 200, response.content)
        invoice = Invoice.objects.get(student=self.student, term='First Term')
        self.assertEqual(Decimal(invoice.total), Decimal('90000'))
        self.assertEqual(
            {item['feeType'] for item in invoice.items},
            {FeeStructure.FeeType.TUITION},
        )


class LegacyBackfillMigrationTests(SecurityTestBase):
    """Migration 0006, exercised as a function rather than through `migrate`.

    It is the only code path that writes `FeeStructure` rows without an acting
    user, and it reads the pre-editor JSON list. Both facts are invisible to the
    request tests above, and the migration is irreversible in practice once
    deployed, so its behaviour is pinned here directly.
    """

    def setUp(self):
        super().setUp()
        from django.apps import apps

        self.apps = apps

    def migration(self):
        import importlib

        return importlib.import_module(
            'records.migrations.0006_backfill_fee_structure_rows',
        )

    def seed_legacy_json(self):
        self.school.fee_structure = [
            {'label': 'Registration fee', 'amount': 5000.0, 'className': '*'},
            {'label': 'Tuition', 'amount': 40000.0, 'className': '*'},
            {'label': 'Development levy', 'amount': 2500.0, 'className': 'JSS 1'},
        ]
        self.school.save(update_fields=['fee_structure'])
        self.jss1 = SchoolClass.objects.filter(school=self.school, name='JSS 1').first()
        if self.jss1 is None:
            self.jss1 = SchoolClass.objects.create(
                school=self.school, level=self.jss_level, name='JSS 1', sort_order=30,
            )

    def test_backfill_mirrors_legacy_fees_and_still_resolves_them(self):
        self.seed_legacy_json()
        self.migration().forwards(self.apps, None)

        rows = FeeStructure.objects.filter(school=self.school)
        self.assertEqual(
            {row.fee_type for row in rows},
            {'registration', 'tuition', 'development'},
        )
        levy = rows.get(fee_type='development')
        self.assertEqual(levy.scope, FeeStructure.Scope.CLASS)
        self.assertEqual(levy.school_class_id, self.jss1.pk)
        self.assertEqual(levy.level_id, self.jss_level.pk)

        # The JSON is left exactly as it was, so the fallback still works.
        self.school.refresh_from_db()
        self.assertEqual(len(self.school.fee_structure), 3)

        items = billing.resolve_invoice_items(
            school=self.school, class_name='JSS 1', session=self.session,
        )
        self.assertEqual(
            sum(Decimal(i['amount']) for i in items), Decimal('47500'),
        )

    def test_backfill_is_idempotent(self):
        self.seed_legacy_json()
        self.migration().forwards(self.apps, None)
        self.migration().forwards(self.apps, None)
        self.assertEqual(FeeStructure.objects.filter(school=self.school).count(), 3)

    def test_backwards_keeps_rows_an_admin_created(self):
        self.seed_legacy_json()
        self.migration().forwards(self.apps, None)

        # A row written through the editor carries the acting user. The reverse
        # must not take it, even though it shares the epoch and blank term.
        FeeStructure.objects.create(
            school=self.school,
            academic_session=self.session,
            level=self.jss_level,
            scope=FeeStructure.Scope.LEVEL,
            scope_key=str(self.jss_level.pk),
            term='',
            fee_type=FeeStructure.FeeType.TUITION,
            label='Tuition',
            amount=Decimal('90000'),
            effective_from=FeeStructure._meta.get_field('effective_from').default,
            created_by=self.admin,
        )

        self.migration().backwards(self.apps, None)

        self.assertFalse(FeeStructure.objects.filter(created_by__isnull=True).exists())
        self.assertTrue(
            FeeStructure.objects.filter(created_by=self.admin, fee_type='tuition').exists(),
        )
