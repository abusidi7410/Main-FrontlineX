"""Event -> notification wiring (spec 32).

Each function here answers one question: *a thing just happened; who needs to
know, and what do they need to be told?* They are deliberately kept out of the
views and the domain services so that:

* the rules can be read, and tested, in one place instead of being scattered
  across payment, result and attendance code paths;
* a caller cannot half-notify: the recipient set, the wording and the dedupe
  key are decided together, and re-running the event is harmless.

Who gets told follows one rule throughout: **the person who has to act, and the
person whose own record it concerns.** Money goes to the bursar and the admin
who sign it off, plus the family it is about. A result goes to the approver,
and to the student and parents only once it is actually published - never when
it is a draft a teacher is still editing. Telling a parent about an unpublished
score would be the worst bug this module could have.
"""

from accounts.services import notifications as notify_svc
from records.services import attendance as attendance_service
from records.services import usage as usage_service

# Roles that sign money off. A principal sees the school's finances read-only,
# so they are included for visibility but not for action.
FINANCE_ROLES = ('school_admin', 'accountant', 'principal')
RESULT_APPROVER_ROLES = ('school_admin', 'principal')


def payment_verified(payment) -> None:
    """A payment was verified against an invoice."""
    invoice = payment.invoice
    student = invoice.student
    school = invoice.school
    name = f'{student.last_name}, {student.first_name}'
    amount = f'{payment.amount:,.2f}'

    notify_svc.notify_roles(
        school, FINANCE_ROLES,
        type='payment',
        title=f'Payment verified — {name}',
        body=f'{amount} received and applied to {student.class_name}.',
        link='/finance',
        dedupe_key=f'payment:{payment.pk}:verified',
    )
    # The family is told about their own money. The message reports a balance
    # the server computed rather than one supplied by the request.
    outstanding = max(invoice.total - invoice.paid, 0)
    notify_svc.notify_parents(
        [student],
        type='payment',
        title=f'Payment received for {name}',
        body=f'{amount} was received. Outstanding balance: {outstanding:,.2f}.',
        link='/fees',
        dedupe_key=f'payment:{payment.pk}:parent',
        school=school,
    )

    # Send SMS notification to parent/guardian phone. Payment success is
    # never coupled to SMS success: every failure mode (allowance exhausted,
    # provider down, bad number) is caught here so the verified payment stands.
    #
    # Idempotency: a succeeded ledger row for (payment, payment_notification)
    # means the SMS already went out, so a re-verification retries nothing.
    from records.models import UsageRecord
    already_sent = UsageRecord.objects.filter(
        payment=payment,
        resource_type=UsageRecord.ResourceType.SMS,
        action_type=UsageRecord.ActionType.PAYMENT_NOTIFICATION,
        status=UsageRecord.Status.SUCCEEDED,
    ).exists()
    if already_sent:
        return
    try:
        from accounts.models import User
        parents = User.objects.filter(
            linked_students=student,
            school_id=school.id,
            role='parent',
            is_active=True,
        )
        for parent in parents:
            if parent.phone:
                try:
                    usage_service.usage_service.send_sms(
                        school=school,
                        to=parent.phone,
                        message=f'Payment of {amount} received for {name}. Outstanding balance: {outstanding:,.2f}.',
                        action_type='payment_notification',
                        student=student,
                        user=parent,
                        invoice=invoice,
                        payment=payment,
                    )
                except Exception as e:
                    import logging
                    logging.getLogger(__name__).warning(
                        f'SMS notification failed for payment {payment.pk}: {e}'
                    )
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(
            f'SMS notification failed for payment {payment.pk}: {e}'
        )


def payment_reversed(payment) -> None:
    """A verified payment was reversed, so the balance went back up."""
    invoice = payment.invoice
    student = invoice.student
    name = f'{student.last_name}, {student.first_name}'
    notify_svc.notify_roles(
        invoice.school, FINANCE_ROLES,
        type='payment',
        title=f'Payment reversed — {name}',
        body=f'{payment.amount:,.2f} was reversed. The outstanding balance has increased.',
        link='/finance',
        dedupe_key=f'payment:{payment.pk}:reversed',
    )
    # A reversal changes what the family owes, so it is not something to find
    # out at the fee desk.
    notify_svc.notify_parents(
        [student],
        type='payment',
        title=f'Payment reversed for {name}',
        body=f'A payment of {payment.amount:,.2f} was reversed. Please check your balance.',
        link='/fees',
        dedupe_key=f'payment:{payment.pk}:reversed-parent',
        school=invoice.school,
    )


