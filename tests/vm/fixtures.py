"""Shared fixtures and configuration helpers for VM-based tests.

This module is the landing zone for code extracted from
``tests/test_boot_image_vm.py``. It will ultimately host:

* tool/host environment probes (``_require_executable`` and friends)
* boot-image build helpers and temporary directory management
* SSH key generation, ISO-building helpers, and disk image fixtures

Only a subset of helpers has been migrated so far to reduce churn while the
module layout stabilizes.
"""

from __future__ import annotations

import os
import shutil
from typing import Optional

import pytest

DEFAULT_SPAWN_TIMEOUT = 900
DEFAULT_LOGIN_TIMEOUT = 300


def _read_timeout_env(name: str, default: int) -> int:
    """Return a positive integer timeout configured via environment variable.

    The defaults are intentionally generous to avoid conflating slow boots with
    test hangs. Values are validated so that misconfiguration surfaces as an
    explicit error rather than silently disabling coverage.
    """

    value = os.environ.get(name)
    if value is None:
        return default
    try:
        parsed = int(value)
    except ValueError as exc:  # pragma: no cover - defensive configuration guard
        raise ValueError(f"{name} must be an integer value") from exc
    if parsed <= 0:  # pragma: no cover - defensive configuration guard
        raise ValueError(f"{name} must be greater than zero")
    return parsed


VM_SPAWN_TIMEOUT: int = _read_timeout_env("BOOT_IMAGE_VM_SPAWN_TIMEOUT", DEFAULT_SPAWN_TIMEOUT)
VM_LOGIN_TIMEOUT: int = _read_timeout_env("BOOT_IMAGE_VM_LOGIN_TIMEOUT", DEFAULT_LOGIN_TIMEOUT)


def _require_executable(executable: str) -> str:
    """Ensure an executable exists in ``PATH`` or skip the invoking test."""

    path: Optional[str] = shutil.which(executable)
    if path is None:
        pytest.skip(f"required executable '{executable}' is not available in PATH")
    return path


__all__ = [
    "DEFAULT_LOGIN_TIMEOUT",
    "DEFAULT_SPAWN_TIMEOUT",
    "VM_LOGIN_TIMEOUT",
    "VM_SPAWN_TIMEOUT",
    "_read_timeout_env",
    "_require_executable",
]
