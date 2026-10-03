"""Notifications and announcements (spec 32).

Two things are worth more than the happy path here, and both are tested first:

1. **A notification inbox is private.** Every read and write is scoped to the
   caller, so no id in a request can reach somebody else's mail. A parent
   reading their own feed is not exercising a management right, which is why
   these endpoints take no role permission.
2. **An audience is a delivery boundary.** A parent must not be able to read a
   staff-only notice, and the assistant must not be a way around that.
"""
from datetime import timedelta

from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import Notification, NotificationPreference, User
from accounts.services import notifications as notify_svc
from records.models import Enrollment, Payment, ResultSheet, Student
from records.services import announcements as announcement_service
from records.services import attendance as attendance_service
from records.services import events as event_service
from records.tests.base import SchoolTestCase
from schools.models import Announcement


class NotificationTestCase(SchoolTestCase):
    def setUp(self):
        super().setUp()
        Notification.objects.all().delete()

    def make_notification(self, user, **kwargs):
        defaults = {
            'type': Notification.Type.SYSTEM,
            'title': 'Notice',
            'body': 'Body',
            'school': user.school,
        }
        # kwargs last, so a caller can override the default school (a platform
        # manager has none).
        defaults.update(kwargs)
        return Notification.objects.create(user=user, **defaults)


class NotificationFeedTests(NotificationTestCase):
    def test_feed_returns_only_the_callers_own_notifications(self):
        self.make_notification(self.admin, title='For the admin')
        self.make_notification(self.principal, title='For the principal')

        self.auth(self.admin)
        response = self.client.get(self.url('/notifications/'))

        self.assertEqual(response.status_code, 200)
        titles = [row['title'] for row in response.data['results']]
        self.assertEqual(titles, ['For the admin'])

    def test_feed_is_newest_first_and_reports_the_unread_count(self):
        # created_at is stamped by auto_now_add, so each row is aged explicitly
        # rather than relying on creation order.
        oldest = self.make_notification(self.admin, title='Oldest')
        middle = self.make_notification(self.admin, title='Middle')
        newest = self.make_notification(self.admin, title='Newest')
        now = timezone.now()
        Notification.objects.filter(pk=oldest.pk).update(created_at=now - timedelta(hours=3))
        Notification.objects.filter(pk=middle.pk).update(created_at=now - timedelta(hours=2))
        Notification.objects.filter(pk=newest.pk).update(created_at=now - timedelta(hours=1))

        self.auth(self.admin)
        response = self.client.get(self.url('/notifications/'))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['unread'], 3)
        self.assertEqual(
            [row['title'] for row in response.data['results']],
            ['Newest', 'Middle', 'Oldest'],
        )

    def test_unread_filter_returns_only_unread(self):
        read = self.make_notification(self.admin, title='Already read')
        Notification.objects.filter(pk=read.pk).update(read_at=timezone.now())
        self.make_notification(self.admin, title='Still unread')

        self.auth(self.admin)
        response = self.client.get(self.url('/notifications/?unread=true'))

        self.assertEqual(response.status_code, 200)
        self.assertEqual([row['title'] for row in response.data['results']], ['Still unread'])
        self.assertEqual(response.data['unread'], 1)

    def test_type_filter_is_validated_rather_than_ignored(self):
        self.auth(self.admin)
        response = self.client.get(self.url('/notifications/?type=bogus'))
        self.assertEqual(response.status_code, 400)
        self.assertIn('type', response.data['fieldErrors'])

    def test_pagination_reports_whether_more_pages_exist(self):
        for i in range(5):
            self.make_notification(self.admin, title=f'Notice {i}')

        self.auth(self.admin)
        response = self.client.get(self.url('/notifications/?pageSize=2'))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['count'], 5)
        self.assertEqual(len(response.data['results']), 2)
        self.assertTrue(response.data['hasMore'])

    def test_anonymous_caller_is_refused(self):
        response = APIClient().get(self.url('/notifications/'))
        self.assertIn(response.status_code, (401, 403))

    def test_a_user_without_a_school_still_reads_their_own_inbox(self):
        # Notifications are a private inbox, not a tenant record, so a platform
        # manager is not excluded for having no school.
        manager = User.objects.create_user(
            email='pm@platform.example', password='Strong-Pass-1!',
            first_name='Pat', last_name='Mour', role=User.Role.PLATFORM_MANAGER,
        )
        self.make_notification(manager, school=None, title='Platform note')

        self.auth(manager)
        response = self.client.get(self.url('/notifications/'))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['count'], 1)


