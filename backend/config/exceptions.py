"""API-wide DRF exception handler.

Normalises DRF error responses into the shape the frontend client expects:

    {"detail": "…", "fieldErrors": {"email": "…"}}

Non-validation errors (403/404/401) keep DRF's native ``detail`` shape, with a
machine-readable ``code`` added for authentication failures. This gives every
endpoint one consistent contract so the client's ``apiFetch`` can surface
per-field errors without special casing.
"""
from rest_framework.exceptions import AuthenticationFailed
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
        data = {
            'detail': detail or 'Please correct the marked fields and try again.',
            'fieldErrors': field_errors,
        }

    # Authentication failures name why they happened so the client can tell a
    # reason worth showing ("your school was suspended") from the routine
    # "your token expired", which would only read as noise on the login page.
    if isinstance(exc, AuthenticationFailed):
        code = exc.get_codes()
        if isinstance(code, str):
            data = {**data, 'code': code}

    return Response(data, status=response.status_code)