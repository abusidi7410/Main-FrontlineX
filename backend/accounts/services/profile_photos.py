"""Cloudinary-backed user profile photos; only the Cloudinary public ID is local."""
from __future__ import annotations

import logging
from uuid import uuid4

import cloudinary
import cloudinary.uploader
from django.conf import settings
from django.core.files.uploadedfile import UploadedFile
from cloudinary.exceptions import Error as CloudinaryError

logger = logging.getLogger(__name__)


MAX_PROFILE_PHOTO_BYTES = 5 * 1024 * 1024
PROFILE_PHOTO_FOLDER = 'frontlinex/profile-photos'


class StorageNotConfigured(RuntimeError):
    """Raised when the deployment has not configured Cloudinary credentials."""


class StorageError(RuntimeError):
    """Raised when Cloudinary rejects or cannot complete an image operation."""


def _configured():
    try:
        if settings.CLOUDINARY_URL:
            cloudinary.config(secure=True)
        config = cloudinary.config()
    except ValueError as exc:
        raise StorageNotConfigured('CLOUDINARY_URL is invalid.') from exc
    if not (config.cloud_name and config.api_key and config.api_secret):
        raise StorageNotConfigured(
            'Profile photo storage is not configured. Contact your administrator.'
        )
    return config


def avatar_url(public_id: str) -> str | None:
    if not public_id:
        return None
    try:
        _configured()
    except StorageNotConfigured:
        logger.error('Cannot build a profile photo URL because Cloudinary is not configured.')
        return None
    return cloudinary.CloudinaryImage(public_id).build_url(
        secure=True,
        width=256,
        height=256,
        crop='fill',
        gravity='face',
        quality='auto',
        fetch_format='auto',
    )


def upload_profile_photo(uploaded_file: UploadedFile, *, user_id: int) -> str:
    _configured()
    try:
        result = cloudinary.uploader.upload(
            uploaded_file,
            folder=PROFILE_PHOTO_FOLDER,
            public_id=f'user-{user_id}-{uuid4().hex}',
            overwrite=False,
            resource_type='image',
        )
    except CloudinaryError as exc:
        raise StorageError('Cloudinary could not upload the profile photo.') from exc

    public_id = result.get('public_id')
    if not isinstance(public_id, str) or not public_id:
        raise StorageError('Cloudinary did not return a profile photo identifier.')
    return public_id


def delete_profile_photo(public_id: str) -> None:
    _configured()
    try:
        result = cloudinary.uploader.destroy(
            public_id,
            invalidate=True,
            resource_type='image',
        )
    except CloudinaryError as exc:
        raise StorageError('Cloudinary could not delete the profile photo.') from exc
    if result.get('result') not in {'ok', 'not found'}:
        raise StorageError('Cloudinary did not confirm profile photo deletion.')