class NotificationMarkReadTests(NotificationTestCase):
    def test_marking_read_touches_only_the_callers_own_row(self):
        mine = self.make_notification(self.admin, title='Mine')
        theirs = self.make_notification(self.principal, title='Theirs')

        self.auth(self.admin)
        response = self.client.post(self.url(f'/notifications/{mine.pk}/read/'))

        self.assertEqual(response.status_code, 200)
        mine.refresh_from_db()
        theirs.refresh_from_db()
        self.assertIsNotNone(mine.read_at)
        self.assertIsNone(theirs.read_at)

    def test_another_users_notification_is_not_found_not_forbidden(self):
        # 404 rather than 403: a 403 would confirm the id exists.
        theirs = self.make_notification(self.principal, title='Theirs')

        self.auth(self.admin)
        response = self.client.post(self.url(f'/notifications/{theirs.pk}/read/'))

        self.assertEqual(response.status_code, 404)

    def test_marking_read_twice_keeps_the_first_moment(self):
        item = self.make_notification(self.admin)
        first = timezone.now() - timedelta(hours=2)

        self.auth(self.admin)
        self.client.post(self.url(f'/notifications/{item.pk}/read/'))
        Notification.objects.filter(pk=item.pk).update(read_at=first)
        self.client.post(self.url(f'/notifications/{item.pk}/read/'))

        item.refresh_from_db()
        self.assertEqual(item.read_at, first)

    def test_read_all_clears_only_the_callers_unread(self):
        self.make_notification(self.admin, title='Unread')
        self.make_notification(self.principal, title='Unread elsewhere')

        self.auth(self.admin)
        response = self.client.post(self.url('/notifications/read-all/'))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['markedRead'], 1)
        self.assertEqual(
            Notification.objects.filter(user=self.admin, read_at__isnull=True).count(), 0,
        )
        self.assertEqual(
            Notification.objects.filter(user=self.principal, read_at__isnull=True).count(), 1,
        )


class NotificationPreferenceTests(NotificationTestCase):
    def test_get_returns_every_type_defaulting_to_enabled(self):
        self.auth(self.admin)
        response = self.client.get(self.url('/notifications/preferences/'))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), len(Notification.Type.choices))
        self.assertTrue(all(row['inApp'] for row in response.data))

    def test_patch_stores_the_opt_out_and_survives_a_second_patch(self):
        self.auth(self.admin)
        response = self.client.patch(
            self.url('/notifications/preferences/'),
            {'preferences': [{'type': 'attendance', 'inApp': False}]},
            format='json',
        )

        self.assertEqual(response.status_code, 200)
        stored = {
            row['type']: row['inApp'] for row in response.data
        }
        self.assertFalse(stored['attendance'])
        self.assertTrue(stored['payment'])

        again = self.client.patch(
            self.url('/notifications/preferences/'),
            {'preferences': [{'type': 'attendance', 'inApp': True}]},
            format='json',
        )
        self.assertEqual(again.status_code, 200)
        self.assertEqual(
            NotificationPreference.objects.filter(
                user=self.admin, type='attendance',
            ).count(),
            1,
        )

    def test_unknown_type_is_rejected(self):
        self.auth(self.admin)
        response = self.client.patch(
            self.url('/notifications/preferences/'),
            {'preferences': [{'type': 'nope', 'inApp': False}]},
            format='json',
        )
        self.assertEqual(response.status_code, 400)

    def test_a_stringly_typed_toggle_is_refused_rather_than_guessed(self):
        # bool("false") is True, so a loose cast would switch the preference *on*
        # for somebody who asked to turn it off.
        self.auth(self.admin)
        response = self.client.patch(
            self.url('/notifications/preferences/'),
            {'preferences': [{'type': 'attendance', 'inApp': 'false'}]},
            format='json',
        )
        self.assertEqual(response.status_code, 400)
        self.assertFalse(
            NotificationPreference.objects.filter(
                user=self.admin, type='attendance', in_app=False,
            ).exists()
        )

    def test_a_muted_type_stops_reaching_the_person(self):
        NotificationPreference.objects.create(
            user=self.teacher, type='announcement', in_app=False,
        )
        announcement_service.create(
            school=self.school, author=self.admin, title='Notice', body='Body',
            audience=['All'],
        )
        self.assertFalse(
            Notification.objects.filter(user=self.teacher, type='announcement').exists()
        )
        self.assertTrue(
            Notification.objects.filter(user=self.admin, type='announcement').exists()
        )


class NotificationFanOutTests(NotificationTestCase):
    def test_roles_are_notified_within_their_school_only(self):
        notify_svc.notify_roles(
            self.school, ('school_admin',), type='system', title='Admin only',
        )
        self.assertTrue(Notification.objects.filter(user=self.admin).exists())
        self.assertFalse(Notification.objects.filter(user=self.other_admin).exists())

    def test_a_dedupe_key_keeps_a_replayed_event_from_duplicating(self):
        first = notify_svc.notify(
            [self.admin], type='payment', title='Paid', dedupe_key='payment:7',
        )
        second = notify_svc.notify(
            [self.admin], type='payment', title='Paid', dedupe_key='payment:7',
        )
        self.assertEqual(first, 1)
        self.assertEqual(second, 0)
        self.assertEqual(Notification.objects.filter(user=self.admin).count(), 1)

    def test_a_dedupe_key_is_per_person_not_global(self):
        notify_svc.notify(
            [self.admin, self.principal], type='payment', title='Paid',
            dedupe_key='payment:7',
        )
        self.assertEqual(Notification.objects.filter(dedupe_key='payment:7').count(), 2)

    def test_notifications_without_a_dedupe_key_are_never_deduplicated(self):
        notify_svc.notify([self.admin], type='system', title='One')
        notify_svc.notify([self.admin], type='system', title='Two')
        self.assertEqual(Notification.objects.filter(user=self.admin).count(), 2)

    def test_an_inactive_account_is_not_notified(self):
        self.principal.is_active = False
        self.principal.save(update_fields=['is_active'])
        notify_svc.notify_roles(
            self.school, ('principal',), type='system', title='Notice',
        )
        self.assertFalse(Notification.objects.filter(user=self.principal).exists())

    def test_a_long_title_is_truncated_rather_than_rejected(self):
        notify_svc.notify([self.admin], type='system', title='x' * 400)
        self.assertEqual(len(Notification.objects.get().title), 200)


