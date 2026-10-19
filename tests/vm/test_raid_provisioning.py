"""Boot-time provisioning of a RAID-1 group through disko (reqs §2.2).

Task-queue item 11: mdadm 4.4 (nixpkgs 26.05) asks whether to add a
write-intent bitmap, and disko answers mdadm with ``echo 'y'``.  Until this
test, no VM test provisioned more than one disk.  Machine: an SSD plus an
equal pair of HDDs (``raid_scsi_disks``), for which the planner puts ``main``
on the SSD and mirrors the pair for the ``swap`` VG.  Spike:
notes/2026-10-19T003559Z-raid-spike.md.
"""

from __future__ import annotations

import pytest

from tests.vm.controller import BootImageVM

pytestmark = [pytest.mark.vm, pytest.mark.slow]


def _pairs(output: str) -> set[tuple[str, ...]]:
    return {tuple(line.split()) for line in output.splitlines() if line.strip()}


def test_ssd_plus_hdd_pair_is_provisioned_with_raid1(
    boot_image_vm_with_raid_disks: BootImageVM,
) -> None:
    vm = boot_image_vm_with_raid_disks

    # The scenario only means something if the guest classifies the disks as intended.
    rotation = vm.run_as_root_checked("lsblk -dnro NAME,ROTA /dev/sda /dev/sdb /dev/sdc", timeout=120)
    assert _pairs(rotation) == {("sda", "0"), ("sdb", "1"), ("sdc", "1")}, rotation

    status = vm.wait_for_storage_status()
    if status.get("STATE") != "applied" or status.get("DETAIL") != "auto-applied":
        pytest.fail(
            "pre-nixos did not auto-apply the RAID plan:\n"
            f"status={status}\n{vm.collect_journal('pre-nixos.service')}"
        )

    mdstat = vm.run_as_root_checked("cat /proc/mdstat", timeout=120)
    assert "active raid1" in mdstat and "sdb1" in mdstat and "sdc1" in mdstat, mdstat
    assert "[UU]" in mdstat, mdstat

    pvs = _pairs(vm.run_as_root_checked("pvs --noheadings -o pv_name,vg_name", timeout=120))
    assert ("/dev/sda2", "main") in pvs, pvs
    assert any(vg == "swap" and pv.startswith("/dev/md") for pv, vg in pvs), pvs
    lvs = _pairs(vm.run_as_root_checked("lvs --noheadings -o lv_name,vg_name", timeout=120))
    assert {("slash", "main"), ("swap", "swap")} <= lvs, lvs

    # Recorded, not asserted, until the bitmap policy is decided (queue item 11, U4).
    detail = vm.run_as_root("mdadm --detail /dev/md/md0 | grep -E 'Intent Bitmap|State :'", timeout=120)
    print(f"mdadm --detail /dev/md/md0:\n{detail}")
