"""Keep unit tests independent of the build host's block devices.

``storage_detection.detect_existing_storage()`` inspects the real machine
(``lsblk``/``wipefs``), so any test that reaches it unguarded behaves
differently on every host: it passes on a host without disks, and fails where
probing is refused (EPERM in sandboxed containers) or where disks carry
signatures.  The autouse ``existing_storage`` fixture replaces the scan for
every test.  A test that reaches the scan must state the scenario it expects;
otherwise it fails with an explanation, so a hidden dependency on host
storage cannot pass by accident.

Usage::

    def test_something(existing_storage):
        existing_storage.devices = []                 # clean machine
        existing_storage.devices = [ExistingStorageDevice(...)]
        existing_storage.error = RuntimeError("...")  # scan failure

Tests of the scan logic itself call ``detect_existing_storage(env)`` with a
fake ``DetectionEnvironment`` (see ``tests/test_storage_detection.py``); the
real commands are exercised by the VM tests under ``tests/vm``.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence

import pytest

from pre_nixos import storage_detection
from pre_nixos.storage_detection import ExistingStorageDevice


class UndeclaredStorageScan(BaseException):
    """Raised when a test reaches the storage scan without a scenario.

    Deliberately a ``BaseException``: production callers wrap the scan in
    ``except Exception`` (reporting a scan failure), which would otherwise
    swallow this and disguise the missing scenario as a scan error.  pytest
    reports it as an ordinary test failure.
    """


@dataclass
class ExistingStorageStub:
    """Scenario returned by the stubbed scan; ``calls`` counts invocations."""

    devices: Sequence[ExistingStorageDevice] | None = None
    error: Exception | None = None
    protected_disks: frozenset[str] = frozenset()
    calls: int = field(default=0, init=False)

    def scan(self) -> list[ExistingStorageDevice]:
        self.calls += 1
        if self.error is not None:
            assert self.devices is None, "set either devices or error, not both"
            raise self.error
        if self.devices is None:
            raise UndeclaredStorageScan(
                "test reached storage_detection.detect_existing_storage() without "
                "declaring a scenario; set existing_storage.devices or "
                "existing_storage.error (see tests/storage_stub.py)"
            )
        return list(self.devices)


@pytest.fixture(autouse=True)
def existing_storage(monkeypatch: pytest.MonkeyPatch) -> ExistingStorageStub:
    stub = ExistingStorageStub()
    monkeypatch.setattr(
        storage_detection, "detect_existing_storage", lambda *args, **kwargs: stub.scan()
    )
    # resolve_protected_disks also inspects the host (findmnt/lsblk); tests get
    # the declared set instead (empty unless a test assigns one).
    monkeypatch.setattr(
        storage_detection,
        "resolve_protected_disks",
        lambda *args, **kwargs: frozenset(stub.protected_disks),
    )
    return stub
