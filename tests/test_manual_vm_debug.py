"""Unit tests for scripts/manual_vm_debug.py resource handling."""
from __future__ import annotations

from pathlib import Path
from typing import Any, List

import pytest

from scripts import manual_vm_debug as mvd
from tests.vm.fixtures import BootImageBuild


class FakeChild:
    def __init__(self) -> None:
        self.logfile: Any = None
        self.close_calls: List[bool] = []

    def close(self, force: bool = False) -> None:
        self.close_calls.append(force)


class LoginFailed(Exception):
    pass


def test_launch_vm_releases_qemu_and_serial_log_when_login_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A failure inside BootImageVM (e.g. login) must not leak QEMU or the log."""

    child = FakeChild()
    monkeypatch.setattr(mvd, "require_executable", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(mvd, "probe_qemu_version", lambda qemu: "QEMU 0.0")
    monkeypatch.setattr(mvd, "write_boot_image_metadata", lambda *args, **kwargs: None)
    monkeypatch.setattr(mvd.pexpect, "spawn", lambda *args, **kwargs: child)

    def failing_vm(**kwargs: Any) -> None:
        raise LoginFailed("login timed out")

    monkeypatch.setattr(mvd, "BootImageVM", failing_vm)

    artifact = BootImageBuild(
        iso_path=tmp_path / "boot.iso",
        store_path=tmp_path,
        deriver=None,
        nar_hash=None,
        root_key_fingerprint="test",
    )
    with pytest.raises(LoginFailed):
        mvd.launch_vm(
            artifact=artifact,
            disk_image=tmp_path / "disk.img",
            ssh_port=2222,
            harness_log=tmp_path / "harness.log",
            serial_log=tmp_path / "serial.log",
            metadata_path=tmp_path / "metadata.json",
        )

    assert child.close_calls == [True]
    assert child.logfile is not None and child.logfile.closed
