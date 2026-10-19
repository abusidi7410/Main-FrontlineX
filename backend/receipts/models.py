import uuid

from django.db import models
from django.db.models import Q

from schools.models import School


class ReceiptSequence(models.Model):
    """Per-school, per-year receipt counter.

    Like admission numbers, receipt numbers are never derived with
    ``max(number) + 1``: the sequence row is locked and advanced in place so two
    cashiers issuing at the same moment cannot mint the same receipt.
    """

    school = models.ForeignKey(
        School, on_delete=models.CASCADE, related_name='receipt_sequences',
    )
    year = models.PositiveIntegerField()
    last_serial = models.PositiveIntegerField(default=0)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['school', 'year'], name='unique_receipt_sequence_per_year',
            ),
        ]

    def __str__(self):
        return f'{self.school_id}/{self.year} → {self.last_serial}'


class ReceiptSettings(models.Model):
    """School-configurable receipt branding."""

    class PaperSize(models.TextChoices):
        A5 = 'A5', 'A5 (receipt)'
        A4 = 'A4', 'A4 (full page)'

    school = models.OneToOneField(
        School, on_delete=models.CASCADE, related_name='receipt_settings',
    )
    prefix = models.CharField(max_length=10, default='RCPT')
    footer_note = models.CharField(
        max_length=255, default='Thank you for your payment.',
        blank=True,
    )
    paper_size = models.CharField(
        max_length=2, choices=PaperSize.choices, default=PaperSize.A5,
    )
    show_logo = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = 'receipt settings'

    def __str__(self):
        return f'Receipt settings — {self.school_id}'


class Receipt(models.Model):
    """An issued official fee receipt.

    A receipt is a *snapshot* of the payment, school and student at the moment
    it was issued. Later edits to a student's class, a school's address or the
    fee structure must not silently rewrite a document a parent already holds.

    At most one ISSUED receipt exists per payment (enforced by a partial unique
    constraint). Correcting a receipt voids the old one and issues a replacement
    linked through ``replaces``; the payment itself is never altered.
    """

    class Status(models.TextChoices):
        ISSUED = 'issued', 'Issued'
        VOIDED = 'voided', 'Voided'

    school = models.ForeignKey(
        School, on_delete=models.CASCADE, related_name='receipts',
    )
    public_id = models.UUIDField(
        default=uuid.uuid4, unique=True, editable=False, db_index=True,
    )
    payment = models.ForeignKey(
        'records.Payment', on_delete=models.CASCADE, related_name='receipts',
    )
    receipt_number = models.CharField(max_length=40)
    status = models.CharField(
        max_length=10, choices=Status.choices, default=Status.ISSUED,
    )

    payer_name = models.CharField(max_length=200)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    amount_in_words = models.CharField(max_length=255)
    purpose = models.CharField(max_length=255)
    balance_after = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    # Immutable snapshots. Strings only, so the document round-trips exactly.
    school_snapshot = models.JSONField(default=dict, blank=True)
    student_snapshot = models.JSONField(default=dict, blank=True)
    invoice_snapshot = models.JSONField(default=dict, blank=True)
    payment_snapshot = models.JSONField(default=dict, blank=True)

    issued_by = models.ForeignKey(
        'accounts.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='issued_receipts',
    )
    issued_at = models.DateTimeField(auto_now_add=True)
    reprint_count = models.PositiveIntegerField(default=0)
    last_reprinted_at = models.DateTimeField(null=True, blank=True)
    last_reprinted_by = models.ForeignKey(
        'accounts.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='reprinted_receipts',
    )
    voided_by = models.ForeignKey(
        'accounts.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='voided_receipts',
    )
    voided_at = models.DateTimeField(null=True, blank=True)
    void_reason = models.CharField(max_length=255, blank=True, default='')
    replaces = models.ForeignKey(
        'self', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='replacement_receipts',
    )

    class Meta:
        ordering = ['-issued_at']
        constraints = [
            models.UniqueConstraint(
                fields=['school', 'receipt_number'],
                name='unique_receipt_number_per_school',
            ),
            # One live receipt per payment. A voided receipt stays as history,
            # so it does not occupy the slot and a corrected receipt can be
            # issued for the same payment.
            models.UniqueConstraint(
                fields=['payment'],
                condition=Q(status='issued'),
                name='one_issued_receipt_per_payment',
            ),
        ]
        indexes = [
            models.Index(fields=['school', 'status']),
            models.Index(fields=['school', '-issued_at']),
            models.Index(fields=['school', 'receipt_number']),
        ]

    def __str__(self):
        return f'{self.receipt_number} ({self.status})'

    @property
    def is_void(self) -> bool:
        return self.status == self.Status.VOIDED
