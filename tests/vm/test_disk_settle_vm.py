"""The boot-time plan includes a disk that appears after the service starts
(task queue item 50, R-D1).

Design: plans/2026-11-11T194943Z-disk-settle-design.md.

The second disk is hot-plugged 5 s after the service says it is waiting for
the disks, inside the 15 s quiet period.  Before item 50 the service planned
at once, so the plan had only the primary disk; now the wait sees the new
disk, restarts its quiet period, and the plan (applied, since both disks are
blank) is for both.
"""

from __future__ import annotations

import json

import pytest

from tests.vm.controller import BootImageVM
from tests.vm.fixtures import LATE_DISK_BYTES, LATE_DISK_SERIAL
from tests.vm.late_disk import LateDiskPlugger

pytestmark = [pytest.mark.vm, pytest.mark.slow]


def test_the_boot_plan_waits_for_a_late_disk(
    boot_image_vm_with_late_disk: tuple[BootImageVM, LateDiskPlugger],
) -> None:
    vm, plugger = boot_image_vm_with_late_disk
    status = vm.wait_for_storage_status()
    plugger.check()

    journal = vm.collect_journal("pre-nixos.service")
    # Item 53: a virtio disk's serial is in /sys/block/<d>/serial; before,
    # this logged "no serial".
    assert "pre-nixos: disk change: added vd" in journal, journal
    assert f"(6 GiB, serial {LATE_DISK_SERIAL})" in journal, journal
    assert "pre-nixos: disks settled after" in journal, journal

    plan = json.loads(vm.run_as_root_checked("cat /run/pre-nixos/storage-plan.json", timeout=60))
    sizes = sorted(entry["size"] for entry in plan["inventory"])
    assert len(sizes) == 2 and LATE_DISK_BYTES in sizes, plan["inventory"]
    assert LATE_DISK_SERIAL in [entry["serial"] for entry in plan["inventory"]], plan["inventory"]
    assert status.get("STATE") == "applied", status
