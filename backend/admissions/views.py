import io

from django.http import FileResponse
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.permissions import HasSchool, require_permissions
from accounts.utils import audit as log_audit
from billing import services as wallet_billing
from records.services import academic as academic_service

from . import services, storage
from .models import AdmissionApplication, AdmissionDocument
from .serializers import (
    AdmissionApplicationDetailSerializer,
    AdmissionApplicationListSerializer,
    AdmissionDocumentSerializer,
    AdmissionSettingsSerializer,
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


def _application(request, public_id):
    return get_object_or_404(
        AdmissionApplication.objects.select_related(
            'class_applied__level', 'academic_session', 'student', 'duplicate_of',
        ).prefetch_related('documents'),
        public_id=public_id,
        school_id=request.user.school_id,
    )


def _document(request, public_id):
    return get_object_or_404(
        AdmissionDocument,
        public_id=public_id,
        school_id=request.user.school_id,
    )


def _access_payload(result):
    entitlement = result.get('entitlement')
    wallet = result.get('wallet')
    return (
        {
            'amountKobo': entitlement.amount_kobo,
            'periodStart': entitlement.period_start.isoformat(),
            'periodEnd': entitlement.period_end.isoformat(),
            'walletBalanceKobo': wallet.balance_kobo,
        }
        if entitlement is not None and wallet is not None else None
    )


class AdmissionApplicationListCreateView(APIView):
    permission_classes = [IsAuthenticated, HasSchool]

    def get_permissions(self):
        if self.request.method == 'POST':
            return [IsAuthenticated(), HasSchool(), require_permissions('admissions.write')()]
        return [IsAuthenticated(), HasSchool(), require_permissions('admissions.read')()]

    def get(self, request):
        queryset = AdmissionApplication.objects.filter(
            school_id=request.user.school_id,
        ).select_related('class_applied__level', 'academic_session', 'student')

        status_filter = (request.query_params.get('status') or '').strip()
        if status_filter and status_filter in AdmissionApplication.Status.values:
            queryset = queryset.filter(status=status_filter)
        search = (request.query_params.get('search') or '').strip()
        if search:
            from django.db.models import Q

            queryset = queryset.filter(
                Q(first_name__icontains=search)
                | Q(middle_name__icontains=search)
                | Q(last_name__icontains=search)
                | Q(guardian_name__icontains=search)
                | Q(guardian_phone__icontains=search)
                | Q(admission_number__icontains=search)
            )
        class_id = request.query_params.get('classId') or request.query_params.get('class_id')
        if class_id:
            queryset = queryset.filter(class_applied_id=class_id)
        session_id = (
            request.query_params.get('sessionId')
            or request.query_params.get('session_id')
        )
        if session_id:
            queryset = queryset.filter(academic_session_id=session_id)

        return Response(_paginate(
            queryset, request, AdmissionApplicationListSerializer,
            context={'request': request},
        ))

    def post(self, request):
        serializer = AdmissionApplicationDetailSerializer(
            data=request.data, context={'request': request},
        )
        serializer.is_valid(raise_exception=True)
        application = serializer.save(
            school=request.user.school,
            created_by=request.user,
            academic_session=(
                serializer.validated_data.get('academic_session')
                or academic_service.current_session(request.user.school)
            ),
        )
        if application.class_applied_id:
            application.applied_level_code = application.class_applied.level.code
            application.save(update_fields=['applied_level_code'])
        log_audit(
            request, 'admission.created', target='AdmissionApplication',
            detail=f'{application.full_name or "New draft"} — draft started',
            entity='admission_application', entity_id=str(application.public_id),
        )
        return Response(
            AdmissionApplicationDetailSerializer(
                application, context={'request': request},
            ).data,
            status=status.HTTP_201_CREATED,
        )


class AdmissionApplicationDetailView(APIView):
    permission_classes = [IsAuthenticated, HasSchool]

    def get_permissions(self):
        if self.request.method in ('PATCH', 'PUT', 'DELETE'):
            return [IsAuthenticated(), HasSchool(), require_permissions('admissions.write')()]
        return [IsAuthenticated(), HasSchool(), require_permissions('admissions.read')()]

    def get(self, request, public_id):
        return Response(AdmissionApplicationDetailSerializer(
            _application(request, public_id), context={'request': request},
        ).data)

    def patch(self, request, public_id):
        application = _application(request, public_id)
        if not application.is_editable:
            raise ValidationError({
                'detail': 'Only a draft application can be edited. Submit a correction instead.',
            })
        serializer = AdmissionApplicationDetailSerializer(
            application, data=request.data, partial=True, context={'request': request},
        )
        serializer.is_valid(raise_exception=True)
        application = serializer.save()
        if application.class_applied_id:
            level_code = application.class_applied.level.code
        else:
            level_code = ''
        if application.applied_level_code != level_code:
            application.applied_level_code = level_code
            application.save(update_fields=['applied_level_code'])
        log_audit(
            request, 'admission.updated', target='AdmissionApplication',
            detail=f'{application.full_name or "Draft"} saved',
            entity='admission_application', entity_id=str(application.public_id),
        )
        return Response(AdmissionApplicationDetailSerializer(
            application, context={'request': request},
        ).data)

    def delete(self, request, public_id):
        application = _application(request, public_id)
        if application.status != AdmissionApplication.Status.DRAFT:
            raise ValidationError({'detail': 'Only a draft application can be deleted.'})
        for document in list(application.documents.all()):
            services.delete_document(document)
        entity_id = str(application.public_id)
        name = application.full_name
        application.delete()
        log_audit(
            request, 'admission.deleted', target='AdmissionApplication',
            detail=f'{name or "Draft"} deleted',
            entity='admission_application', entity_id=entity_id,
        )
        return Response(status=status.HTTP_204_NO_CONTENT)


class AdmissionSubmitView(APIView):
    permission_classes = [IsAuthenticated, HasSchool, require_permissions('admissions.write')]

    def post(self, request, public_id):
        application = _application(request, public_id)
        allow_duplicate = bool(request.data.get('allowDuplicate'))
        application = services.submit_application(
            application, allow_duplicate=allow_duplicate,
        )
        log_audit(
            request, 'admission.submitted', target='AdmissionApplication',
            detail=f'{application.full_name} submitted for review',
            entity='admission_application', entity_id=str(application.public_id),
        )
        return Response(AdmissionApplicationDetailSerializer(
            _application(request, public_id), context={'request': request},
        ).data)


class AdmissionStartReviewView(APIView):
    permission_classes = [IsAuthenticated, HasSchool, require_permissions('admissions.review')]

    def post(self, request, public_id):
        application = services.start_review(_application(request, public_id))
        log_audit(
            request, 'admission.review_started', target='AdmissionApplication',
            detail=f'{application.full_name} moved to review',
            entity='admission_application', entity_id=str(application.public_id),
        )
        return Response(AdmissionApplicationDetailSerializer(
            _application(request, public_id), context={'request': request},
        ).data)


class AdmissionApproveView(APIView):
    permission_classes = [IsAuthenticated, HasSchool, require_permissions('admissions.review')]

    def post(self, request, public_id):
        application = _application(request, public_id)
        try:
            result = services.approve_application(
                application,
                actor=request.user,
                class_id=request.data.get('classId'),
                admission_number=request.data.get('admissionNumber') or '',
            )
        except wallet_billing.InsufficientFunds as exc:
            return Response(
                {
                    'detail': wallet_billing.error_message(exc),
                    'requiredKobo': exc.required_kobo,
                    'availableKobo': exc.available_kobo,
                },
                status=status.HTTP_402_PAYMENT_REQUIRED,
            )

        approved = result['application']
        invoice = result['invoice']
        student = result['student']
        log_audit(
            request, 'admission.approved', target='AdmissionApplication',
            detail=f'{approved.full_name} admitted as {student.admission_number}',
            entity='admission_application', entity_id=str(approved.public_id),
            after={
                'studentId': str(student.public_id),
                'admissionNumber': student.admission_number,
                'className': student.class_name,
            },
        )
        data = dict(AdmissionApplicationDetailSerializer(
            _application(request, public_id), context={'request': request},
        ).data)
        data.update({
            'studentId': str(student.public_id),
            'invoiceId': str(invoice.id) if invoice else '',
            'invoiceTotal': str(invoice.total) if invoice else '',
            'registrationFeeConfigured': invoice is not None,
            'access': _access_payload(result),
        })
        return Response(data)


class AdmissionRejectView(APIView):
    permission_classes = [IsAuthenticated, HasSchool, require_permissions('admissions.review')]

    def post(self, request, public_id):
        application = services.reject_application(
            _application(request, public_id),
            reason=request.data.get('reason') or '',
            actor=request.user,
        )
        log_audit(
            request, 'admission.rejected', target='AdmissionApplication',
            detail=f'{application.full_name} rejected: {application.decision_reason}',
            entity='admission_application', entity_id=str(application.public_id),
        )
        return Response(AdmissionApplicationDetailSerializer(
            _application(request, public_id), context={'request': request},
        ).data)


class AdmissionWithdrawView(APIView):
    permission_classes = [IsAuthenticated, HasSchool, require_permissions('admissions.write')]

    def post(self, request, public_id):
        application = services.withdraw_application(
            _application(request, public_id),
            reason=request.data.get('reason') or '',
        )
        log_audit(
            request, 'admission.withdrawn', target='AdmissionApplication',
            detail=f'{application.full_name} withdrawn',
            entity='admission_application', entity_id=str(application.public_id),
        )
        return Response(AdmissionApplicationDetailSerializer(
            _application(request, public_id), context={'request': request},
        ).data)


class AdmissionDocumentListView(APIView):
    permission_classes = [IsAuthenticated, HasSchool, require_permissions('admissions.write')]
    parser_classes = [MultiPartParser, FormParser]

    def get(self, request, public_id):
        application = _application(request, public_id)
        return Response(AdmissionDocumentSerializer(
            application.documents.all(), many=True, context={'request': request},
        ).data)

    def post(self, request, public_id):
        application = _application(request, public_id)
        file = request.FILES.get('file') or request.FILES.get('document')
        if file is None:
            raise ValidationError({'file': 'Choose a file to upload.'})
        content = file.read()
        document = services.store_document(
            application=application,
            category=request.data.get('category') or '',
            filename=file.name,
            content=content,
            actor=request.user,
        )
        log_audit(
            request, 'admission.document_uploaded', target='AdmissionDocument',
            detail=(
                f'{document.get_category_display()} uploaded for '
                f'{application.full_name}'
            ),
            entity='admission_document', entity_id=str(document.public_id),
            after={'filename': document.original_filename, 'bytes': document.size_bytes},
        )
        return Response(
            AdmissionDocumentSerializer(document, context={'request': request}).data,
            status=status.HTTP_201_CREATED,
        )


class AdmissionDocumentDetailView(APIView):
    permission_classes = [IsAuthenticated, HasSchool, require_permissions('admissions.write')]

    def delete(self, request, public_id):
        document = _document(request, public_id)
        application = document.application
        if application is not None and not application.is_editable:
            raise ValidationError({
                'detail': 'Documents cannot be removed from a submitted application.',
            })
        entity_id = str(document.public_id)
        label = document.get_category_display()
        application_name = application.full_name if application else ''
        services.delete_document(document)
        log_audit(
            request, 'admission.document_deleted', target='AdmissionDocument',
            detail=f'{label} removed for {application_name}',
            entity='admission_document', entity_id=entity_id,
        )
        return Response(status=status.HTTP_204_NO_CONTENT)


class AdmissionDocumentReviewView(APIView):
    permission_classes = [IsAuthenticated, HasSchool, require_permissions('admissions.review')]

    def post(self, request, public_id):
        document = _document(request, public_id)
        document = services.review_document(
            document,
            status=request.data.get('status') or '',
            actor=request.user,
            note=request.data.get('note') or '',
        )
        log_audit(
            request, 'admission.document_reviewed', target='AdmissionDocument',
            detail=f'{document.get_category_display()} marked {document.status}',
            entity='admission_document', entity_id=str(document.public_id),
            after={'status': document.status, 'note': document.review_note},
        )
        return Response(AdmissionDocumentSerializer(
            document, context={'request': request},
        ).data)


class AdmissionDocumentDownloadView(APIView):
    permission_classes = [IsAuthenticated, HasSchool, require_permissions('admissions.read')]

    def get(self, request, public_id):
        document = _document(request, public_id)
        try:
            content = storage.read(document.storage_key, document.extension)
        except storage.DocumentStorageError as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_404_NOT_FOUND)

        log_audit(
            request, 'admission.document_downloaded', target='AdmissionDocument',
            detail=f'{document.original_filename} downloaded',
            entity='admission_document', entity_id=str(document.public_id),
        )
        response = FileResponse(
            io.BytesIO(content),
            as_attachment=request.query_params.get('inline') != '1',
            filename=document.original_filename,
            content_type=document.content_type,
        )
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Cache-Control'] = 'private, no-store'
        return response