def result_sheet_advanced(sheet, action: str) -> None:
    """A result sheet moved through its lifecycle.

    Only `submit` and `publish` notify. `review`, `approve` and `lock` are the
    approval chain talking to itself, and notifying on each step trains staff to
    dismiss the bell without reading it.
    """
    school = sheet.school
    label = f'{sheet.class_obj.name} · {sheet.subject} · {sheet.assessment}'

    if action == 'submit':
        notify_svc.notify_roles(
            school, RESULT_APPROVER_ROLES,
            type='result',
            title=f'Results awaiting approval — {label}',
            body=f'{sheet.academic_session.name} was submitted for review.',
            link='/results',
            dedupe_key=f'result:{sheet.pk}:submitted',
        )
        return

    if action != 'publish':
        return

    notify_svc.notify_students(
        _students_of(sheet),
        type='result',
        title=f'Results published — {label}',
        body=f'Your {sheet.assessment} result for {sheet.subject} is now available.',
        link='/results',
        dedupe_key=f'result:{sheet.pk}:published',
        school=school,
    )
    notify_svc.notify_parents(
        _students_of(sheet),
        type='result',
        title=f'Results published — {label}',
        body=f'The {sheet.assessment} result is now available.',
        link='/children',
        dedupe_key=f'result:{sheet.pk}:published-parent',
        school=school,
    )


def attendance_gaps(school, on, class_names: list[str]) -> None:
    """Registers were not taken on a school day.

    Called by the daily sweep rather than inline: whether a register is missing
    is only knowable after the day is over, and a school should not have to ask
    for this alert.
    """
    if not class_names:
        return
    listed = ', '.join(class_names)
    notify_svc.notify_roles(
        school, RESULT_APPROVER_ROLES,
        type='attendance',
        title=f'Registers not taken ({on:%d %b %Y})',
        body=f'No attendance was recorded for: {listed}.',
        link='/attendance-overview',
        # Keyed by day so the sweep can run repeatedly in a day without
        # re-alerting about the same gap.
        dedupe_key=f'attendance-gap:{on:%Y-%m-%d}',
    )


def password_changed(user) -> None:
    """The account holder changed their own password."""
    notify_svc.notify(
        [user.pk],
        type='security',
        title='Your password was changed',
        body='If this was not you, contact your school administrator immediately.',
        link='/settings',
        dedupe_key='',
        school=user.school,
    )


def new_login(user, ip: str = '', previous_ip: str = '') -> None:
    """A successful sign-in from a place this account has not used before.

    Best-effort context only: the message goes to the person who just signed
    in, and carries no detail another reader could act on.

    `previous_ip` is part of the dedupe key rather than the body. A network that
    hands out a fresh address each time (mobile data, some proxies) would
    otherwise produce one notification per sign-in, and the value of the warning
    comes entirely from being rare.
    """
    where = f' from {ip}' if ip else ''
    notify_svc.notify(
        [user.pk],
        type='security',
        title='New sign-in to your account',
        body=f'Signed in{where}. If this was not you, change your password now.',
        link='/settings',
        school=user.school,
        dedupe_key=f'login:{previous_ip or "unknown"}>{ip or "unknown"}',
    )


def ai_usage_milestone(school, *, used: int, limit: int) -> None:
    """A school has used most of its AI allowance.

    Only fires on the threshold crossing, not on every subsequent query, so a
    busy school is not buried under it.
    """
    percent = round((used / limit) * 100) if limit else 100
    notify_svc.notify_roles(
        school, ('school_admin',),
        type='ai',
        title='AI usage is running high',
        body=f'{used} of {limit} AI queries used this period ({percent}%).',
        link='/ai',
        dedupe_key=f'ai-usage:{limit}:{int(used / limit * 10)}',
    )


