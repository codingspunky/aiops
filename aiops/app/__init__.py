from __future__ import annotations

"""Top-level package for aiops app.

This module may contain package-wide utilities and initializations.
"""

from datetime import datetime


def get_current_utc_iso() -> str:
    """Return the current UTC time as an ISO‑8601 string with a trailing ``Z``.

    The function uses :func:`datetime.datetime.utcnow` and appends ``Z`` to
    indicate UTC, matching the common ISO 8601 representation used in APIs.
    """
    return datetime.utcnow().isoformat() + "Z"
