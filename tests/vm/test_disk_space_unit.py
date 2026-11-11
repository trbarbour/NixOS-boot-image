"""Disk-space handling of the VM harness (task queue items 37 and 38).

Item 38: test ISOs and VM disk images filled the session's disk allowance
again and again (runs lost on 2026-10-18, 10-19, 11-07, 11-08 and 11-10).
``df``'s Avail is the real limit (experiment 2026-11-11: a ``fallocate`` just
over it fails with ENOSPC, just under it succeeds), so the harness measures
free space with ``statvfs`` (``shutil.disk_usage``) and:

* deletes this repository's older, unreferenced image store paths after a build;
* refuses to start a VM below a minimum, with a message saying what to free;
* stops a running VM below a floor, so the test fails with the reason instead
  of an ENOSPC halfway through an install.

Item 37: a failed ``nix build`` reported only ``CalledProcessError``; the
failure must carry the tail of Nix's stderr.
"""

from __future__ import annotations

import os
import stat
import subprocess
import threading
import time
from pathlib import Path
from typing import List

import pytest

from tests.vm import disk_space
from tests.vm.disk_space import FreeSpaceGuard, InsufficientSpace

GIB = 1024**3
STORE = Path("/nix/store")
ISO = "2pldvmh9gf2kmj5gb23ps25q5k2xpwmw-pre-nixos-0.29.0-20261111032737-s0e7468e5-26.05.20261031.fa13731-x86_64-linux.iso"
OLD_ISO = "a9vwgnyn59nx3hb02nq01pq61zgsj2hq-pre-nixos-0.28.1-g02a93f5-26.05.20261031.fa13731-x86_64-linux.iso"
SD = "0k3ylmzyfz9mlm1xqgc4yh0p7m5cxnls-pre-nixos-0.27.1-gb2c3ec0-sd-card-26.05.20261031.fa13731-aarch64-linux.img.zst"
NOT_IMAGES = [
    "kp6p38x6zb21n7gdlnp9nsm2aagq7sg2-pre-nixos-0.29.0",  # the Python package
    "gdmr38pqgy421j9f5vaviqf0g090wjmw-pre-nixos-0.29.0.drv",
    "hvj7nvy7jnljkq0m2v1592pgc1af607k-no-degraded-md-start.drv",
    "xz24bm2725bh2alz510gqxa9lbjxasqb-qemu-10.2.4",
    "y06739hhpsa67vkk2qw512grxkcbk3wh-other-x86_64-linux.iso",
]


def test_stale_images_are_the_other_pre_nixos_images() -> None:
    names = [ISO, OLD_ISO, SD, *NOT_IMAGES]
    assert disk_space.stale_image_paths(names, keep=STORE / ISO, store=STORE) == [
        STORE / OLD_ISO,
        STORE / SD,
    ]


def test_delete_stale_images_tolerates_live_paths() -> None:
    calls: List[List[str]] = []

    def runner(cmd: List[str]) -> subprocess.CompletedProcess[str]:
        calls.append(cmd)
        live = str(STORE / SD) in cmd
        return subprocess.CompletedProcess(cmd, 1 if live else 0, "", "still alive" if live else "")

    deleted = disk_space.delete_stale_images(
        "nix-store", keep=STORE / ISO, names=[ISO, OLD_ISO, SD], store=STORE, run=runner
    )
    assert deleted == [STORE / OLD_ISO]
    assert calls == [
        ["nix-store", "--delete", str(STORE / OLD_ISO)],
        ["nix-store", "--delete", str(STORE / SD)],
    ]


def test_require_free_space(tmp_path: Path) -> None:
    disk_space.require_free_space(tmp_path, minimum_bytes=0, purpose="test", free=lambda p: 5 * GIB)
    with pytest.raises(InsufficientSpace) as info:
        disk_space.require_free_space(
            tmp_path, minimum_bytes=4 * GIB, purpose="starting a VM", free=lambda p: 3 * GIB
        )
    message = str(info.value)
    assert "starting a VM" in message and "3.0 GiB" in message and "4.0 GiB" in message
    assert "nix-store --gc" in message


def test_guard_calls_once_below_the_floor() -> None:
    readings = iter([5 * GIB, 2 * GIB, 0.5 * GIB, 0.4 * GIB] + [0.4 * GIB] * 100)
    lows: List[int] = []
    fired = threading.Event()

    def on_low(free: int) -> None:
        lows.append(free)
        fired.set()

    guard = FreeSpaceGuard(
        Path("/"), floor_bytes=GIB, poll_seconds=0.01, on_low=on_low, free=lambda p: int(next(readings))
    )
    guard.start()
    assert fired.wait(5)
    time.sleep(0.05)
    guard.stop()
    assert lows == [int(0.5 * GIB)]
    assert guard.tripped


