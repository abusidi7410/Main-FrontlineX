"""Daily notification sweep (spec 32).

Two of the eight notification types describe something that becomes true by
passing rather than by somebody pressing a button, so they cannot be emitted
from inside a request:

* a register that was never taken
* a subscription that is about to lapse

Both are "has anything happened since we last looked?" questions, which is
what this command answers. Run it once a day from cron; it is idempotent, so a
second run on the same day adds nothing and a missed run is not a lost
notification the following day.
"""

from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from records.services import events as event_service
from records.services.sweep_lock import release_sweep_lock, try_acquire_sweep_lock
from schools.models import School, SchoolSubscription

#: Days before expiry at which the school is warned. Only the closest one fires
#: per subscription, chosen by the dedupe key inside the emitter.
REMINDER_DAYS = (7, 3, 1)


class Command(BaseCommand):
    help = 'Emit attendance-gap and subscription-expiry notifications.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--date',
            help='Day to check for missing registers (YYYY-MM-DD). Defaults to today.',
        )
        parser.add_argument(
            '--school',
            help='Limit the sweep to one school id.',
        )

    def handle(self, *args, **options):
        # Single-flight across pods/workers: the loser exits quietly instead
        # of double-emitting. Released in `finally` so a crash never wedges
        # future runs (and Postgres drops session locks on disconnect anyway).
        if not try_acquire_sweep_lock('notifications'):
            self.stdout.write('Another sweep_notifications is running; exiting.')
            return
        try:
            self._run(*args, **options)
        finally:
            release_sweep_lock('notifications')

    def _run(self, *args, **options):
        if options['date']:
            from django.utils.dateparse import parse_date
            on = parse_date(options['date'])
            if on is None:
                self.stderr.write('Could not read --date. Use YYYY-MM-DD.')
                return
        else:
            on = timezone.localdate()

        schools = School.objects.filter(is_active=True)
        if options['school']:
            schools = schools.filter(pk=options['school'])
        if not schools.exists():
            self.stderr.write('No active schools matched.')
            return

        gaps = 0
        for school in schools:
            gaps += len(event_service.sweep_attendance_gaps(school, on))

        reminders = self._remind_expiring(schools)

        self.stdout.write(
            self.style.SUCCESS(
                f'Swept {schools.count()} schools for {on}: '
                f'{gaps} attendance gap(s), {reminders} subscription reminder(s).'
            )
        )

    def _remind_expiring(self, schools) -> int:
        """Warn schools whose subscription is about to run out.

        PENDING subscriptions are included: a new school's pay-by deadline is
        stored on the same field, so the same reminders chase an unpaid trial
        and the same lapse flips it EXPIRED when the window closes with no
        verified payment.
        """
        now = timezone.now()
        sent = 0
        upcoming = schools.filter(
            subscription__status__in=[
                SchoolSubscription.Status.ACTIVE, SchoolSubscription.Status.PENDING,
            ],
            subscription__expires_at__isnull=False,
            subscription__expires_at__gt=now,
        ).select_related('subscription__plan')

        for school in upcoming:
            days_left = (school.subscription.expires_at - now).days
            if days_left not in REMINDER_DAYS:
                continue
            plan = getattr(school.subscription.plan, 'name', '') or ''
            event_service.subscription_ending(school, days_left=days_left, plan_name=plan)
            sent += 1

        # Already lapsed: the strongest alert the subscription type carries, and
        # one the school cannot miss behind a busy inbox. PENDING past its
        # pay-by deadline lapses the same way, so an unpaid trial cannot run
        # free forever.
        lapsed = schools.filter(
            subscription__status__in=[
                SchoolSubscription.Status.ACTIVE, SchoolSubscription.Status.PENDING,
            ],
            subscription__expires_at__lte=now,
        )
        for school in lapsed.select_related('subscription__plan'):
            plan = getattr(school.subscription.plan, 'name', '') or ''
            # Notify first (dedupe_key makes re-emission a no-op), then flip
            # with a WHERE guard so overlapping runs cannot double-write the
            # status. Alert is never lost to a crash between the two steps.
            event_service.subscription_ending(
                school, days_left=0, plan_name=plan,
            )
            SchoolSubscription.objects.filter(
                pk=school.subscription.pk,
                status__in=[
                    SchoolSubscription.Status.ACTIVE,
                    SchoolSubscription.Status.PENDING,
                ],
            ).update(status=SchoolSubscription.Status.EXPIRED)
            sent += 1

        return sent
