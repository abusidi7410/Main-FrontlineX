"""Late/missed teacher class check-in sweep (spec: teacher class attendance).

Runs every few minutes during the school day from cron. For each active
school it materialises today's timetabled lessons that passed their grace
deadline without a verified check-in, marks them MISSED and alerts the
administrator exactly once.

Idempotent by construction: the unique (staff, date, slot) constraint means
re-running finds the rows it already created, `late_alert_sent` blocks repeat
alerts, and notifications carry a per-session dedupe key. A lesson already
checked in or cancelled is never touched — nothing is marked missed before
its deadline, and nothing a teacher later checks into stays missed.
"""

from django.core.management.base import BaseCommand
from django.utils import timezone

from records.services import teacher_checkin as teacher_checkin_service
from records.services.sweep_lock import release_sweep_lock, try_acquire_sweep_lock
from schools.models import School


class Command(BaseCommand):
    help = 'Mark missed teacher class check-ins and alert administrators once.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--date',
            help='Day to sweep (YYYY-MM-DD). Defaults to today.',
        )
        parser.add_argument(
            '--school',
            help='Limit the sweep to one school id.',
        )

    def handle(self, *args, **options):
        # Single-flight across workers: the loser exits quietly instead of
        # double-marking and double-alerting. Released in `finally` so a crash
        # never wedges future runs.
        if not try_acquire_sweep_lock('teacher_checkins'):
            self.stdout.write('Another sweep_teacher_checkins is running; exiting.')
            return
        try:
            self._run(*args, **options)
        finally:
            release_sweep_lock('teacher_checkins')

    def _run(self, *args, **options):
        if options['date']:
            from django.utils.dateparse import parse_date

            day = parse_date(options['date'])
            if day is None:
                self.stderr.write('Could not read --date. Use YYYY-MM-DD.')
                return
        else:
            day = timezone.localdate()

        schools = School.objects.filter(is_active=True)
        if options['school']:
            schools = schools.filter(pk=options['school'])
        if not schools.exists():
            self.stderr.write('No active schools matched.')
            return

        missed = 0
        for school in schools:
            rows = teacher_checkin_service.sweep_school_day(school, day)
            missed += len(rows)

        self.stdout.write(
            self.style.SUCCESS(
                f'Swept {schools.count()} schools for {day}: '
                f'{missed} missed session(s).'
            )
        )
