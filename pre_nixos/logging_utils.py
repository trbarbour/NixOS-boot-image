"""Structured logging helpers for pre-nixos components."""

from __future__ import annotations

import datetime as _dt
import json
import os
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence


def _serialise(value: Any) -> Any:
    """Return a JSON-friendly representation of *value*."""

    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Mapping):
        return {str(key): _serialise(item) for key, item in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_serialise(item) for item in value]
    return repr(value)


def _logs_enabled() -> bool:
    """Return ``True`` when structured logging is enabled via the environment."""

    value = os.environ.get("PRE_NIXOS_LOG_EVENTS")
    if value is None:
        return False
    return value.strip().lower() not in {"", "0", "false", "no"}


def log_event(event: str, **fields: Any) -> None:
    """Emit a structured log entry to ``stderr`` when logging is enabled.

    The entry includes an ISO-8601 UTC timestamp so the consumer can reconstruct
    execution order even when journal output interleaves with other services.
    Non-JSON-serialisable values are converted to strings via ``repr``.
    """

    if not _logs_enabled():
        return

    record = {
        "timestamp": _dt.datetime.now(_dt.timezone.utc).isoformat(),
        "event": event,
    }
    for key, value in fields.items():
        record[str(key)] = _serialise(value)

    sys.stderr.write(json.dumps(record, sort_keys=True) + "\n")
    sys.stderr.flush()

