"""Daily notification sweep (spec 32).

Attendance-gap detection runs here ("has anything happened since we last
looked?"). The old subscription-expiry branch is retired with the fixed
subscription model — see `_remind_expiring`, kept as a documented no-op so
cron history and call sites keep working.
"""

from django.core.management.base import BaseCommand
from django.utils import timezone

from records.services import events as event_service
from records.services.sweep_lock import release_sweep_lock, try_acquire_sweep_lock
from schools.models import School

#: Days before expiry at which the school is warned. Only the closest one fires
#: per subscription, chosen by the dedupe key inside the emitter.
REMINDER_DAYS = (7, 3, 1)


class Command(BaseCommand):
    help = 'Emit attendance-gap notifications.'

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

        self._remind_expiring(schools)

        self.stdout.write(
            self.style.SUCCESS(
                f'Swept {schools.count()} schools for {on}: '
                f'{gaps} attendance gap(s).'
            )
        )

    def _remind_expiring(self, schools) -> int:
        """Retired no-op: fixed subscriptions no longer exist.

        Kept so existing cron invocations and tests calling the sweep keep
        passing without subscription side effects. Returns 0 reminders.
        """
        return 0