class AdmissionStatsView(APIView):
    permission_classes = [IsAuthenticated, HasSchool, require_permissions('admissions.read')]

    def get(self, request):
        from django.db.models import Count, Q
        from django.utils import timezone

        school_id = request.user.school_id
        queryset = AdmissionApplication.objects.filter(school_id=school_id)
        counts = queryset.aggregate(**{
            status_value: Count('id', filter=Q(status=status_value))
            for status_value in AdmissionApplication.Status.values
        })
        month_start = timezone.localtime().replace(
            day=1, hour=0, minute=0, second=0, microsecond=0,
        )
        return Response({
            'total': queryset.count(),
            'draft': counts.get('draft', 0),
            'submitted': counts.get('submitted', 0),
            'underReview': counts.get('under_review', 0),
            'approved': counts.get('approved', 0),
            'rejected': counts.get('rejected', 0),
            'withdrawn': counts.get('withdrawn', 0),
            'needsReview': counts.get('submitted', 0) + counts.get('under_review', 0),
            'approvedThisMonth': queryset.filter(
                status=AdmissionApplication.Status.APPROVED,
                reviewed_at__gte=month_start,
            ).count(),
        })


class AdmissionSettingsView(APIView):
    permission_classes = [IsAuthenticated, HasSchool]

    def get_permissions(self):
        if self.request.method in ('PATCH', 'PUT'):
            return [IsAuthenticated(), HasSchool(), require_permissions('admissions.settings')()]
        return [IsAuthenticated(), HasSchool(), require_permissions('admissions.read')()]

    def get(self, request):
        settings_obj = services.get_settings(request.user.school)
        return Response(AdmissionSettingsSerializer(settings_obj).data)

    def patch(self, request):
        settings_obj = services.get_settings(request.user.school)
        serializer = AdmissionSettingsSerializer(
            settings_obj, data=request.data, partial=True,
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        log_audit(
            request, 'admission.settings_updated', target='AdmissionSettings',
            detail='Admission requirements updated',
            entity='admission_settings', entity_id=str(settings_obj.pk),
            after=serializer.data,
        )
        return Response(serializer.data)
