from rest_framework import serializers

from .models import Receipt, ReceiptSettings


class ReceiptSerializer(serializers.ModelSerializer):
    id = serializers.SerializerMethodField()
    receiptNumber = serializers.CharField(source='receipt_number', read_only=True)
    paymentId = serializers.SerializerMethodField()
    payerName = serializers.CharField(source='payer_name', read_only=True)
    amountInWords = serializers.CharField(source='amount_in_words', read_only=True)
    balanceAfter = serializers.DecimalField(
        source='balance_after', max_digits=12, decimal_places=2, read_only=True,
    )
    issuedBy = serializers.SerializerMethodField()
    issuedAt = serializers.DateTimeField(
        source='issued_at', format='%Y-%m-%dT%H:%M:%S', read_only=True,
    )
    reprintCount = serializers.IntegerField(source='reprint_count', read_only=True)
    lastReprintedAt = serializers.DateTimeField(
        source='last_reprinted_at', format='%Y-%m-%dT%H:%M:%S', read_only=True,
    )
    voidedBy = serializers.SerializerMethodField()
    voidedAt = serializers.DateTimeField(
        source='voided_at', format='%Y-%m-%dT%H:%M:%S', read_only=True,
    )
    voidReason = serializers.CharField(source='void_reason', read_only=True)
    replacesId = serializers.SerializerMethodField()
    school = serializers.JSONField(source='school_snapshot', read_only=True)
    student = serializers.JSONField(source='student_snapshot', read_only=True)
    invoice = serializers.JSONField(source='invoice_snapshot', read_only=True)
    payment = serializers.JSONField(source='payment_snapshot', read_only=True)
    studentName = serializers.SerializerMethodField()
    admissionNumber = serializers.SerializerMethodField()
    downloadUrl = serializers.SerializerMethodField()

    class Meta:
        model = Receipt
        fields = [
            'id', 'receiptNumber', 'status', 'paymentId', 'payerName', 'amount',
            'amountInWords', 'purpose', 'balanceAfter', 'issuedBy', 'issuedAt',
            'reprintCount', 'lastReprintedAt', 'voidedBy', 'voidedAt', 'voidReason',
            'replacesId', 'school', 'student', 'invoice', 'payment',
            'studentName', 'admissionNumber', 'downloadUrl',
        ]

    def get_id(self, obj):
        return str(obj.public_id)

    def get_paymentId(self, obj):
        return str(obj.payment_id)

    def get_issuedBy(self, obj):
        return obj.issued_by.get_full_name() if obj.issued_by else ''

    def get_voidedBy(self, obj):
        return obj.voided_by.get_full_name() if obj.voided_by else ''

    def get_replacesId(self, obj):
        return str(obj.replaces.public_id) if obj.replaces_id else None

    def get_studentName(self, obj):
        return (obj.student_snapshot or {}).get('name', '')

    def get_admissionNumber(self, obj):
        return (obj.student_snapshot or {}).get('admissionNumber', '')

    def get_downloadUrl(self, obj):
        return f'/api/v1/receipts/{obj.public_id}/download/'


class ReceiptListSerializer(ReceiptSerializer):
    class Meta(ReceiptSerializer.Meta):
        fields = [
            'id', 'receiptNumber', 'status', 'paymentId', 'payerName',
            'studentName', 'admissionNumber', 'amount', 'purpose', 'issuedAt',
            'voidedAt', 'reprintCount', 'downloadUrl',
        ]


class ReceiptSettingsSerializer(serializers.ModelSerializer):
    footerNote = serializers.CharField(
        source='footer_note', required=False, allow_blank=True, max_length=255,
    )
    paperSize = serializers.ChoiceField(
        source='paper_size', choices=ReceiptSettings.PaperSize.choices, required=False,
    )
    showLogo = serializers.BooleanField(source='show_logo', required=False)

    class Meta:
        model = ReceiptSettings
        fields = ['prefix', 'footerNote', 'paperSize', 'showLogo']

    def validate_prefix(self, value):
        cleaned = ''.join(ch for ch in (value or '').upper() if ch.isalnum())
        if not cleaned:
            raise serializers.ValidationError('Enter a receipt prefix (letters or digits).')
        return cleaned[:10]
