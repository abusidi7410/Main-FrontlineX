"""Serializers for wallet & billing endpoints (camelCase for the frontend)."""
from rest_framework import serializers

from .models import SmsAlert, WalletDeposit, WalletTransaction


class WalletTransactionSerializer(serializers.ModelSerializer):
    studentName = serializers.SerializerMethodField()
    admissionNumber = serializers.SerializerMethodField()

    class Meta:
        model = WalletTransaction
        fields = [
            'id', 'reference', 'direction', 'amount_kobo', 'category', 'status',
            'message_reference', 'provider_reference',
            'balance_before_kobo', 'balance_after_kobo',
            'description', 'created_at', 'studentName', 'admissionNumber',
        ]

    def get_studentName(self, obj):
        if obj.student is None:
            return ''
        return f'{obj.student.first_name} {obj.student.last_name}'.strip()

    def get_admissionNumber(self, obj):
        return obj.student.admission_number if obj.student else ''


class WalletDepositSerializer(serializers.ModelSerializer):
    class Meta:
        model = WalletDeposit
        fields = [
            'id', 'reference', 'amount_kobo', 'currency', 'status',
            'authorization_url', 'created_at',
        ]


class StudentAccessSerializer(serializers.Serializer):
    """Built from a dict in the view (student + entitlement + status)."""

    studentId = serializers.CharField(source='student.pk')
    studentName = serializers.SerializerMethodField()
    admissionNumber = serializers.SerializerMethodField()
    status = serializers.CharField()
    priceKobo = serializers.IntegerField()
    periodStart = serializers.SerializerMethodField()
    periodEnd = serializers.SerializerMethodField()
    amountKobo = serializers.SerializerMethodField()

    def get_studentName(self, obj):
        student = obj['student']
        return f'{student.first_name} {student.last_name}'.strip()

    def get_admissionNumber(self, obj):
        return obj['student'].admission_number or ''

    def get_periodStart(self, obj):
        entitlement = obj.get('entitlement')
        return entitlement.period_start.isoformat() if entitlement else None

    def get_periodEnd(self, obj):
        entitlement = obj.get('entitlement')
        return entitlement.period_end.isoformat() if entitlement else None

    def get_amountKobo(self, obj):
        entitlement = obj.get('entitlement')
        return entitlement.amount_kobo if entitlement else None


class SmsAlertSerializer(serializers.ModelSerializer):
    class Meta:
        model = SmsAlert
        fields = [
            'id', 'reference', 'recipient', 'message', 'status',
            'customer_kobo', 'provider_cost_kobo', 'provider_reference',
            'provider_error', 'created_at',
        ]
