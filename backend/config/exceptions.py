"""API-wide DRF exception handler.

Normalises DRF error responses into the shape the frontend client expects:

    {"detail": "…", "fieldErrors": {"email": "…"}}

Non-validation errors (403/404/401) keep DRF's native ``detail`` shape.
This gives every endpoint one consistent contract so the client's
``apiFetch`` can surface per-field errors without special casing.
"""
from rest_framework.response import Response
from rest_framework.views import exception_handler


def frontline_exception_handler(exc, context):
    response = exception_handler(exc, context)
    if response is None:
        return response

    data = response.data
    if not isinstance(data, dict):
        return response

    field_errors = {}
    detail = data.get('detail')
    for key, value in data.items():
        if key == 'detail':
            continue
        if isinstance(value, (list, tuple)):
            field_errors[key] = str(value[0]) if value else ''
        else:
            field_errors[key] = str(value)

    if field_errors:
        return Response(
            {
                'detail': detail or 'Please correct the marked fields and try again.',
                'fieldErrors': field_errors,
            },
            status=response.status_code,
        )
    return response