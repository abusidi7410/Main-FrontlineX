"""Balance reminder sweep (spec: automatic reminders from the academic calendar).

For every active school whose current session's term ends in `--days` days,
send one outstanding-balance SMS per student who:

* is ACTIVE,
* has a non-cancelled invoice for the current session with outstanding > 0,
* has a guardian phone on file.

Idempotency comes from `ReminderLog`: the (school, student, type, term, rule)
unique row is claimed with `get_or_create` before sending, so a re-run on the
same day adds nothing and a missed run is not a lost reminder the following day.
SMS allowance is checked through `UsageService`, so an exhausted school gets
nothing sent (and nothing recorded as sent) while payments and balances
themselves are unaffected.

Run once a day from cron alongside `sweep_notifications`.
"""

from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from records.models import AcademicSession, Invoice, ReminderLog, Student
from records.services.usage import AllowanceExhausted, usage_service


class Command(BaseCommand):
    help = 'Send outstanding balance reminders N days before term end.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--days',
            type=int,
            default=7,
            help='Days before term end at which to send (default: 7).',
        )
        parser.add_argument(
            '--school',
            help='Limit the sweep to one school id.',
        )

    def handle(self, *args, **options):
        days = options['days']
        rule = f'{days}_days_before_term_end'
        target = timezone.localdate() + timedelta(days=days)

        sessions = AcademicSession.objects.filter(
            is_active=True, term_end_date=target,
        ).select_related('school')
        if options['school']:
            sessions = sessions.filter(school_id=options['school'])

        if not sessions.exists():
            self.stderr.write(f'No sessions ending in {days} days.')
            return

        sent = skipped = failed = 0
        for session in sessions:
            school = session.school
            if not school.is_active:
                continue

            invoices = Invoice.objects.filter(
                school=school,
                academic_session=session,
                is_cancelled=False,
            ).select_related('student')

            for invoice in invoices:
                if invoice.outstanding <= 0:
                    continue
                student = invoice.student
                if student.status != Student.Status.ACTIVE:
                    continue
                if not student.guardian_phone:
                    continue

                # Claim the idempotency slot before spending an SMS unit.
                _, created = ReminderLog.objects.get_or_create(
                    school=school,
                    student=student,
                    reminder_type='balance_reminder',
                    term=invoice.term,
                    reminder_rule=rule,
                    defaults={'status': 'pending'},
                )
                if not created:
                    skipped += 1
                    continue

                name = f'{student.first_name} {student.last_name}'.strip()
                message = (
                    f'Dear parent of {name}: outstanding balance of '
                    f'₦{invoice.outstanding:,.2f} for {invoice.term}. '
                    f'Please settle before the term closes.'
                )
                try:
                    usage_service.send_sms(
                        school=school,
                        to=student.guardian_phone,
                        message=message,
                        action_type='balance_reminder',
                        student=student,
                        invoice=invoice,
                    )
                except AllowanceExhausted:
                    # Exhaustion blocks the SMS only. The reminder slot is
                    # already claimed so we do not retry-storm the provider;
                    # the school must top up its allowance.
                    ReminderLog.objects.filter(
                        school=school, student=student,
                        reminder_type='balance_reminder',
                        term=invoice.term, reminder_rule=rule,
                    ).update(status='blocked_exhausted')
                    skipped += 1
                    continue
                except Exception as exc:  # provider failure: record and move on
                    ReminderLog.objects.filter(
                        school=school, student=student,
                        reminder_type='balance_reminder',
                        term=invoice.term, reminder_rule=rule,
                    ).update(status='failed')
                    self.stderr.write(f'SMS failed for student {student.pk}: {exc}')
                    failed += 1
                    continue

                ReminderLog.objects.filter(
                    school=school, student=student,
                    reminder_type='balance_reminder',
                    term=invoice.term, reminder_rule=rule,
                ).update(status='sent')
                sent += 1

        self.stdout.write(
            f'Balance reminders: {sent} sent, {skipped} skipped, {failed} failed.'
        )
