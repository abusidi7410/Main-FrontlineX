"""Private storage for admission documents.

Admission documents are applicant PII (birth certificates, report cards, ...).
They are therefore *never* written under ``MEDIA_ROOT`` and never given a public
URL: Django's media handler would serve them to anyone who guessed the path.
Every byte is read back through an authorised view that re-checks the caller's
school and permission first.

Two backends exist, chosen by ``DOCUMENT_STORAGE_BACKEND``:

* ``filesystem`` (default) — bytes live in ``PRIVATE_DOCUMENT_ROOT``, which is
  deliberately outside ``MEDIA_ROOT``/``STATIC_ROOT`` so no web server is ever
  configured to serve it.
* ``cloudinary`` — bytes are uploaded as Cloudinary ``raw`` resources with
  ``type='private'``. Cloudinary refuses to deliver a private resource without a
  signed URL, and the URL is minted here for a few minutes at a time.

The storage key is always generated from a UUID; a client-supplied filename can
never influence the path, so traversal and cross-tenant overwrites are
structurally impossible.
"""
from __future__ import annotations

import os
import uuid

from django.conf import settings


class DocumentStorageError(Exception):
    """Raised when a document cannot be persisted or retrieved."""


#: Extension derived from the sniffed content type, never from the upload name.
EXTENSION_BY_CONTENT_TYPE = {
    'application/pdf': 'pdf',
    'image/jpeg': 'jpg',
    'image/png': 'png',
    'image/webp': 'webp',
}


def backend_name() -> str:
    return getattr(settings, 'DOCUMENT_STORAGE_BACKEND', 'filesystem')


def build_key(school_id) -> str:
    """A server-generated key. No part of it comes from the upload."""
    return f'admissions/{school_id}/{uuid.uuid4().hex}'


def extension_for(content_type: str) -> str:
    try:
        return EXTENSION_BY_CONTENT_TYPE[content_type]
    except KeyError as exc:  # pragma: no cover - guarded by validation
        raise DocumentStorageError(f'Unsupported content type {content_type!r}.') from exc


def _root() -> str:
    root = getattr(settings, 'PRIVATE_DOCUMENT_ROOT', None)
    if not root:
        root = os.path.join(settings.BASE_DIR, 'private_documents')
    return str(root)


def _local_path(key: str) -> str:
    """Resolve a key inside the private root, refusing to escape it."""
    root = os.path.abspath(_root())
    path = os.path.abspath(os.path.join(root, *key.split('/')))
    if path != root and not path.startswith(root + os.sep):
        raise DocumentStorageError('Refusing to touch a path outside the private root.')
    return path


def _save_filesystem(key: str, content: bytes) -> str:
    path = _local_path(key)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'wb') as handle:
        handle.write(content)
    return key


def _read_filesystem(key: str) -> bytes:
    path = _local_path(key)
    try:
        with open(path, 'rb') as handle:
            return handle.read()
    except FileNotFoundError as exc:
        raise DocumentStorageError('The stored document is missing.') from exc


def _delete_filesystem(key: str) -> None:
    try:
        os.remove(_local_path(key))
    except FileNotFoundError:
        return


def _cloudinary_config_present() -> bool:
    return bool(getattr(settings, 'CLOUDINARY_URL', ''))


def _save_cloudinary(key: str, content: bytes, extension: str) -> str:
    import cloudinary.uploader

    if not _cloudinary_config_present():  # pragma: no cover - guarded by caller
        raise DocumentStorageError('Cloudinary is not configured.')
    try:
        cloudinary.uploader.upload(
            content,
            public_id=key,
            resource_type='raw',
            type='private',
            format=extension,
            overwrite=True,
        )
    except Exception as exc:  # pragma: no cover - network/SDK failure
        raise DocumentStorageError('The document could not be uploaded.') from exc
    return key


def _read_cloudinary(key: str, extension: str) -> bytes:
    import urllib.request

    import cloudinary.utils

    if not _cloudinary_config_present():  # pragma: no cover - guarded by caller
        raise DocumentStorageError('Cloudinary is not configured.')
    try:
        url = cloudinary.utils.private_download_url(
            key, extension, resource_type='raw', type='private',
        )
        with urllib.request.urlopen(url, timeout=30) as response:  # noqa: S310
            return response.read()
    except Exception as exc:  # pragma: no cover - network/SDK failure
        raise DocumentStorageError('The document could not be read.') from exc


def _delete_cloudinary(key: str) -> None:  # pragma: no cover - network/SDK
    import cloudinary.uploader

    if not _cloudinary_config_present():
        return
    try:
        cloudinary.uploader.destroy(key, resource_type='raw', type='private')
    except Exception:
        return


def save(key: str, content: bytes, extension: str) -> str:
    if backend_name() == 'cloudinary':
        return _save_cloudinary(key, content, extension)
    return _save_filesystem(key, content)


def read(key: str, extension: str) -> bytes:
    if backend_name() == 'cloudinary':
        return _read_cloudinary(key, extension)
    return _read_filesystem(key)


def delete(key: str) -> None:
    if backend_name() == 'cloudinary':  # pragma: no cover - network/SDK
        _delete_cloudinary(key)
        return
    _delete_filesystem(key)


#: Content types we accept, mapped to the magic-byte prefix that must be present
#: in the payload. A browser-supplied ``Content-Type`` is a hint, not proof, so
#: the bytes themselves are checked before anything is stored.
MAGIC_PREFIXES = {
    'application/pdf': b'%PDF-',
    'image/jpeg': b'\xff\xd8\xff',
    'image/png': b'\x89PNG\r\n\x1a\n',
}

ALLOWED_CONTENT_TYPES = frozenset(EXTENSION_BY_CONTENT_TYPE)


def sniff_content_type(head: bytes) -> str | None:
    """Return the content type the bytes actually are, or None when unknown."""
    for content_type, prefix in MAGIC_PREFIXES.items():
        if head.startswith(prefix):
            return content_type
    if head[:4] == b'RIFF' and head[8:12] == b'WEBP':
        return 'image/webp'
    return None
