"""Shared resolution of public (UUID) identifiers.

Internal primary keys stay the real identity of every row; `public_id` is the
only identifier a client ever sees or sends. These helpers keep the two worlds
separate and, crucially, stop an arbitrary string from reaching an ORM lookup
where a UUIDField would raise a Django ValidationError mid-query and turn a
simple "bad id" into a 500.
"""
from __future__ import annotations

import uuid

from django.http import Http404


def parse_public_id(value) -> uuid.UUID | None:
    """A public id parsed to a UUID, or ``None`` when it is not one.

    ``None`` means "this value cannot be any row's public id", which callers
    treat as not-found (404) rather than as a malformed request.
    """
    try:
        return uuid.UUID(str(value))
    except (TypeError, ValueError, AttributeError):
        return None


def required_public_id(value):
    """A public id parsed to a UUID or ``Http404``.

    A hand-crafted id for a student, staff member or other public-id entity
    answers exactly like an id that does not exist: the response never
    distinguishes "badly formatted" from "never existed".
    """
    parsed = parse_public_id(value)
    if parsed is None:
        raise Http404
    return parsed