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

    message = json.dumps(record, sort_keys=True)

    sys.stderr.write(message + "\n")
    sys.stderr.flush()
    _append_to_log_file(message)

_DEFAULT_LOG_FILE = Path("/var/log/pre-nixos/actions.log")


def _log_file_path() -> Path:
    """Return the configured log file path.

    When ``PRE_NIXOS_LOG_FILE`` is not set or is empty, fall back to the
    default location used by the boot image.
    """

    value = os.environ.get("PRE_NIXOS_LOG_FILE")
    if value is None or value.strip() == "":
        return _DEFAULT_LOG_FILE
    return Path(value)


def _append_to_log_file(message: str) -> None:
    """Append the given JSON *message* to the configured log file."""

    log_file = _log_file_path()
    try:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        with log_file.open("a", encoding="utf-8") as handle:
            handle.write(message + "\n")
    except OSError as exc:  # pragma: no cover - defensive logging path
        sys.stderr.write(f"pre-nixos: failed to write log to {log_file}: {exc}\n")
        sys.stderr.flush()
