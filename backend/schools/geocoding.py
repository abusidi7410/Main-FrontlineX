"""Server-side reverse geocoding via OpenStreetMap's Nominatim.

Proxied through the backend so the browser never talks to a third-party tile or
geocoding host directly: there are no vendor keys to leak, one place to add
caching or rate limiting later, and the frontend stays free of third-party
scripts. Fails soft — any network or parsing error returns ``None`` so the
caller can fall back to showing raw coordinates instead of erroring.
"""
from __future__ import annotations

import json
import urllib.parse
import urllib.request

from django.conf import settings

NOMINATIM_URL = getattr(
    settings,
    'NOMINATIM_REVERSE_URL',
    'https://nominatim.openstreetmap.org/reverse',
)
# Nominatim's usage policy requires an identifying User-Agent.
USER_AGENT = getattr(
    settings,
    'GEOCODER_USER_AGENT',
    'FrontlineNexus/1.0 (school attendance)',
)
TIMEOUT_SECONDS = 5


def reverse_geocode(latitude, longitude):
    """Return ``{label, address, latitude, longitude}`` for a point, or None.

    Returning None (rather than raising) is deliberate: a check-in must never
    fail because a third-party geocoder is slow or down.
    """
    try:
        lat = float(latitude)
        lng = float(longitude)
    except (TypeError, ValueError):
        return None

    query = urllib.parse.urlencode({
        'lat': f'{lat:.6f}',
        'lon': f'{lng:.6f}',
        'format': 'jsonv2',
        'zoom': 18,
        'addressdetails': 1,
    })
    request = urllib.request.Request(
        f'{NOMINATIM_URL}?{query}',
        headers={'User-Agent': USER_AGENT, 'Accept': 'application/json'},
    )
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            payload = json.loads(response.read().decode('utf-8'))
    except Exception:
        return None

    if not isinstance(payload, dict):
        return None
    address = payload.get('address')
    return {
        'label': payload.get('display_name') or '',
        'address': address if isinstance(address, dict) else {},
        'latitude': lat,
        'longitude': lng,
    }
