"""Single-flight guard for cron sweeps.

Two workers (or a cron overlap) running the same sweep in the same minute must
not double-send. Each sweep takes a Postgres session-level advisory lock at
start; the loser exits quietly. The winner releases it in a `finally` block.

Session-level (not transaction-scoped) so the sweep itself can keep using
short transactions throughout. On non-Postgres backends (sqlite in tests)
there is nothing to coordinate, so acquisition trivially succeeds.
"""
from __future__ import annotations

import hashlib

from django.db import connection


def _lock_key(name: str) -> int:
    digest = hashlib.sha256(f'frontlinex:sweep:{name}'.encode('utf-8')).digest()
    # Signed 63-bit int: safe for pg_try_advisory_lock(bigint).
    return int.from_bytes(digest[:8], 'big') % (2**62)


def try_acquire_sweep_lock(name: str) -> bool:
    """True when this process won the sweep; False when another worker holds it."""
    if connection.vendor != 'postgresql':
        return True
    with connection.cursor() as cursor:
        cursor.execute('SELECT pg_try_advisory_lock(%s)', [_lock_key(name)])
        row = cursor.fetchone()
    return bool(row and row[0])


def release_sweep_lock(name: str) -> None:
    """Release a lock taken with :func:`try_acquire_sweep_lock`."""
    if connection.vendor != 'postgresql':
        return
    with connection.cursor() as cursor:
        cursor.execute('SELECT pg_advisory_unlock(%s)', [_lock_key(name)])
