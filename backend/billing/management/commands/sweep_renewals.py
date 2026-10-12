"""Per-student access renewal sweep.

Runs daily. For each entitlement whose paid period ended before today and has
no successor period, attempts one independent renewal:

* wallet covers the current student price → debit once, new rolling period
  linked via `renewed_from`, school keeps access;
* wallet short → no charge, no renewal; the school administrator is notified
  once per entitlement (dedupe key), and the entitlement ages into grace,
  then expired, per the platform grace policy.

Successful renewals are never rolled back because a later student in the same
run cannot be funded: each student is evaluated and written independently.

Single-flight across workers via the shared sweep advisory lock. Safe to
re-run: successor check + unique (student, period_start) make retries no-ops.
"""
from django.core.management.base import BaseCommand
from django.db import IntegrityError, transaction
from django.utils import timezone
from datetime import timedelta

from accounts.services.notifications import notify_roles
from records.services.sweep_lock import release_sweep_lock, try_acquire_sweep_lock
from schools.models import School

from billing import services
from billing.models import StudentEntitlement, WalletTransaction


class Command(BaseCommand):
    help = 'Renew per-student access entitlements that lapsed, wallet permitting.'

    def add_arguments(self, parser):
        parser.add_argument('--school', help='Limit the sweep to one school id.')

    def handle(self, *args, **options):
        if not try_acquire_sweep_lock('access_renewals'):
            self.stdout.write('Another sweep_renewals is running; exiting.')
            return
        try:
            self._run(*args, **options)
        finally:
            release_sweep_lock('access_renewals')

    def _run(self, *args, **options):
        today = timezone.localdate()
        pricing = services.get_pricing()
        if not pricing.auto_renew:
            self.stdout.write('Automatic renewal is disabled; nothing to do.')
            return
        schools = School.objects.filter(is_active=True)
        if options['school']:
            schools = schools.filter(pk=options['school'])
        renewed = failed = 0
        for school in schools:
            due = StudentEntitlement.objects.filter(
                school=school, period_end__lt=today,
            ).order_by('period_end', 'id')
            school_renewed: list[str] = []
            school_failed: list[str] = []
            for old in due:
                if StudentEntitlement.objects.filter(
                    student=old.student, renewed_from=old,
                ).exists():
                    continue
                if services.live_entitlement(old.student, today) is not None:
                    continue
                try:
                    with transaction.atomic():
                        student = old.student
                        wallet = services._lock_wallet(school)
                        if wallet.balance_kobo < pricing.student_price_kobo:
                            raise services.InsufficientFunds(
                                pricing.student_price_kobo, wallet.balance_kobo,
                                'student renewal',
                            )
                        period_end = today + timedelta(
                            days=services._period_days(),
                        )
                        new = StudentEntitlement.objects.create(
                            student=student,
                            school=school,
                            period_start=today,
                            period_end=period_end,
                            amount_kobo=pricing.student_price_kobo,
                            renewed_from=old,
                        )
                        before = wallet.balance_kobo
                        wallet.balance_kobo = before - pricing.student_price_kobo
                        wallet.save(update_fields=['balance_kobo', 'updated_at'])
                        entry = WalletTransaction.objects.create(
                            school=school,
                            reference=services._ref('WTX'),
                            direction=WalletTransaction.Direction.DEBIT,
                            amount_kobo=pricing.student_price_kobo,
                            category=WalletTransaction.Category.STUDENT_RENEWAL,
                            status=WalletTransaction.Status.SUCCESS,
                            student=student,
                            balance_before_kobo=before,
                            balance_after_kobo=wallet.balance_kobo,
                            description=(
                                f'Student access renewal for {student} '
                                f'({today} – {period_end}).'
                            ),
                        )
                        new.wallet_transaction = entry
                        new.save(update_fields=['wallet_transaction'])
                except services.InsufficientFunds:
                    school_failed.append(_student_label(old))
                    notify_roles(
                        school, ('school_admin',),
                        type='payment',
                        title='Student renewal needs wallet funds',
                        body=(
                            f'{_student_label(old)} could not be renewed: '
                            f'₦{pricing.student_price_kobo / 100:,.2f} required. '
                            f'Fund the wallet in Wallet & Billing.'
                        ),
                        dedupe_key=f'renewal-failed:{old.pk}:{today.isoformat()}',
                    )
                    failed += 1
                    continue
                except IntegrityError:
                    # A concurrent renewal won this student; successor check
                    # above makes the retry a no-op.
                    continue
                school_renewed.append(_student_label(old))
                renewed += 1
            if school_renewed or school_failed:
                notify_roles(
                    school, ('school_admin',),
                    type='payment',
                    title='Student renewals processed',
                    body=(
                        f'{len(school_renewed)} student(s) renewed'
                        + (
                            f', {len(school_failed)} need(s) wallet funds: '
                            + ', '.join(school_failed[:5])
                            if school_failed else ''
                        )
                        + '.'
                    ),
                    dedupe_key=f'renewal-summary:{school.pk}:{today.isoformat()}',
                )
        self.stdout.write(
            f'Access renewals: {renewed} renewed, {failed} need funds.',
        )


def _student_label(entitlement) -> str:
    student = entitlement.student
    name = f'{student.first_name} {student.last_name}'.strip()
    number = student.admission_number or ''
    return f'{name} ({number})'.strip() if number else (name or str(student.pk))