class AnnouncementVisibilityTests(NotificationTestCase):
    def publish(self, title, audience):
        return announcement_service.create(
            school=self.school, author=self.admin, title=title, body='Body',
            audience=audience,
        )

    def test_staff_with_communication_read_see_the_whole_board(self):
        self.publish('Staff only', ['Staff'])
        self.publish('Parents only', ['Parents'])

        self.auth(self.teacher)
        response = self.client.get(self.url('/announcements/'))

        titles = sorted(row['title'] for row in response.data)
        self.assertEqual(titles, ['Parents only', 'Staff only'])

    def test_a_parent_sees_parent_and_all_but_not_staff_notices(self):
        self.publish('Staff only', ['Staff'])
        self.publish('Parents only', ['Parents'])
        self.publish('Everyone', ['All'])

        self.auth(self.parent)
        response = self.client.get(self.url('/announcements/'))

        titles = sorted(row['title'] for row in response.data)
        self.assertEqual(titles, ['Everyone', 'Parents only'])

    def test_a_student_does_not_see_a_parents_notice(self):
        self.publish('Parents only', ['Parents'])
        self.auth(self.student_user)
        response = self.client.get(self.url('/announcements/'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, [])

    def test_announcements_do_not_cross_schools(self):
        self.publish('Success notice', ['All'])
        announcement_service.create(
            school=self.other_school, author=self.other_admin, title='Rival notice',
            body='Body', audience=['All'],
        )

        self.auth(self.admin)
        response = self.client.get(self.url('/announcements/'))
        titles = [row['title'] for row in response.data]
        self.assertEqual(titles, ['Success notice'])

    def test_an_expired_announcement_is_hidden_but_kept(self):
        item = announcement_service.create(
            school=self.school, author=self.admin, title='Rescheduled exam',
            body='Body', audience=['All'], expires_at=timezone.now() - timedelta(hours=1),
        )
        self.auth(self.admin)
        response = self.client.get(self.url('/announcements/'))
        self.assertEqual(response.data, [])
        self.assertTrue(Announcement.objects.filter(pk=item.pk).exists())

    def test_a_lowercase_audience_from_the_platform_broadcast_still_matches(self):
        # The platform endpoint has always written audience=['all'].
        Announcement.objects.create(
            school=self.school, author=self.admin, title='Platform style', body='Body',
            audience=['all'], scope=Announcement.Scope.SCHOOL,
        )
        self.auth(self.parent)
        response = self.client.get(self.url('/announcements/'))
        self.assertEqual([row['title'] for row in response.data], ['Platform style'])

    def test_an_unknown_audience_label_fails_closed(self):
        self.assertEqual(announcement_service.normalise_audience(['Everyone']), [])
        self.assertEqual(announcement_service.normalise_audience(None), [])

    def test_pinned_announcements_sort_first(self):
        self.publish('Ordinary', ['All'])
        self.publish('Urgent', ['All'])
        urgent = Announcement.objects.get(title='Urgent')
        Announcement.objects.filter(pk=urgent.pk).update(is_pinned=True)

        self.auth(self.admin)
        response = self.client.get(self.url('/announcements/'))
        self.assertEqual(response.data[0]['title'], 'Urgent')


class AnnouncementWriteTests(NotificationTestCase):
    def test_publishing_fans_out_to_the_named_audience(self):
        self.auth(self.principal)
        response = self.client.post(
            self.url('/announcements/'),
            {'title': 'Closed for elections', 'body': 'School is closed Friday.',
             'audience': ['Parents']},
            format='json',
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data['title'], 'Closed for elections')
        self.assertEqual(response.data['audience'], ['Parents'])
        self.assertTrue(Notification.objects.filter(user=self.parent).exists())
        self.assertFalse(Notification.objects.filter(user=self.teacher).exists())

    def test_field_level_errors_use_the_projects_wrapper(self):
        self.auth(self.admin)
        response = self.client.post(
            self.url('/announcements/'), {'title': 'Only a title'}, format='json',
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn('body', response.data['fieldErrors'])

    def test_publishing_to_all_reaches_every_role(self):
        self.auth(self.admin)
        self.client.post(
            self.url('/announcements/'),
            {'title': 'Everyone', 'body': 'Body', 'audience': ['All']},
            format='json',
        )
        reached = Notification.objects.filter(type='announcement').count()
        self.assertEqual(reached, 7)

    def test_republishing_does_not_duplicate_notifications(self):
        self.auth(self.admin)
        payload = {'title': 'Once', 'body': 'Body', 'audience': ['Parents']}
        self.client.post(self.url('/announcements/'), payload, format='json')
        # Editing an announcement re-fans it; the dedupe key is the row id.
        item = Announcement.objects.get(title='Once')
        announcement_service.publish(item)
        self.assertEqual(Notification.objects.filter(type='announcement').count(), 1)

    def test_a_teacher_may_not_publish(self):
        self.auth(self.teacher)
        response = self.client.post(
            self.url('/announcements/'),
            {'title': 'Nope', 'body': 'Body', 'audience': ['All']},
            format='json',
        )
        self.assertEqual(response.status_code, 403)

    def test_a_parent_may_not_publish(self):
        self.auth(self.parent)
        response = self.client.post(
            self.url('/announcements/'),
            {'title': 'Nope', 'body': 'Body', 'audience': ['All']},
            format='json',
        )
        self.assertEqual(response.status_code, 403)

    def test_title_and_body_are_required(self):
        self.auth(self.admin)
        self.assertEqual(
            self.client.post(
                self.url('/announcements/'), {'body': 'Body'}, format='json',
            ).status_code,
            400,
        )
        self.assertEqual(
            self.client.post(
                self.url('/announcements/'), {'title': 'Title'}, format='json',
            ).status_code,
            400,
        )

    def test_an_unrecognised_audience_is_rejected_not_widened(self):
        self.auth(self.admin)
        response = self.client.post(
            self.url('/announcements/'),
            {'title': 'Title', 'body': 'Body', 'audience': ['The Entire World']},
            format='json',
        )
        self.assertEqual(response.status_code, 400)
        self.assertFalse(Announcement.objects.filter(title='Title').exists())

    def test_an_expiry_in_the_past_is_rejected(self):
        self.auth(self.admin)
        response = self.client.post(
            self.url('/announcements/'),
            {
                'title': 'Title', 'body': 'Body', 'audience': ['All'],
                'expiresAt': '2020-01-01T00:00:00Z',
            },
            format='json',
        )
        self.assertEqual(response.status_code, 400)

    def test_a_secretary_may_publish(self):
        self.auth(self.secretary)
        response = self.client.post(
            self.url('/announcements/'),
            {'title': 'Notices', 'body': 'Body', 'audience': ['Staff']},
            format='json',
        )
        self.assertEqual(response.status_code, 201)


class AnnouncementDetailTests(NotificationTestCase):
    def setUp(self):
        super().setUp()
        self.item = announcement_service.create(
            school=self.school, author=self.admin, title='Original', body='Body',
            audience=['All'],
        )

    def test_an_author_can_pin_and_unpin(self):
        self.auth(self.admin)
        response = self.client.patch(
            self.url(f'/announcements/{self.item.pk}/'), {'isPinned': True}, format='json',
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data['isPinned'])

        response = self.client.patch(
            self.url(f'/announcements/{self.item.pk}/'), {'isPinned': False}, format='json',
        )
        self.assertFalse(response.data['isPinned'])

    def test_an_author_can_edit_and_withdraw(self):
        self.auth(self.admin)
        response = self.client.patch(
            self.url(f'/announcements/{self.item.pk}/'),
            {'title': 'Corrected', 'body': 'Corrected body'},
            format='json',
        )
        self.assertEqual(response.data['title'], 'Corrected')

        response = self.client.delete(self.url(f'/announcements/{self.item.pk}/'))
        self.assertEqual(response.status_code, 204)
        self.assertFalse(Announcement.objects.filter(pk=self.item.pk).exists())

    def test_the_patch_writes_the_fields_it_claims_to(self):
        # update_fields is a whitelist: naming a field that is not in it means the
        # change is silently dropped, so the stored row has to be checked rather
        # than only the response body.
        self.auth(self.admin)
        self.client.patch(
            self.url(f'/announcements/{self.item.pk}/'),
            {'isPinned': True, 'title': 'Renamed'},
            format='json',
        )
        self.item.refresh_from_db()
        self.assertTrue(self.item.is_pinned)
        self.assertEqual(self.item.title, 'Renamed')

    def test_an_expiry_in_the_past_is_refused_on_edit_too(self):
        # Otherwise an edit could quietly publish a notice that is already gone,
        # which reads as the school losing it.
        self.auth(self.admin)
        past = (timezone.now() - timedelta(days=1)).isoformat()
        response = self.client.patch(
            self.url(f'/announcements/{self.item.pk}/'), {'expiresAt': past}, format='json',
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn('expiresAt', response.data['fieldErrors'])
        self.item.refresh_from_db()
        self.assertIsNone(self.item.expires_at)

    def test_a_stringly_typed_pin_is_refused_rather_than_guessed(self):
        # bool("false") is True, so a loose cast would pin the wrong way.
        self.auth(self.admin)
        response = self.client.patch(
            self.url(f'/announcements/{self.item.pk}/'), {'isPinned': 'false'}, format='json',
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn('isPinned', response.data['fieldErrors'])
        self.item.refresh_from_db()
        self.assertFalse(self.item.is_pinned)

    def test_an_expiry_can_be_cleared_explicitly(self):
        self.item.expires_at = timezone.now() + timedelta(days=3)
        self.item.save(update_fields=['expires_at'])
        self.auth(self.admin)
        response = self.client.patch(
            self.url(f'/announcements/{self.item.pk}/'), {'expiresAt': None}, format='json',
        )
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.data['expiresAt'])

    def test_an_empty_patch_is_refused(self):
        # Silently succeeding on a no-op would tell the author "saved" for
        # something that never changed.
        self.auth(self.admin)
        response = self.client.patch(
            self.url(f'/announcements/{self.item.pk}/'), {}, format='json',
        )
        self.assertEqual(response.status_code, 400)

    def test_a_teacher_cannot_edit(self):
        self.auth(self.teacher)
        response = self.client.patch(
            self.url(f'/announcements/{self.item.pk}/'), {'isPinned': True}, format='json',
        )
        self.assertEqual(response.status_code, 403)

    def test_another_schools_announcement_is_not_reachable(self):
        rival = announcement_service.create(
            school=self.other_school, author=self.other_admin, title='Rival', body='Body',
            audience=['All'],
        )
        self.auth(self.admin)
        self.assertEqual(
            self.client.get(self.url(f'/announcements/{rival.pk}/')).status_code, 404,
        )
        self.assertEqual(
            self.client.patch(
                self.url(f'/announcements/{rival.pk}/'), {'isPinned': True}, format='json',
            ).status_code,
            404,
        )

    def test_a_parent_cannot_read_a_staff_only_announcement_directly(self):
        staff_only = announcement_service.create(
            school=self.school, author=self.admin, title='Staff', body='Body',
            audience=['Staff'],
        )
        self.auth(self.parent)
        self.assertEqual(
            self.client.get(self.url(f'/announcements/{staff_only.pk}/')).status_code, 404,
        )


class EventNotificationTests(NotificationTestCase):
    def setUp(self):
        super().setUp()
        self.student = self.make_student(
            first_name='Ada', last_name='Nwosu',
            student_profile=None,
        ) if False else self.make_student(first_name='Ada', last_name='Nwosu')
        Enrollment.objects.create(
            school=self.school, student=self.student, academic_session=self.session,
            class_obj=self.jss1, status=Enrollment.Status.ACTIVE,
        )
        self.parent.linked_students.add(self.student)
        User.objects.filter(pk=self.student_user.pk).update(
            student_profile=self.student,
        )
        self.student_user.refresh_from_db()
        self.invoice = self.make_invoice(student=self.student, total='50000')

    def an_open_school_day(self):
        """The most recent day this school is actually open.

        `sweep_attendance_gaps` deliberately reports nothing at the weekend or on
        a declared closure, so a test that wants gaps reported has to name a day
        the school is open. Asking the calendar instead of hard-coding a weekday
        is what keeps these assertions honest: run on a Saturday and a bare
        `localdate()` makes the "2 notifications" expectation fail for a reason
        that has nothing to do with the code under test.
        """
        day = timezone.localdate()
        for _ in range(7):
            if attendance_service.is_school_day(self.school, day):
                return day
            day -= timedelta(days=1)
        self.fail('the school was closed for the whole of the last week')

    def test_a_verified_payment_reaches_the_bursar_and_the_family(self):
        payment = Payment.objects.create(
            school=self.school, invoice=self.invoice, amount=20000,
            method=Payment.Method.CASH, status=Payment.Status.PENDING,
            reference='PAY-1',
        )
        event_service.payment_verified(payment)

        self.assertTrue(
            Notification.objects.filter(user=self.admin, type='payment').exists()
        )
        self.assertTrue(
            Notification.objects.filter(user=self.accountant, type='payment').exists()
        )
        parent_note = Notification.objects.get(user=self.parent)
        self.assertIn('20,000', parent_note.body)

    def test_the_parent_message_reports_the_server_computed_balance(self):
        # The invoice is the source of truth for what is owed; the notification
        # reports what the server computed, never a figure from the request.
        self.invoice.paid = 20000
        self.invoice.save(update_fields=['paid'])
        payment = Payment.objects.create(
            school=self.school, invoice=self.invoice, amount=20000,
            method=Payment.Method.CASH, status=Payment.Status.VERIFIED, reference='PAY-2',
        )
        event_service.payment_verified(payment)
        self.assertIn('30,000', Notification.objects.get(user=self.parent).body)

    def test_a_reversed_payment_warns_the_family(self):
        payment = Payment.objects.create(
            school=self.school, invoice=self.invoice, amount=20000,
            method=Payment.Method.CASH, status=Payment.Status.VERIFIED, reference='PAY-3',
        )
        event_service.payment_reversed(payment)
        self.assertIn('reversed', Notification.objects.get(user=self.parent).title.lower())

    def test_payment_events_do_not_cross_schools(self):
        payment = Payment.objects.create(
            school=self.school, invoice=self.invoice, amount=20000,
            method=Payment.Method.CASH, status=Payment.Status.PENDING, reference='PAY-4',
        )
        event_service.payment_verified(payment)
        self.assertFalse(Notification.objects.filter(user=self.other_admin).exists())

    def _sheet(self):
        return ResultSheet.objects.create(
            school=self.school, academic_session=self.session, class_obj=self.jss1,
            subject='Mathematics', assessment='First Test',
            status=ResultSheet.Status.DRAFT,
        )

    def test_submitted_results_reach_the_approver_but_not_the_family(self):
        sheet = self._sheet()
        event_service.result_sheet_advanced(sheet, 'submit')

        self.assertTrue(
            Notification.objects.filter(user=self.admin, type='result').exists()
        )
        # A parent must never hear about a score that has not been published.
        self.assertFalse(
            Notification.objects.filter(user=self.parent, type='result').exists()
        )

    def test_published_results_reach_the_student_and_the_parent(self):
        sheet = self._sheet()
        event_service.result_sheet_advanced(sheet, 'publish')

        self.assertTrue(
            Notification.objects.filter(user=self.student_user, type='result').exists()
        )
        self.assertTrue(
            Notification.objects.filter(user=self.parent, type='result').exists()
        )

    def test_internal_approval_steps_do_not_notify(self):
        sheet = self._sheet()
        for action in ('review', 'approve', 'lock'):
            event_service.result_sheet_advanced(sheet, action)
        self.assertFalse(Notification.objects.filter(type='result').exists())

    def test_an_approved_student_tells_the_office_and_the_family(self):
        self.student.status = Student.Status.ACTIVE
        self.student.save(update_fields=['status'])
        event_service.student_activated(self.student)

        self.assertTrue(
            Notification.objects.filter(user=self.secretary, type='system').exists()
        )
        self.assertTrue(Notification.objects.filter(user=self.parent).exists())

    def test_settling_the_last_fee_releases_the_family_and_the_office(self):
        # The real path, not the helper: `activate_student_if_fully_paid` is what
        # puts a new student on a roster, so that is where the notice has to come
        # from or one of its three call sites can forget.
        from records.models import Invoice
        from records.services import billing as billing_service

        pending = self.make_student(
            admission_number='SUA/T/NEW1', first_name='Ada', last_name='Bello',
            class_name='JSS 1', status=Student.Status.PENDING_PAYMENT,
        )
        pending_parent = User.objects.create_user(
            email='parent2@success.example', password='Strong-Pass-1!',
            role=User.Role.PARENT, school=self.school, is_active=True,
        )
        pending_parent.linked_students.add(pending)

        invoice = self.make_invoice(
            student=pending, total='10000', paid='10000',
            source=Invoice.Source.ADMISSION, is_cancelled=False,
        )
        invoice.payments.create(
            school=self.school, amount=10000, method='cash', status='verified',
        )

        self.assertTrue(billing_service.activate_student_if_fully_paid(pending))
        self.assertEqual(
            Notification.objects.filter(user=pending_parent, type='system').count(), 1,
        )
        self.assertTrue(
            Notification.objects.filter(user=self.secretary, type='system').exists()
        )

        # Running it again must not re-notify: the student is no longer pending,
        # so there is nothing to announce.
        self.assertFalse(billing_service.activate_student_if_fully_paid(pending))
        self.assertEqual(
            Notification.objects.filter(user=pending_parent, type='system').count(), 1,
        )

    def test_the_daily_sweep_is_idempotent_within_a_day(self):
        day = self.an_open_school_day()
        first = event_service.sweep_attendance_gaps(self.school, day)
        second = event_service.sweep_attendance_gaps(self.school, day)
        self.assertEqual(first, second)
        # Dedupe is per person, so the second run adds nothing for either of
        # the two roles that are told about a missing register.
        self.assertEqual(
            Notification.objects.filter(type='attendance').count(), 2,
        )

    def test_the_daily_sweep_tells_only_the_people_who_act_on_it(self):
        event_service.sweep_attendance_gaps(self.school, self.an_open_school_day())
        reached = set(
            Notification.objects.filter(type='attendance').values_list('user__role', flat=True),
        )
        self.assertEqual(reached, {'school_admin', 'principal'})

    def test_the_sweep_stays_quiet_when_the_school_is_closed(self):
        # The sweep runs on a calendar cron. A Saturday alert about missing
        # registers would train an admin to ignore the one notification that
        # does matter.
        saturday = timezone.localdate()
        while saturday.weekday() != 5:
            saturday -= timedelta(days=1)
        self.assertEqual(event_service.sweep_attendance_gaps(self.school, saturday), [])
        self.assertFalse(Notification.objects.filter(type='attendance').exists())

    def test_a_declared_closure_also_stops_the_sweep(self):
        # A school that has marked the day closed must not be chased about it.
        # Anchored to an open day so the closure is the only reason for silence.
        day = self.an_open_school_day()
        self.school.non_school_days = [day.isoformat()]
        self.school.save(update_fields=['non_school_days'])
        self.assertEqual(event_service.sweep_attendance_gaps(self.school, day), [])
        self.assertFalse(Notification.objects.filter(type='attendance').exists())

    def test_a_lapsed_subscription_says_expired_rather_than_ends_in_zero_days(self):
        event_service.subscription_ending(self.school, days_left=0)
        note = Notification.objects.get(user=self.admin, type='subscription')
        self.assertIn('expired', note.title.lower())
        # A distinct dedupe key, so a lapse is not mistaken for "ends today".
        event_service.subscription_ending(self.school, days_left=0)
        self.assertEqual(
            Notification.objects.filter(user=self.admin, type='subscription').count(), 1,
        )

    def test_a_password_change_notifies_only_that_account(self):
        event_service.password_changed(self.teacher)
        self.assertTrue(
            Notification.objects.filter(user=self.teacher, type='security').exists()
        )
        self.assertFalse(Notification.objects.filter(user=self.admin).exists())

    def test_a_sign_in_from_a_new_address_is_reported_once(self):
        # The warning is only useful while it stays rare, so a network that
        # changes address every time must not produce one notification per login.
        self.teacher.last_login_ip = '10.0.0.1'
        self.teacher.save(update_fields=['last_login_ip'])

        event_service.new_login(self.teacher, ip='203.0.113.9', previous_ip='10.0.0.1')
        event_service.new_login(self.teacher, ip='203.0.113.9', previous_ip='10.0.0.1')

        note = Notification.objects.get(user=self.teacher, type='security')
        self.assertIn('203.0.113.9', note.body)
        self.assertEqual(
            Notification.objects.filter(user=self.teacher, type='security').count(), 1,
        )

    def _sign_in_as_teacher(self, **extra):
        """Log the teacher in through the real endpoint.

        The fixture hashes inside `setUp` under the fast MD5 override, which has
        already been undone by the time a test body runs, so the stored hash can
        never verify. Re-setting the password here hashes it with the hasher that
        is actually active during the request.
        """
        self.teacher.set_password('Strong-Pass-1!')
        self.teacher.save(update_fields=['password'])
        return self.client.post(
            self.url('/auth/login/'),
            {'identifier': 'teacher@success.example', 'password': 'Strong-Pass-1!'},
            format='json',
            **extra,
        )

    def test_the_login_view_stamps_the_address_and_warns_on_a_change(self):
        self.teacher.last_login_ip = '10.0.0.1'
        self.teacher.save(update_fields=['last_login_ip'])

        login = self._sign_in_as_teacher(HTTP_X_FORWARDED_FOR='203.0.113.9, 10.1.1.1')
        self.assertEqual(login.status_code, 200)

        self.teacher.refresh_from_db()
        # The left-most forwarded entry is the real client, not the proxy.
        self.assertEqual(self.teacher.last_login_ip, '203.0.113.9')
        self.assertIsNotNone(self.teacher.last_login)
        self.assertTrue(
            Notification.objects.filter(user=self.teacher, type='security').exists()
        )

    def test_a_sign_in_from_the_same_address_is_not_reported(self):
        self.teacher.last_login_ip = '203.0.113.9'
        self.teacher.save(update_fields=['last_login_ip'])

        self.assertEqual(self._sign_in_as_teacher(REMOTE_ADDR='203.0.113.9').status_code, 200)
        self.assertFalse(
            Notification.objects.filter(user=self.teacher, type='security').exists()
        )

    def test_the_first_sign_in_after_this_feature_is_not_reported(self):
        self.teacher.last_login_ip = None
        self.teacher.save(update_fields=['last_login_ip'])

        self.assertEqual(self._sign_in_as_teacher(REMOTE_ADDR='198.51.100.4').status_code, 200)
        # A first sign-in from a device is the normal case, not a warning.
        self.assertFalse(
            Notification.objects.filter(user=self.teacher, type='security').exists()
        )

    def test_a_failed_sign_in_records_nothing(self):
        self.teacher.last_login_ip = '10.0.0.1'
        self.teacher.save(update_fields=['last_login_ip'])
        self.teacher.set_password('Strong-Pass-1!')
        self.teacher.save(update_fields=['password'])

        response = self.client.post(
            self.url('/auth/login/'),
            {'identifier': 'teacher@success.example', 'password': 'Wrong-Pass-1!'},
            format='json',
            REMOTE_ADDR='203.0.113.9',
        )
        self.assertEqual(response.status_code, 401)
        self.teacher.refresh_from_db()
        self.assertEqual(self.teacher.last_login_ip, '10.0.0.1')
        self.assertFalse(Notification.objects.filter(type='security').exists())

    def test_ai_usage_alerts_only_the_admin_and_only_per_decile(self):
        event_service.ai_usage_milestone(self.school, used=85, limit=100)
        event_service.ai_usage_milestone(self.school, used=88, limit=100)
        event_service.ai_usage_milestone(self.school, used=95, limit=100)

        self.assertEqual(Notification.objects.filter(user=self.admin, type='ai').count(), 2)
        self.assertFalse(Notification.objects.filter(user=self.teacher, type='ai').exists())

    def test_subscription_reminders_fire_at_each_threshold(self):
        event_service.subscription_ending(self.school, days_left=7)
        event_service.subscription_ending(self.school, days_left=1)
        event_service.subscription_ending(self.school, days_left=1)
        self.assertEqual(
            Notification.objects.filter(user=self.admin, type='subscription').count(), 2,
        )


class NotificationSweepCommandTests(NotificationTestCase):
    def test_the_command_runs_and_reports(self):
        from io import StringIO

        from django.core.management import call_command

        out = StringIO()
        call_command('sweep_notifications', stdout=out)
        self.assertIn('Swept', out.getvalue())

    def test_the_command_warns_a_school_about_to_lapse(self):
        from datetime import timedelta

        from django.core.management import call_command

        subscription = self.school.subscription
        subscription.expires_at = timezone.now() + timedelta(days=3, hours=1)
        subscription.save(update_fields=['expires_at'])

        call_command('sweep_notifications', stdout=None)

        note = Notification.objects.filter(type='subscription').first()
        self.assertIsNotNone(note)
        self.assertIn('3', note.title)

    def test_the_command_expires_a_lapsed_subscription(self):
        from schools.models import SchoolSubscription

        subscription = self.school.subscription
        subscription.expires_at = timezone.now() - timedelta(days=1)
        subscription.save(update_fields=['expires_at'])

        from django.core.management import call_command
        call_command('sweep_notifications', stdout=None)

        subscription.refresh_from_db()
        self.assertEqual(subscription.status, SchoolSubscription.Status.EXPIRED)


class PlatformBroadcastTests(NotificationTestCase):
    """A platform broadcast is addressed to every tenant at once.

    The delivery decision here is deliberate and worth pinning, because it is
    the one place where the "one row per recipient" rule does not apply.
    """

    def test_a_broadcast_reaches_every_school_board_without_per_user_rows(self):
        manager = User.objects.create_user(
            email='platform@frontline.example', password='Strong-Pass-1!',
            role=User.Role.PLATFORM_MANAGER, school=None, is_active=True,
            is_staff=True, is_superuser=True,
        )
        item = announcement_service.create_platform(
            author=manager, title='Scheduled maintenance', body='Downtime on Sunday.',
        )

        self.assertEqual(item.scope, Announcement.Scope.PLATFORM)
        self.assertIsNone(item.school_id)

        # Delivered on the board of both schools...
        for user in (self.admin, self.other_admin):
            self.assertTrue(
                announcement_service.visible_to(user).filter(pk=item.pk).exists(),
                f'{user.role} should see the broadcast',
            )

        # ...and deliberately not written into anybody's notification centre,
        # which would be one row per user across every tenant on one POST.
        self.assertFalse(Notification.objects.filter(title='Scheduled maintenance').exists())

    def test_a_broadcast_is_not_editable_through_the_school_endpoint(self):
        manager = User.objects.create_user(
            email='platform2@frontline.example', password='Strong-Pass-1!',
            role=User.Role.PLATFORM_MANAGER, school=None, is_active=True,
            is_staff=True, is_superuser=True,
        )
        item = announcement_service.create_platform(
            author=manager, title='Broadcast', body='Body',
        )

        # A school manager has no route to a platform row: publishing, editing and
        # deleting all resolve through the school-scoped queryset.
        self.auth(self.admin)
        self.assertEqual(self.client.get(self.url(f'/announcements/{item.pk}/')).status_code, 404)
        self.assertEqual(
            self.client.patch(
                self.url(f'/announcements/{item.pk}/'), {'title': 'Hijacked'}, format='json',
            ).status_code,
            404,
        )
        self.assertEqual(self.client.delete(self.url(f'/announcements/{item.pk}/')).status_code, 404)
        item.refresh_from_db()
        self.assertEqual(item.title, 'Broadcast')

    def test_a_broadcast_does_not_appear_in_a_schools_create_path(self):
        # Creating through the school endpoint must always record the school, or
        # a bug there would silently turn a school notice into a broadcast.
        self.auth(self.admin)
        response = self.client.post(
            self.url('/announcements/'),
            {'title': 'Notice', 'body': 'Body', 'audience': ['All']},
            format='json',
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data['scope'], Announcement.Scope.SCHOOL)
        self.assertEqual(response.data['author'], 'Admin Test')
