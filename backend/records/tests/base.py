"""Shared fixtures for the records test suite.

Builds a realistic school — code, levels, classes, session, fee structure — and
one user per role so authorisation tests can assert on real role boundaries
rather than mocks.
"""
from __future__ import annotations

from decimal import Decimal

from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from accounts.models import User
from records.models import (
    AcademicSession,
    FeeStructure,
    Invoice,
    Level,
    SchoolClass,
    Student,
)
from schools.models import School, SchoolSubscription, SubscriptionPlan


class SchoolTestCase(TestCase):
    """Base class: a school with a full academic structure plus role users."""

    school_code = 'SUA'

    # PBKDF2 hashing of seven users per test dominates the suite runtime and is
    # irrelevant to what these tests assert. MD5 keeps the suite fast; this
    # override is test-only and never touches production settings.
    @override_settings(PASSWORD_HASHERS=[
        'django.contrib.auth.hashers.MD5PasswordHasher',
    ])
    def setUp(self):
        super().setUp()
        self.school = School.objects.create(
            name='Success Academy', slug='success-academy', code=self.school_code,
            address='1 Academy Way', state='Kano', lga='Kano Municipal',
            phone='+2348000000011', email='success@example.com', is_active=True,
            current_session='2026/2027', current_term='First Term',
        )
        self.other_school = School.objects.create(
            name='Rival College', slug='rival-college', code='RVC',
            address='2 Rival Road', state='Lagos', lga='Ikeja',
            phone='+2348000000099', email='rival@example.com', is_active=True,
            current_session='2026/2027',
        )
        plan = SubscriptionPlan.objects.create(
            name='standard', min_students=1, max_students=5000, monthly_price=100,
            # Usage allowances the platform enforces on paid services. The
            # fixture mirrors a real paid plan so allowance logic is exercised
            # with headroom; exhaustion tests zero these out per-test.
            monthly_sms_allowance=1000,
            monthly_otp_allowance=1000,
            monthly_ai_allowance=1000,
            sms_cost_per_unit=200,
            otp_cost_per_unit=100,
            ai_cost_per_credit=50,
        )
        SchoolSubscription.objects.create(
            school=self.school, plan=plan, status=SchoolSubscription.Status.ACTIVE,
        )
        SchoolSubscription.objects.create(
            school=self.other_school, plan=plan, status=SchoolSubscription.Status.ACTIVE,
        )

        self.session = AcademicSession.objects.create(
            school=self.school, name='2026/2027', start_year=2026, end_year=2027,
            is_current=True,
        )
        AcademicSession.objects.create(
            school=self.other_school, name='2026/2027',
            start_year=2026, end_year=2027, is_current=True,
        )

        self.jss_level = Level.objects.create(
            school=self.school, code=Level.JUNIOR_SECONDARY,
            name='Junior Secondary', sort_order=30,
        )
        self.pri_level = Level.objects.create(
            school=self.school, code=Level.PRIMARY, name='Primary', sort_order=20,
        )
        self.sss_level = Level.objects.create(
            school=self.school, code=Level.SENIOR_SECONDARY,
            name='Senior Secondary', sort_order=40,
        )
        self.jss1 = SchoolClass.objects.create(
            school=self.school, level=self.jss_level, name='JSS 1', sort_order=30,
        )
        self.jss2 = SchoolClass.objects.create(
            school=self.school, level=self.jss_level, name='JSS 2', sort_order=31,
        )
        self.sss1 = SchoolClass.objects.create(
            school=self.school, level=self.sss_level, name='SSS 1', sort_order=40,
        )

        self._make_users()
        self.client = APIClient()

    def _make_users(self):
        def make(email, role, school=None, **kwargs):
            return User.objects.create_user(
                email=email, password='Strong-Pass-1!',
                first_name=email.split('@')[0].title(), last_name='Test',
                role=role, school=school, is_active=True, **kwargs,
            )

        self.admin = make('admin@success.example', User.Role.SCHOOL_ADMIN, self.school)
        self.principal = make('principal@success.example', User.Role.PRINCIPAL, self.school)
        self.accountant = make('accountant@success.example', User.Role.ACCOUNTANT, self.school)
        self.teacher = make('teacher@success.example', User.Role.TEACHER, self.school)
        self.secretary = make('secretary@success.example', User.Role.SECRETARY, self.school)
        self.parent = make('parent@success.example', User.Role.PARENT, self.school)
        self.student_user = make('student@success.example', User.Role.STUDENT, self.school)
        self.other_admin = make('admin@rival.example', User.Role.SCHOOL_ADMIN, self.other_school)

    # ── helpers ────────────────────────────────────────────────────────────

    def auth(self, user):
        self.client.force_authenticate(user)
        return user

    def url(self, path):
        return f'/api/v1{path}'

    def make_student(self, **kwargs):
        defaults = {
            'school': self.school,
            'admission_number': f'SUA/T/{kwargs.pop("admission_number", "STU")}',
            'first_name': 'Test', 'last_name': 'Student',
            'gender': Student.Gender.MALE, 'class_name': 'JSS 1',
        }
        defaults.update(kwargs)
        return Student.objects.create(**defaults)

    def make_fee(self, *, amount, label='Tuition', scope=FeeStructure.Scope.SCHOOL,
                 fee_type=FeeStructure.FeeType.TUITION, school_class=None, level=None,
                 term='', session=None, is_active=True):
        fee = FeeStructure(
            school=self.school,
            academic_session=session or self.session,
            term=term,
            scope=scope,
            fee_type=fee_type,
            label=label,
            amount=Decimal(amount),
            is_active=is_active,
        )
        if school_class is not None:
            fee.school_class = school_class
            fee.level = school_class.level
        elif level is not None:
            fee.level = level
        fee.save()
        return fee

    def make_invoice(self, *, student=None, total='115000', term='',
                     session=None, items=None, **kwargs):
        return Invoice.objects.create(
            school=self.school,
            student=student or self.make_student(),
            academic_session=session or self.session,
            term=term,
            total=Decimal(total),
            items=items if items is not None else [
                {'feeType': 'tuition', 'label': 'Tuition', 'amount': str(total)},
            ],
            **kwargs,
        )
