"""Thin Paystack client built on the standard library.

Deliberately dependency-free: the backend already makes one outbound HTTP call
this way for reverse geocoding, and pulling in a third-party SDK for two calls
would widen the dependency surface for no benefit.

Every call reads the secret key from settings. When it is absent the caller gets
:class:`PaystackConfigError`, so an endpoint can refuse to start a charge rather
than silently marking a school as paid. Nothing here ever trusts a
client-supplied amount or reference: the caller resolves those from the database
first, and verification is the only thing that ever confirms a payment.
"""
from __future__ import annotations

import hashlib
import hmac
import json
from urllib import error, parse, request

from django.conf import settings


class PaystackError(Exception):
    """Any failure talking to Paystack: network, HTTP, or a rejected payload."""


class PaystackConfigError(PaystackError):
    """Raised when the secret key is not configured on this deployment."""


def _secret_key() -> str:
    key = getattr(settings, 'PAYSTACK_SECRET_KEY', '') or ''
    if not key:
        raise PaystackConfigError('Online payments are not configured on this server yet.')
    return key


def _base_url() -> str:
    base = getattr(settings, 'PAYSTACK_BASE_URL', '') or 'https://api.paystack.co'
    return base.rstrip('/')


def _call(method: str, path: str, payload: dict | None = None, timeout: int = 20) -> dict:
    url = f'{_base_url()}{path}'
    data = json.dumps(payload).encode('utf-8') if payload is not None else None
    req = request.Request(url, data=data, method=method)
    req.add_header('Authorization', f'Bearer {_secret_key()}')
    req.add_header('Content-Type', 'application/json')
    req.add_header('Accept', 'application/json')
    try:
        with request.urlopen(req, timeout=timeout) as response:
            body = response.read().decode('utf-8')
    except error.HTTPError as exc:
        detail = exc.read().decode('utf-8', 'replace')
        raise PaystackError(f'Paystack returned HTTP {exc.code}: {detail[:300]}') from exc
    except error.URLError as exc:
        raise PaystackError(f'Could not reach Paystack: {exc.reason}') from exc
    try:
        parsed = json.loads(body)
    except ValueError as exc:
        raise PaystackError('Paystack returned an unreadable response.') from exc
    if not parsed.get('status', False):
        raise PaystackError(parsed.get('message') or 'Paystack rejected the request.')
    return parsed.get('data') or {}


def initialize_transaction(
    *, email: str, amount_kobo: int, reference: str,
    callback_url: str = '', metadata: dict | None = None,
) -> dict:
    """Start a charge. Returns Paystack's checkout handles (access_code, url)."""
    payload = {
        'email': email,
        'amount': int(amount_kobo),
        'reference': reference,
        'currency': 'NGN',
    }
    if callback_url:
        payload['callback_url'] = callback_url
    if metadata:
        payload['metadata'] = metadata
    return _call('POST', '/transaction/initialize', payload)


def verify_transaction(reference: str) -> dict:
    """Ask Paystack what really happened to a transaction, by our reference."""
    return _call('GET', f'/transaction/verify/{parse.quote(reference, safe="")}')


def verify_webhook_signature(raw_body: bytes, signature: str) -> bool:
    """True when a webhook body was signed with our secret key.

    A webhook is unauthenticated by nature, so the HMAC over the raw bytes is
    the *only* thing that proves it came from Paystack. Compared in constant
    time so a signature cannot be guessed byte by byte.
    """
    key = getattr(settings, 'PAYSTACK_SECRET_KEY', '') or ''
    if not key or not signature:
        return False
    expected = hmac.new(key.encode('utf-8'), raw_body, hashlib.sha512).hexdigest()
    return hmac.compare_digest(expected, signature)