def subscription_ending(school, *, days_left: int, plan_name: str = '') -> None:
    """A subscription is close to lapsing.

    `days_left=0` means it has already lapsed rather than "ends today": the plan
    has stopped working, so the wording and the link both change.
    """
    plan = f' on {plan_name}' if plan_name else ''
    lapsed = days_left <= 0
    notify_svc.notify_roles(
        school, ('school_admin',),
        type='subscription',
        title='Subscription expired' if lapsed
        else f'Subscription ends in {days_left} day{"s" if days_left != 1 else ""}',
        body=(
            f'Your plan{plan} has lapsed. Renew to restore students, staff and fees.'
            if lapsed
            else f'Renew{plan} to keep students, staff and fees available.'
        ),
        link='/subscription',
        dedupe_key='subscription:expired' if lapsed else f'subscription:{days_left}',
    )


def student_activated(student) -> None:
    """A student has cleared the financial gate and can start classes.

    This is the moment `Student.status` goes from PENDING_PAYMENT to ACTIVE,
    which is what puts somebody on a class roster. The family wants to know, and
    so does the office that was holding the record.
    """
    school = student.school
    name = f'{student.last_name}, {student.first_name}'
    notify_svc.notify_roles(
        school, ('school_admin', 'secretary'),
        type='system',
        title=f'Registration complete - {name}',
        body=f'{name} is now an active student in {student.class_name}.',
        link=f'/students/{student.pk}',
        dedupe_key=f'student:{student.pk}:activated',
    )
    notify_svc.notify_parents(
        [student],
        type='system',
        title=f'{name} is now enrolled',
        body=f'Registration for {student.class_name} is complete and classes can begin.',
        link='/children',
        dedupe_key=f'student:{student.pk}:activated-parent',
        school=school,
    )


def promotion_decided(school, student, decision: str, source_session: str,
                      target_session: str, target_class: str) -> None:
    """A promotion decision was applied to one student.

    The family is told the outcome in plain terms: promoted, promoted with
    conditions, repeating, or graduated. 'review' deliberately notifies
    nobody — an unfinished decision is the office's business, not the
    family's, and telling a parent "your child is under review" before the
    school has decided would be needlessly alarming.
    """
    if decision == 'review':
        return
    name = f'{student.last_name}, {student.first_name}'
    outcome = {
        'promote': f'Promoted to {target_class} for {target_session}.',
        'conditional': (
            f'Promoted to {target_class} for {target_session} with conditions. '
            'Check the report card for details.'
        ),
        'repeat': f'Will repeat {target_class} in {target_session}.',
        'graduate': f'Graduated after {source_session}.',
    }.get(decision)
    if outcome is None:
        return
    notify_svc.notify_parents(
        [student],
        type='result',
        title=f'Promotion decision — {name}',
        body=outcome,
        link='/children',
        dedupe_key=f'promotion:{student.pk}:{target_session}:{decision}',
        school=school,
    )
    notify_svc.notify_students(
        [student.pk],
        type='result',
        title='Your promotion decision is available',
        body=outcome,
        link='/results',
        dedupe_key=f'promotion:{student.pk}:{target_session}:{decision}-student',
        school=school,
    )


def _students_of(sheet):
    """The students on a result sheet, read through its class and session.

    Taken from the sheet's own scope rather than re-derived from a class name,
    so the people notified are exactly the people the result is about.
    """
    from records.models import Enrollment
    return list(
        Enrollment.objects.filter(
            school_id=sheet.school_id,
            class_obj_id=sheet.class_obj_id,
            academic_session_id=sheet.academic_session_id,
            status=Enrollment.Status.ACTIVE,
        ).select_related('student').values_list('student', flat=True)
    )


def sweep_attendance_gaps(school, on) -> list[str]:
    """Alert on registers missing for a school day. Returns the classes missed.

    Safe to call repeatedly: the dedupe key is the date, so the second run of
    the day adds nothing.

    Returns nothing on a day the school is not open. A cron job runs every
    calendar day, and a Saturday gap alert would be noise that teaches an admin
    to ignore this notification entirely.
    """
    if not attendance_service.is_school_day(school, on):
        return []
    rows = attendance_service.overview_for(school, on)
    missing = [row['className'] for row in rows if row['submitted'] == 0]
    attendance_gaps(school, on, missing)
    return missing
