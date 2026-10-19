import io
from datetime import datetime

from django.http import FileResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.permissions import HasSchool, require_permissions
from accounts.utils import audit as log_audit
from records.models import Payment

from . import services
from .models import Receipt
from .pdf import render_receipt_pdf
from .serializers import (
    ReceiptListSerializer,
    ReceiptSerializer,
    ReceiptSettingsSerializer,
)


def _paginate(queryset, request, serializer_class, context=None):
    try:
        page = max(int(request.query_params.get('page', 1)), 1)
    except (TypeError, ValueError) as exc:
        raise ValidationError({'page': 'Enter a valid page number.'}) from exc
    try:
        raw_size = request.query_params.get('page_size') or request.query_params.get('pageSize')
        page_size = int(raw_size) if raw_size not in (None, '') else 20
    except (TypeError, ValueError) as exc:
        raise ValidationError({'pageSize': 'Enter a valid page size.'}) from exc
    page_size = min(max(page_size, 1), 100)

    count = queryset.count()
    start = (page - 1) * page_size
    items = queryset[start:start + page_size]
    return {
        'results': serializer_class(items, many=True, context=context or {}).data,
        'count': count,
        'page': page,
        'pageSize': page_size,
        'totalPages': max((count + page_size - 1) // page_size, 1),
    }


def _receipt(request, public_id):
    return get_object_or_404(
        Receipt.objects.select_related('school', 'payment', 'issued_by', 'voided_by'),
        public_id=public_id,
        school_id=request.user.school_id,
    )


class ReceiptListView(APIView):
    permission_classes = [IsAuthenticated, HasSchool, require_permissions('receipts.read')]

    def get(self, request):
        from django.db.models import Q

        queryset = Receipt.objects.filter(
            school_id=request.user.school_id,
        ).select_related('payment', 'issued_by', 'voided_by')

        status_filter = (request.query_params.get('status') or '').strip()
        if status_filter in Receipt.Status.values:
            queryset = queryset.filter(status=status_filter)

        search = (request.query_params.get('search') or '').strip()
        if search:
            queryset = queryset.filter(
                Q(receipt_number__icontains=search)
                | Q(payer_name__icontains=search)
                | Q(payment__reference__icontains=search)
                | Q(student_snapshot__name__icontains=search)
                | Q(student_snapshot__admissionNumber__icontains=search)
            )

        issued_from = (request.query_params.get('dateFrom') or '').strip()
        if issued_from:
            try:
                start = datetime.strptime(issued_from, '%Y-%m-%d').date()
            except ValueError as exc:
                raise ValidationError({'dateFrom': 'Use YYYY-MM-DD.'}) from exc
            queryset = queryset.filter(issued_at__date__gte=start)
        issued_to = (request.query_params.get('dateTo') or '').strip()
        if issued_to:
            try:
                end = datetime.strptime(issued_to, '%Y-%m-%d').date()
            except ValueError as exc:
                raise ValidationError({'dateTo': 'Use YYYY-MM-DD.'}) from exc
            queryset = queryset.filter(issued_at__date__lte=end)

        return Response(_paginate(
            queryset, request, ReceiptListSerializer, context={'request': request},
        ))


class ReceiptIssueView(APIView):
    permission_classes = [IsAuthenticated, HasSchool, require_permissions('receipts.issue')]

    def post(self, request):
        payment_id = request.data.get('paymentId') or request.data.get('payment_id')
        if not payment_id:
            raise ValidationError({'paymentId': 'Choose the payment to receipt.'})
        payment = get_object_or_404(
            Payment, pk=payment_id, school_id=request.user.school_id,
        )
        replace = bool(request.data.get('replace'))
        receipt = services.issue_receipt(
            payment, actor=request.user, replace=replace,
        )
        log_audit(
            request, 'receipt.issued' if not replace else 'receipt.replaced',
            target='Receipt',
            detail=(
                f'{receipt.receipt_number} issued for {receipt.payer_name} '
                f'({receipt.amount})'
            ),
            entity='receipt', entity_id=str(receipt.public_id),
            after={
                'receiptNumber': receipt.receipt_number,
                'paymentId': str(payment.pk),
                'amount': str(receipt.amount),
            },
        )
        return Response(
            ReceiptSerializer(receipt, context={'request': request}).data,
            status=status.HTTP_201_CREATED,
        )


class ReceiptDetailView(APIView):
    permission_classes = [IsAuthenticated, HasSchool, require_permissions('receipts.read')]

    def get(self, request, public_id):
        return Response(ReceiptSerializer(
            _receipt(request, public_id), context={'request': request},
        ).data)


class ReceiptReprintView(APIView):
    permission_classes = [IsAuthenticated, HasSchool, require_permissions('receipts.reprint')]

    def post(self, request, public_id):
        receipt = services.reprint_receipt(
            _receipt(request, public_id), actor=request.user,
        )
        log_audit(
            request, 'receipt.reprinted', target='Receipt',
            detail=f'{receipt.receipt_number} reprinted (count {receipt.reprint_count})',
            entity='receipt', entity_id=str(receipt.public_id),
        )
        return Response(ReceiptSerializer(
            receipt, context={'request': request},
        ).data)


class ReceiptVoidView(APIView):
    permission_classes = [IsAuthenticated, HasSchool, require_permissions('receipts.void')]

    def post(self, request, public_id):
        receipt = services.void_receipt(
            _receipt(request, public_id),
            reason=request.data.get('reason') or '',
            actor=request.user,
        )
        log_audit(
            request, 'receipt.voided', target='Receipt',
            detail=f'{receipt.receipt_number} voided: {receipt.void_reason}',
            entity='receipt', entity_id=str(receipt.public_id),
        )
        return Response(ReceiptSerializer(
            receipt, context={'request': request},
        ).data)


class ReceiptDownloadView(APIView):
    permission_classes = [IsAuthenticated, HasSchool, require_permissions('receipts.read')]

    def get(self, request, public_id):
        receipt = _receipt(request, public_id)
        pdf_bytes = render_receipt_pdf(receipt)
        response = FileResponse(
            io.BytesIO(pdf_bytes),
            as_attachment=request.query_params.get('inline') != '1',
            filename=f'{receipt.receipt_number.replace("/", "-")}.pdf',
            content_type='application/pdf',
        )
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Cache-Control'] = 'private, no-store'
        return response


class ReceiptStatsView(APIView):
    permission_classes = [IsAuthenticated, HasSchool, require_permissions('receipts.read')]

    def get(self, request):
        from django.db.models import Sum

        queryset = Receipt.objects.filter(school_id=request.user.school_id)
        month_start = timezone.localtime().replace(
            day=1, hour=0, minute=0, second=0, microsecond=0,
        )
        issued = queryset.filter(status=Receipt.Status.ISSUED)
        this_month = issued.filter(issued_at__gte=month_start)
        recent = list(
            queryset.order_by('-issued_at')[:5],
        )
        return Response({
            'totalIssued': issued.count(),
            'totalVoided': queryset.filter(status=Receipt.Status.VOIDED).count(),
            'issuedThisMonth': this_month.count(),
            'valueThisMonth': str(
                this_month.aggregate(total=Sum('amount'))['total'] or 0
            ),
            'recent': ReceiptListSerializer(
                recent, many=True, context={'request': request},
            ).data,
        })


class ReceiptSettingsView(APIView):
    permission_classes = [IsAuthenticated, HasSchool]

    def get_permissions(self):
        if self.request.method in ('PATCH', 'PUT'):
            return [IsAuthenticated(), HasSchool(), require_permissions('receipts.settings')()]
        return [IsAuthenticated(), HasSchool(), require_permissions('receipts.read')()]

    def get(self, request):
        settings_obj = services.get_settings(request.user.school)
        return Response(ReceiptSettingsSerializer(settings_obj).data)

    def patch(self, request):
        settings_obj = services.get_settings(request.user.school)
        serializer = ReceiptSettingsSerializer(
            settings_obj, data=request.data, partial=True,
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        log_audit(
            request, 'receipt.settings_updated', target='ReceiptSettings',
            detail='Receipt branding updated',
            entity='receipt_settings', entity_id=str(settings_obj.pk),
            after=serializer.data,
        )
        return Response(serializer.data)