def test_guard_stays_quiet_above_the_floor() -> None:
    guard = FreeSpaceGuard(
        Path("/"), floor_bytes=GIB, poll_seconds=0.01, on_low=lambda free: pytest.fail("low"),
        free=lambda p: 5 * GIB,
    )
    guard.start()
    time.sleep(0.05)
    guard.stop()
    assert not guard.tripped


def test_thresholds_from_the_environment(monkeypatch) -> None:
    monkeypatch.delenv("PRE_NIXOS_VM_MIN_FREE_GIB", raising=False)
    assert disk_space.min_free_bytes() == int(disk_space.DEFAULT_MIN_FREE_GIB * GIB)
    monkeypatch.setenv("PRE_NIXOS_VM_MIN_FREE_GIB", "2.5")
    assert disk_space.min_free_bytes() == int(2.5 * GIB)
    monkeypatch.setenv("PRE_NIXOS_VM_MIN_FREE_GIB", "lots")
    with pytest.raises(ValueError):
        disk_space.min_free_bytes()


def test_failure_message_leads_with_the_abort_reason() -> None:
    from tests.vm.controller import with_abort_reason

    assert with_abort_reason("Unexpected EOF", None) == "Unexpected EOF"
    message = with_abort_reason("Unexpected EOF", "the disk allowance ran low (0.8 GiB free)")
    assert message.splitlines() == [
        "VM stopped by the harness: the disk allowance ran low (0.8 GiB free)",
        "Unexpected EOF",
    ]


# --- Codex on #349 ----------------------------------------------------------


def test_every_image_held_by_the_session_is_kept() -> None:
    """Finding 1: the session-scoped x86 and AArch64 builds are not GC roots
    (--no-link), so cleaning after one build must keep the other's image."""

    calls: List[List[str]] = []

    def runner(cmd: List[str]) -> subprocess.CompletedProcess[str]:
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, "", "")

    deleted = disk_space.delete_stale_images(
        "nix-store", keep={STORE / ISO, STORE / SD}, names=[ISO, OLD_ISO, SD], store=STORE, run=runner
    )
    assert deleted == [STORE / OLD_ISO]
    assert calls == [["nix-store", "--delete", str(STORE / OLD_ISO)]]


def test_fixture_registers_each_build_before_cleaning(monkeypatch, tmp_path: Path) -> None:
    from tests.vm import fixtures

    kept: List[frozenset] = []
    monkeypatch.delenv(disk_space.KEEP_IMAGES_ENV, raising=False)
    monkeypatch.setattr(fixtures, "_SESSION_IMAGES", set())
    monkeypatch.setattr(
        disk_space, "delete_stale_images", lambda nix_store, *, keep, **kw: kept.append(frozenset(keep)) or []
    )
    fixtures._delete_stale_images("nix", keep=STORE / ISO)
    fixtures._delete_stale_images("nix", keep=STORE / SD)
    assert kept == [frozenset({STORE / ISO}), frozenset({STORE / ISO, STORE / SD})]


def test_guard_watches_the_fullest_filesystem() -> None:
    """Finding 2: VM disks may live on another filesystem than the logs."""

    free = {Path("/logs"): 50 * GIB, Path("/tmp/disks"): int(0.5 * GIB)}
    fired = threading.Event()
    guard = FreeSpaceGuard(
        [Path("/logs"), Path("/tmp/disks")], floor_bytes=GIB, poll_seconds=0.01,
        on_low=lambda available: fired.set(), free=lambda p: free[p],
    )
    guard.start()
    assert fired.wait(5)
    guard.stop()


def test_require_free_space_checks_every_filesystem(tmp_path: Path) -> None:
    free = {Path("/logs"): 50 * GIB, Path("/tmp/disks"): 2 * GIB}
    with pytest.raises(InsufficientSpace) as info:
        disk_space.require_free_space(
            [Path("/logs"), Path("/tmp/disks")], minimum_bytes=4 * GIB, purpose="starting a VM",
            free=lambda p: free[p],
        )
    assert "/tmp/disks" in str(info.value)


def test_low_space_handler_stops_qemu_even_if_logging_fails() -> None:
    """Finding 3: an ENOSPC while logging must not stop the termination."""

    from tests.vm.fixtures import _low_space_handler

    class Child:
        terminated = False

        def terminate(self, force: bool = False) -> bool:
            Child.terminated = True
            return True

    class Vm:
        abort_reason = None

    def log(message: str) -> None:
        raise OSError(28, "No space left on device")

    vm = Vm()
    handler = _low_space_handler(vm, Child(), log)
    handler(int(0.5 * GIB))
    assert Child.terminated
    assert vm.abort_reason and "ran low" in vm.abort_reason
