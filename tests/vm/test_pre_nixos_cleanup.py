"""RAID/LVM residue regression scenario."""

from __future__ import annotations

from pathlib import Path
from typing import List

import pytest

from tests.vm.cleanup_plan import build_raid_residue_plan
from tests.vm.controller import BootImageVM

pytestmark = [pytest.mark.vm, pytest.mark.slow]

# The residue plan's commands name these devices, so the hot-plugged disks
# must arrive as exactly these (checked below, not assumed).
RESIDUE_DISKS = (("residue-a", "/dev/vdb"), ("residue-b", "/dev/vdc"))


def test_pre_nixos_cleans_raid_lvm_residue(
    boot_image_vm_for_hotplug: BootImageVM,
    vm_additional_disks: List[Path],
) -> None:
    vm = boot_image_vm_for_hotplug
    plan = build_raid_residue_plan()
    vm.assert_commands_available("mdadm", "pvcreate", "vgcreate", "lvcreate", "blkid")

    # The boot-time pre-nixos run provisions every disk it can see; seeding
    # residue while it runs lets it destroy the residue, and disks it has
    # provisioned are busy afterwards (both seen 2026-10-18). So let it finish
    # with only the primary disk, then attach fresh disks for the residue.
    vm.wait_for_unit_inactive("pre-nixos", timeout=600)
    assert len(vm_additional_disks) >= len(RESIDUE_DISKS)
    for (serial, expected_device), image in zip(RESIDUE_DISKS, vm_additional_disks):
        device = vm.hotplug_disk(image, serial=serial)
        assert device == expected_device, (serial, device)

    for command in plan.preseed_commands:
        vm.run_as_root_checked(command, timeout=300)

    device_listing = vm.run_as_root_checked(
        "ls -l /dev/vd[abc] /dev/md127 /dev/vg_residue || true", timeout=180
    )
    assert "/dev/vdb" in device_listing
    assert "/dev/vdc" in device_listing

    sentinel_content = vm.run_as_root_checked(
        (
            f"dd if={plan.sentinel_path} bs=1 count=64 status=none 2>/dev/null "
            "| hexdump -C"
        ),
        timeout=180,
    )
    assert "residue-marker" in sentinel_content

    vm.run_as_root_checked(
        "systemctl set-environment PRE_NIXOS_FORCE_CLEANUP=1", timeout=180
    )
    vm.run_as_root("systemctl restart pre-nixos.service", timeout=240)
    vm.wait_for_unit_inactive("pre-nixos", timeout=600)

    verification_outputs = [
        vm.run_as_root(command, timeout=240) for command in plan.verification_commands
    ]
    combined_output = "\n".join(verification_outputs)

    assert "/dev/md127" not in combined_output
    assert "vg_residue" not in combined_output
    assert "lv_residue" not in combined_output

    sentinel_after_cleanup = vm.run_as_root(
        (
            f"if [ -e {plan.sentinel_path} ]; then "
            f"dd if={plan.sentinel_path} bs=1 count=64 status=none 2>/dev/null "
            "| hexdump -C; fi"
        ),
        timeout=180,
    )
    assert "residue-marker" not in sentinel_after_cleanup
