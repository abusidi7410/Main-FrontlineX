from __future__ import annotations

from decimal import Decimal

from django.utils import timezone

from receipts.amounts import amount_in_words
from receipts.models import Receipt, ReceiptSettings
from records.models import Payment
from records.tests.base import SchoolTestCase


class AmountInWordsTests(SchoolTestCase):
    def test_whole_naira(self):
        self.assertEqual(
            amount_in_words(Decimal('115000')),
            'One hundred and fifteen thousand naira only',
        )

    def test_kobo_is_not_rounded_away(self):
        self.assertEqual(
            amount_in_words(Decimal('2500.75')),
            'Two thousand five hundred naira and seventy-five kobo only',
        )


class ReceiptTests(SchoolTestCase):
    def setUp(self):
        super().setUp()
        self.invoice = self.make_invoice(total='50000')
        self.invoice.paid = Decimal('50000')
        self.invoice.save(update_fields=['paid'])
        self.payment = Payment.objects.create(
            school=self.school,
            invoice=self.invoice,
            amount=Decimal('50000'),
            method=Payment.Method.CASH,
            status=Payment.Status.VERIFIED,
            reference='PAY-0001',
            verified_by=self.accountant,
            verified_at=timezone.now(),
        )

    def url_for(self, path):
        return self.url(path)

    def issue(self, payment=None, **extra):
        return self.client.post(
            self.url_for('/receipts/issue/'),
            {'paymentId': (payment or self.payment).pk, **extra},
            format='json',
        )

    def test_issue_numbers_a_receipt_and_snapshots_the_payment(self):
        self.auth(self.accountant)
        response = self.issue()
        self.assertEqual(response.status_code, 201, response.data)
        receipt = response.data
        self.assertEqual(
            receipt['receiptNumber'],
            f'SUA/RCPT/{timezone.localdate().year}/000001',
        )
        self.assertEqual(receipt['status'], 'issued')
        self.assertEqual(receipt['amount'], '50000.00')
        self.assertEqual(receipt['payerName'], 'Test Student')
        self.assertEqual(receipt['studentName'], 'Test Student')
        self.assertEqual(receipt['school']['name'], 'Success Academy')
        self.assertEqual(receipt['payment']['reference'], 'PAY-0001')
        self.assertEqual(receipt['invoice']['total'], '50000.00')
        self.assertEqual(receipt['balanceAfter'], '0.00')

        # A second issue for the same payment is a conflict, and it points the
        # cashier at the receipt that already exists.
        response = self.issue()
        self.assertEqual(response.status_code, 409, response.data)
        self.assertEqual(response.data['fieldErrors']['receiptId'], receipt['id'])

    def test_replacement_voids_the_old_receipt_and_links_the_new_one(self):
        self.auth(self.accountant)
        first = self.issue().data
        response = self.issue(replace=True)
        self.assertEqual(response.status_code, 201, response.data)
        second = response.data
        self.assertNotEqual(second['id'], first['id'])
        self.assertEqual(second['replacesId'], first['id'])

        old = Receipt.objects.get(public_id=first['id'])
        self.assertEqual(old.status, Receipt.Status.VOIDED)
        self.assertEqual(
            old.void_reason, 'Voided and replaced by a corrected receipt.',
        )
        self.assertEqual(
            Receipt.objects.filter(payment=self.payment, status=Receipt.Status.ISSUED).count(),
            1,
        )

    def test_pending_or_reversed_payments_cannot_be_receipted(self):
        self.payment.status = Payment.Status.PENDING
        self.payment.save(update_fields=['status'])
        self.auth(self.accountant)
        response = self.issue()
        self.assertEqual(response.status_code, 400)
        self.assertIn('detail', response.data)

    def test_reprint_is_counted_and_audited(self):
        self.auth(self.accountant)
        receipt_id = self.issue().data['id']

        self.auth(self.secretary)
        response = self.client.post(
            self.url_for(f'/receipts/{receipt_id}/reprint/'), {}, format='json',
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['reprintCount'], 1)

        response = self.client.post(
            self.url_for(f'/receipts/{receipt_id}/reprint/'), {}, format='json',
        )
        self.assertEqual(response.data['reprintCount'], 2)

        from schools.models import AuditLog

        self.assertEqual(
            AuditLog.objects.filter(action='receipt.reprinted').count(), 2,
        )

    def test_void_requires_a_reason_and_only_an_admin_may_do_it(self):
        self.auth(self.accountant)
        receipt_id = self.issue().data['id']

        response = self.client.post(
            self.url_for(f'/receipts/{receipt_id}/void/'), {'reason': 'Wrong amount.'},
            format='json',
        )
        self.assertEqual(response.status_code, 403)

        self.auth(self.admin)
        response = self.client.post(
            self.url_for(f'/receipts/{receipt_id}/void/'), {}, format='json',
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn('reason', response.data['fieldErrors'])

        response = self.client.post(
            self.url_for(f'/receipts/{receipt_id}/void/'),
            {'reason': 'Wrong amount.'}, format='json',
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['status'], 'voided')
        self.assertEqual(response.data['voidReason'], 'Wrong amount.')

        # Voiding a receipt never changes the underlying payment.
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, Payment.Status.VERIFIED)

        # Once voided, a corrected receipt can be issued without the replace flag.
        self.auth(self.accountant)
        response = self.issue()
        self.assertEqual(response.status_code, 201, response.data)
        self.assertIsNone(response.data['replacesId'])

    def test_download_returns_a_pdf_and_is_tenant_scoped(self):
        self.auth(self.accountant)
        receipt_id = self.issue().data['id']
        url = self.url_for(f'/receipts/{receipt_id}/download/')

        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/pdf')
        self.assertEqual(response['X-Content-Type-Options'], 'nosniff')
        body = b''.join(response.streaming_content)
        self.assertTrue(body.startswith(b'%PDF'))
        self.assertGreater(len(body), 1000)

        self.auth(self.other_admin)
        self.assertEqual(self.client.get(url).status_code, 404)

        self.auth(self.teacher)
        self.assertEqual(self.client.get(url).status_code, 403)

    def test_search_status_and_stats(self):
        self.auth(self.accountant)
        self.issue()
        second_invoice = self.make_invoice(
            total='20000', term='First Term', student=self.invoice.student,
        )
        Payment.objects.create(
            school=self.school, invoice=second_invoice, amount=Decimal('20000'),
            method=Payment.Method.BANK_TRANSFER, status=Payment.Status.VERIFIED,
            reference='PAY-0002',
        )
        # The second invoice has no verified-by user; issue still works because
        # only the payment status matters.
        response = self.client.post(
            self.url_for('/receipts/issue/'),
            {'paymentId': second_invoice.payments.first().pk}, format='json',
        )
        self.assertEqual(response.status_code, 201, response.data)

        response = self.client.get(self.url_for('/receipts/?search=PAY-0001'))
        self.assertEqual(response.data['count'], 1)
        response = self.client.get(self.url_for('/receipts/?status=issued'))
        self.assertEqual(response.data['count'], 2)

        response = self.client.get(self.url_for('/receipts/stats/'))
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['totalIssued'], 2)
        self.assertEqual(response.data['totalVoided'], 0)
        self.assertEqual(len(response.data['recent']), 2)

    def test_permissions_for_list_and_settings(self):
        self.auth(self.teacher)
        self.assertEqual(self.client.get(self.url_for('/receipts/')).status_code, 403)

        self.auth(self.secretary)
        self.assertEqual(self.client.get(self.url_for('/receipts/')).status_code, 200)
        self.assertEqual(self.issue().status_code, 403)

        self.assertEqual(
            self.client.patch(
                self.url_for('/receipts/settings/'), {'prefix': 'FEE'}, format='json',
            ).status_code,
            403,
        )
        self.assertEqual(self.client.get(self.url_for('/receipts/settings/')).status_code, 200)

        self.auth(self.admin)
        response = self.client.patch(
            self.url_for('/receipts/settings/'),
            {'prefix': 'fee', 'paperSize': 'A4', 'showLogo': False, 'footerNote': 'Keep this.'},
            format='json',
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['prefix'], 'FEE')
        self.assertEqual(response.data['paperSize'], 'A4')
        self.assertFalse(response.data['showLogo'])

        # New receipts use the configured prefix and settings.
        self.auth(self.accountant)
        receipt = self.issue().data
        self.assertIn('/FEE/', receipt['receiptNumber'])

    def test_numbering_is_sequential_per_school_and_year(self):
        self.auth(self.accountant)
        first = self.issue().data['receiptNumber']
        second_invoice = self.make_invoice(
            total='1000', term='Second Term', student=self.invoice.student,
        )
        Payment.objects.create(
            school=self.school, invoice=second_invoice, amount=Decimal('1000'),
            method=Payment.Method.CASH, status=Payment.Status.VERIFIED,
            reference='PAY-0003',
        )
        second = self.client.post(
            self.url_for('/receipts/issue/'),
            {'paymentId': second_invoice.payments.first().pk}, format='json',
        ).data['receiptNumber']
        self.assertTrue(first.endswith('/000001'))
        self.assertTrue(second.endswith('/000002'))

    def test_receipt_settings_are_created_lazily(self):
        self.assertFalse(ReceiptSettings.objects.filter(school=self.school).exists())
        self.auth(self.accountant)
        response = self.client.get(self.url_for('/receipts/settings/'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['prefix'], 'RCPT')
        self.assertTrue(ReceiptSettings.objects.filter(school=self.school).exists())
