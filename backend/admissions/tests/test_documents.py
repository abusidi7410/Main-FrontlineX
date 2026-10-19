from __future__ import annotations

import os
import shutil
import tempfile

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings

from admissions.models import AdmissionApplication, AdmissionSettings
from admissions.storage import _local_path
from records.tests.base import SchoolTestCase

PDF_BYTES = b'%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>\nendobj\ntrailer\n%%EOF\n'


class AdmissionDocumentTests(SchoolTestCase):
    def setUp(self):
        super().setUp()
        self.private_root = tempfile.mkdtemp(prefix='frontline-private-')
        self.storage_override = override_settings(
            PRIVATE_DOCUMENT_ROOT=self.private_root,
            DOCUMENT_STORAGE_BACKEND='filesystem',
        )
        self.storage_override.enable()
        AdmissionSettings.objects.create(
            school=self.school,
            required_documents=['birth_certificate'],
        )

    def tearDown(self):
        self.storage_override.disable()
        shutil.rmtree(self.private_root, ignore_errors=True)
        super().tearDown()

    def draft(self, **overrides):
        self.auth(self.secretary)
        data = {
            'firstName': 'Amina', 'lastName': 'Yusuf', 'gender': 'female',
            'dateOfBirth': '2015-04-12', 'classId': self.jss1.id,
            'academicSessionId': self.session.id,
            'guardianName': 'Bello Yusuf', 'guardianPhone': '08031234567',
            'guardianAddress': '12 Zoo Road, Kano', 'declaredBy': 'Bello Yusuf',
        }
        data.update(overrides)
        response = self.client.post(
            self.url('/admissions/applications/'), data, format='json',
        )
        self.assertEqual(response.status_code, 201, response.data)
        return response.data['id']

    def upload(self, application_id, *, content=PDF_BYTES, category='birth_certificate',
               filename='birth.pdf', content_type='application/pdf'):
        upload = SimpleUploadedFile(
            filename, content, content_type=content_type,
        )
        return self.client.post(
            self.url(f'/admissions/applications/{application_id}/documents/'),
            {'file': upload, 'category': category},
            format='multipart',
        )

    def submit(self, application_id):
        return self.client.post(
            self.url(f'/admissions/applications/{application_id}/submit/'), {}, format='json',
        )

    def test_upload_stores_bytes_in_the_private_root_not_media(self):
        application_id = self.draft()
        response = self.upload(application_id)
        self.assertEqual(response.status_code, 201, response.data)
        document_id = response.data['id']
        self.assertEqual(response.data['contentType'], 'application/pdf')
        self.assertEqual(response.data['status'], 'pending')

        application = AdmissionApplication.objects.get(public_id=application_id)
        document = application.documents.get(public_id=document_id)
        path = _local_path(document.storage_key)
        self.assertTrue(path.startswith(os.path.abspath(self.private_root)))
        self.assertTrue(os.path.exists(path))
        # The key is generated; it never contains the client's filename.
        self.assertNotIn('birth.pdf', document.storage_key)

        # A public media URL is not a way to reach the file.
        response = self.client.get(f'/media/{document.storage_key}')
        self.assertIn(response.status_code, (403, 404))

    def test_upload_rejects_a_disguised_file_and_an_oversized_file(self):
        application_id = self.draft()
        response = self.upload(
            application_id, content=b'<script>alert(1)</script>',
            filename='evil.pdf', content_type='application/pdf',
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn('file', response.data['fieldErrors'])
        self.assertFalse(
            AdmissionApplication.objects.get(public_id=application_id).documents.exists(),
        )

        with override_settings(PRIVATE_DOCUMENT_MAX_BYTES=10):
            response = self.upload(application_id)
        self.assertEqual(response.status_code, 400)
        self.assertIn('file', response.data['fieldErrors'])

    def test_upload_validates_category_and_requires_a_file(self):
        application_id = self.draft()
        response = self.client.post(
            self.url(f'/admissions/applications/{application_id}/documents/'),
            {}, format='multipart',
        )
        self.assertEqual(response.status_code, 400)

        upload = SimpleUploadedFile('birth.pdf', PDF_BYTES, content_type='application/pdf')
        response = self.client.post(
            self.url(f'/admissions/applications/{application_id}/documents/'),
            {'file': upload, 'category': 'not-a-category'},
            format='multipart',
        )
        self.assertEqual(response.status_code, 400)

    def test_approval_is_blocked_until_required_documents_are_verified(self):
        application_id = self.draft()
        self.upload(application_id)
        self.submit(application_id)

        self.auth(self.principal)
        response = self.client.post(
            self.url(f'/admissions/applications/{application_id}/approve/'), {}, format='json',
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn('documents', response.data['fieldErrors'])

        application = AdmissionApplication.objects.get(public_id=application_id)
        document = application.documents.first()
        response = self.client.post(
            self.url(f'/admissions/documents/{document.public_id}/review/'),
            {'status': 'verified'}, format='json',
        )
        self.assertEqual(response.status_code, 200, response.data)

        response = self.client.post(
            self.url(f'/admissions/applications/{application_id}/approve/'), {}, format='json',
        )
        self.assertEqual(response.status_code, 200, response.data)
        document.refresh_from_db()
        self.assertIsNotNone(document.student_id)

    def test_rejected_documents_do_not_satisfy_the_requirement(self):
        application_id = self.draft()
        self.upload(application_id)
        self.submit(application_id)

        self.auth(self.principal)
        document = AdmissionApplication.objects.get(
            public_id=application_id,
        ).documents.first()
        self.client.post(
            self.url(f'/admissions/documents/{document.public_id}/review/'),
            {'status': 'rejected', 'note': 'Unreadable.'}, format='json',
        )
        response = self.client.post(
            self.url(f'/admissions/applications/{application_id}/approve/'), {}, format='json',
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn('documents', response.data['fieldErrors'])

    def test_download_is_authorised_and_tenant_scoped(self):
        application_id = self.draft()
        document_id = self.upload(application_id).data['id']
        url = self.url(f'/admissions/documents/{document_id}/download/')

        self.auth(self.accountant)
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/pdf')
        self.assertEqual(response['X-Content-Type-Options'], 'nosniff')
        self.assertEqual(b''.join(response.streaming_content), PDF_BYTES)

        self.auth(self.other_admin)
        self.assertEqual(self.client.get(url).status_code, 404)

        self.client.force_authenticate(None)
        self.assertEqual(self.client.get(url).status_code, 401)

    def test_documents_cannot_be_removed_after_submission(self):
        application_id = self.draft()
        document_id = self.upload(application_id).data['id']
        self.submit(application_id)

        response = self.client.delete(
            self.url(f'/admissions/documents/{document_id}/'),
        )
        self.assertEqual(response.status_code, 400)

    def test_draft_document_delete_removes_the_blob(self):
        application_id = self.draft()
        document_id = self.upload(application_id).data['id']
        document = AdmissionApplication.objects.get(
            public_id=application_id,
        ).documents.first()
        path = _local_path(document.storage_key)
        self.assertTrue(os.path.exists(path))

        response = self.client.delete(
            self.url(f'/admissions/documents/{document_id}/'),
        )
        self.assertEqual(response.status_code, 204)
        self.assertFalse(os.path.exists(path))

    def test_draft_documents_are_not_deletable_by_another_school(self):
        application_id = self.draft()
        document_id = self.upload(application_id).data['id']
        self.auth(self.other_admin)
        self.assertEqual(
            self.client.delete(
                self.url(f'/admissions/documents/{document_id}/'),
            ).status_code,
            404,
        )
