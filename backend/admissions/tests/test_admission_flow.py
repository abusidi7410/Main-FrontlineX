from __future__ import annotations

from admissions.models import AdmissionApplication, AdmissionSettings
from records.models import Enrollment, Registration, Student
from records.tests.base import SchoolTestCase


class AdmissionFlowTests(SchoolTestCase):
    def setUp(self):
        super().setUp()
        AdmissionSettings.objects.create(
            school=self.school, required_documents=[], referee_required=False,
        )

    def payload(self, **overrides):
        data = {
            'firstName': 'Amina',
            'middleName': 'Bello',
            'lastName': 'Yusuf',
            'gender': 'female',
            'dateOfBirth': '2015-04-12',
            'nationality': 'Nigerian',
            'stateOfOrigin': 'Kano',
            'lgaOfOrigin': 'Kano Municipal',
            'classId': self.jss1.id,
            'academicSessionId': self.session.id,
            'guardianName': 'Bello Yusuf',
            'guardianRelationship': 'Father',
            'guardianPhone': '08031234567',
            'guardianEmail': 'bello@example.com',
            'guardianAddress': '12 Zoo Road, Kano',
            'emergencyContactName': 'Bello Yusuf',
            'emergencyContactPhone': '08031234567',
            'declaredBy': 'Bello Yusuf',
        }
        data.update(overrides)
        return data

    def create(self, **overrides):
        return self.client.post(
            self.url('/admissions/applications/'), self.payload(**overrides), format='json',
        )

    def test_draft_can_be_created_updated_and_submitted(self):
        self.auth(self.secretary)
        response = self.create()
        self.assertEqual(response.status_code, 201, response.data)
        application_id = response.data['id']
        self.assertEqual(response.data['status'], 'draft')
        self.assertEqual(response.data['levelCode'], 'JSS')
        self.assertEqual(response.data['className'], 'JSS 1')

        # A draft may be incomplete: a partial patch is accepted.
        response = self.client.patch(
            self.url(f'/admissions/applications/{application_id}/'),
            {'religion': 'Islam', 'medicalConditions': 'Asthma'},
            format='json',
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['religion'], 'Islam')

        response = self.client.post(
            self.url(f'/admissions/applications/{application_id}/submit/'), {}, format='json',
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['status'], 'submitted')
        self.assertIsNotNone(response.data['submittedAt'])

        application = AdmissionApplication.objects.get(public_id=application_id)
        self.assertIsNotNone(application.declared_at)

        # A submitted application is no longer editable.
        response = self.client.patch(
            self.url(f'/admissions/applications/{application_id}/'),
            {'religion': 'Christianity'}, format='json',
        )
        self.assertEqual(response.status_code, 400)

    def test_submit_requires_the_form_and_returns_field_errors(self):
        self.auth(self.secretary)
        response = self.create(
            firstName='', lastName='', guardianName='', guardianPhone='',
            guardianAddress='', classId=None, declaredBy='',
        )
        self.assertEqual(response.status_code, 201)
        application_id = response.data['id']

        response = self.client.post(
            self.url(f'/admissions/applications/{application_id}/submit/'), {}, format='json',
        )
        self.assertEqual(response.status_code, 400)
        for field in (
            'firstName', 'lastName', 'guardianName', 'guardianPhone',
            'guardianAddress', 'classId', 'declaredBy',
        ):
            self.assertIn(field, response.data['fieldErrors'], field)

    def test_approval_creates_the_same_student_opening_state_as_manual_entry(self):
        self.auth(self.secretary)
        application_id = self.create().data['id']
        self.client.post(
            self.url(f'/admissions/applications/{application_id}/submit/'), {}, format='json',
        )

        self.auth(self.principal)
        response = self.client.post(
            self.url(f'/admissions/applications/{application_id}/approve/'), {}, format='json',
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['status'], 'approved')
        self.assertEqual(response.data['admissionNumber'], 'SUA/JSS/2026/000001')

        student = Student.objects.get(school=self.school, admission_number='SUA/JSS/2026/000001')
        self.assertEqual(student.first_name, 'Amina')
        self.assertEqual(student.last_name, 'Yusuf')
        self.assertEqual(student.class_name, 'JSS 1')
        self.assertEqual(student.status, Student.Status.ACTIVE)
        self.assertEqual(student.admission_year, 2026)
        self.assertEqual(student.admission_number_source, Student.AdmissionNumberSource.SYSTEM_GENERATED)
        # The guardian phone is normalized to E.164 for the parent login.
        self.assertEqual(student.guardian_phone, '+2348031234567')

        application = AdmissionApplication.objects.get(public_id=application_id)
        self.assertEqual(application.student_id, student.id)
        self.assertEqual(application.reviewed_by, self.principal)

        registration = Registration.objects.get(student=student)
        self.assertEqual(registration.status, Registration.Status.APPROVED)
        self.assertTrue(Enrollment.objects.filter(student=student, status=Enrollment.Status.ACTIVE).exists())

        # Approving twice is refused, not silently duplicated.
        response = self.client.post(
            self.url(f'/admissions/applications/{application_id}/approve/'), {}, format='json',
        )
        self.assertEqual(response.status_code, 400)

    def test_duplicate_application_is_blocked_unless_confirmed(self):
        self.auth(self.secretary)
        first = self.create().data['id']
        self.client.post(
            self.url(f'/admissions/applications/{first}/submit/'), {}, format='json',
        )
        second = self.create().data['id']

        response = self.client.post(
            self.url(f'/admissions/applications/{second}/submit/'), {}, format='json',
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn('duplicateApplicationId', response.data['fieldErrors'])

        response = self.client.post(
            self.url(f'/admissions/applications/{second}/submit/'),
            {'allowDuplicate': True}, format='json',
        )
        self.assertEqual(response.status_code, 200, response.data)
        second_app = AdmissionApplication.objects.get(public_id=second)
        self.assertEqual(str(second_app.duplicate_of.public_id), first)

    def test_reject_and_withdraw_are_final(self):
        self.auth(self.secretary)
        application_id = self.create().data['id']
        self.client.post(
            self.url(f'/admissions/applications/{application_id}/submit/'), {}, format='json',
        )
        self.auth(self.admin)
        response = self.client.post(
            self.url(f'/admissions/applications/{application_id}/reject/'),
            {'reason': 'Class is full.'}, format='json',
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['status'], 'rejected')
        self.assertEqual(response.data['decisionReason'], 'Class is full.')

        self.auth(self.secretary)
        response = self.client.post(
            self.url(f'/admissions/applications/{application_id}/withdraw/'), {}, format='json',
        )
        self.assertEqual(response.status_code, 400)

    def test_roles_and_tenants_are_enforced(self):
        self.auth(self.secretary)
        application_id = self.create().data['id']
        self.client.post(
            self.url(f'/admissions/applications/{application_id}/submit/'), {}, format='json',
        )

        self.auth(self.teacher)
        self.assertEqual(
            self.client.get(self.url('/admissions/applications/')).status_code, 403,
        )
        self.assertEqual(
            self.client.post(
                self.url(f'/admissions/applications/{application_id}/approve/'), {}, format='json',
            ).status_code, 403,
        )

        self.auth(self.accountant)
        self.assertEqual(
            self.client.get(self.url('/admissions/applications/')).status_code, 200,
        )
        self.assertEqual(
            self.client.post(
                self.url(f'/admissions/applications/{application_id}/approve/'), {}, format='json',
            ).status_code, 403,
        )

        self.auth(self.secretary)
        self.assertEqual(
            self.client.post(
                self.url(f'/admissions/applications/{application_id}/approve/'), {}, format='json',
            ).status_code, 403,
        )

        # Another school's administrator cannot see the application at all.
        self.auth(self.other_admin)
        response = self.client.get(
            self.url(f'/admissions/applications/{application_id}/'),
        )
        self.assertEqual(response.status_code, 404)

    def test_stats_and_dashboard_filters(self):
        self.auth(self.secretary)
        first = self.create().data['id']
        second = self.create(firstName='Musa', lastName='Ali', guardianPhone='08099887766').data['id']
        self.client.post(self.url(f'/admissions/applications/{first}/submit/'), {}, format='json')

        response = self.client.get(self.url('/admissions/stats/'))
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['total'], 2)
        self.assertEqual(response.data['draft'], 1)
        self.assertEqual(response.data['submitted'], 1)
        self.assertEqual(response.data['needsReview'], 1)

        response = self.client.get(self.url('/admissions/applications/?status=draft&search=Musa'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['count'], 1)
        self.assertEqual(response.data['results'][0]['id'], second)

    def test_settings_are_admin_only(self):
        self.auth(self.accountant)
        self.assertEqual(self.client.get(self.url('/admissions/settings/')).status_code, 200)
        self.assertEqual(
            self.client.patch(
                self.url('/admissions/settings/'), {'refereeRequired': True}, format='json',
            ).status_code, 403,
        )

        self.auth(self.admin)
        response = self.client.patch(
            self.url('/admissions/settings/'),
            {'refereeRequired': True, 'requiredDocuments': ['birth_certificate']},
            format='json',
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['requiredDocuments'], ['birth_certificate'])
        self.assertTrue(response.data['refereeRequired'])

    def test_approval_accepts_a_school_assigned_number_and_rejects_a_duplicate(self):
        self.auth(self.secretary)
        application_id = self.create().data['id']
        self.client.post(
            self.url(f'/admissions/applications/{application_id}/submit/'), {}, format='json',
        )

        Student.objects.create(
            school=self.school,
            admission_number='SUA/JSS/2026/000009',
            first_name='Existing',
            last_name='Pupil',
            gender=Student.Gender.MALE,
            class_name='JSS 1',
        )
        self.auth(self.principal)
        response = self.client.post(
            self.url(f'/admissions/applications/{application_id}/approve/'),
            {'admissionNumber': 'SUA/JSS/2026/000009'}, format='json',
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn('admissionNumber', response.data['fieldErrors'])

        response = self.client.post(
            self.url(f'/admissions/applications/{application_id}/approve/'),
            {'admissionNumber': 'SUA/JSS/2026/000010'}, format='json',
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['admissionNumber'], 'SUA/JSS/2026/000010')

    def test_admission_charge_is_skipped_when_enforcement_is_off(self):
        from billing.models import PlatformPricing

        pricing = PlatformPricing.objects.get(pk=1)
        self.assertFalse(pricing.enforce_student_access)
        # The default shared fixture is unenforced; approval must not need a wallet.
        self.auth(self.secretary)
        application_id = self.create().data['id']
        self.client.post(
            self.url(f'/admissions/applications/{application_id}/submit/'), {}, format='json',
        )
        self.auth(self.principal)
        response = self.client.post(
            self.url(f'/admissions/applications/{application_id}/approve/'), {}, format='json',
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertIsNone(response.data['access'])

    def test_totals_in_response_are_decimal_strings(self):
        self.auth(self.secretary)
        application_id = self.create().data['id']
        self.client.post(
            self.url(f'/admissions/applications/{application_id}/submit/'), {}, format='json',
        )
        self.auth(self.principal)
        response = self.client.post(
            self.url(f'/admissions/applications/{application_id}/approve/'), {}, format='json',
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn(response.data['invoiceTotal'], ('', '0', '0.00'))

    def test_review_start_transition(self):
        self.auth(self.secretary)
        application_id = self.create().data['id']
        self.client.post(
            self.url(f'/admissions/applications/{application_id}/submit/'), {}, format='json',
        )
        self.auth(self.principal)
        response = self.client.post(
            self.url(f'/admissions/applications/{application_id}/start-review/'), {}, format='json',
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['status'], 'under_review')


class AdmissionDraftIsolationTests(SchoolTestCase):
    def test_draft_is_not_visible_to_another_school(self):
        AdmissionSettings.objects.create(school=self.school, required_documents=[])
        self.auth(self.admin)
        response = self.client.post(
            self.url('/admissions/applications/'),
            {'firstName': 'A', 'lastName': 'B'},
            format='json',
        )
        self.assertEqual(response.status_code, 201, response.data)
        application_id = response.data['id']

        self.auth(self.other_admin)
        self.assertEqual(
            self.client.get(self.url(f'/admissions/applications/{application_id}/')).status_code,
            404,
        )
        self.assertEqual(
            self.client.get(
                self.url(f'/admissions/applications/{application_id}/documents/'),
            ).status_code,
            404,
        )


class AdmissionApprovalBillingTests(SchoolTestCase):
    """Approval reuses the per-student activation debit exactly like manual entry.

    Enforcement is on here (the shared base runs unenforced), so an approval
    must fund the activation from the wallet and surface the same access payload
    the student-create endpoint returns.
    """

    def setUp(self):
        super().setUp()
        from billing import services as billing_services
        from billing.models import PlatformPricing, WalletTransaction

        self.pricing = PlatformPricing.objects.get(pk=1)
        self.pricing.enforce_student_access = True
        self.pricing.save(update_fields=['enforce_student_access'])
        billing_services.credit_wallet(
            self.school, 50000, category=WalletTransaction.Category.DEPOSIT,
            created_by=self.admin,
        )
        AdmissionSettings.objects.create(
            school=self.school, required_documents=[], referee_required=False,
        )

    def approve(self):
        self.auth(self.secretary)
        application_id = self.client.post(
            self.url('/admissions/applications/'),
            {
                'firstName': 'Amina', 'lastName': 'Yusuf', 'gender': 'female',
                'dateOfBirth': '2015-04-12', 'classId': self.jss1.id,
                'academicSessionId': self.session.id,
                'guardianName': 'Bello Yusuf', 'guardianPhone': '08031234567',
                'guardianAddress': '12 Zoo Road, Kano', 'declaredBy': 'Bello Yusuf',
            },
            format='json',
        ).data['id']
        self.client.post(
            self.url(f'/admissions/applications/{application_id}/submit/'), {}, format='json',
        )
        self.auth(self.principal)
        return self.client.post(
            self.url(f'/admissions/applications/{application_id}/approve/'), {}, format='json',
        )

    def test_approval_debits_the_wallet_once_and_reports_access(self):
        from billing import services as billing_services
        from billing.models import StudentEntitlement

        response = self.approve()
        self.assertEqual(response.status_code, 200, response.data)
        access = response.data['access']
        self.assertIsNotNone(access)
        self.assertEqual(access['amountKobo'], self.pricing.student_price_kobo)
        self.assertIsNotNone(access['periodStart'])
        self.assertIsNotNone(access['periodEnd'])

        student = Student.objects.get(school=self.school, admission_number='SUA/JSS/2026/000001')
        self.assertEqual(
            StudentEntitlement.objects.filter(student=student).count(), 1,
        )
        self.assertEqual(
            billing_services.get_wallet(self.school).balance_kobo,
            50000 - self.pricing.student_price_kobo,
        )

    def test_approval_without_funds_is_rejected_and_creates_nothing(self):
        from billing.models import Wallet

        Wallet.objects.filter(school=self.school).update(balance_kobo=0)
        response = self.approve()
        self.assertEqual(response.status_code, 402, response.data)
        self.assertEqual(response.data['availableKobo'], 0)
        self.assertEqual(response.data['requiredKobo'], self.pricing.student_price_kobo)
        self.assertFalse(
            Student.objects.filter(school=self.school, first_name='Amina').exists(),
        )
        application = AdmissionApplication.objects.get(school=self.school)
        self.assertEqual(application.status, AdmissionApplication.Status.SUBMITTED)
        self.assertIsNone(application.student_id)
