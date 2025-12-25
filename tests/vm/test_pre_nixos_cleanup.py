"""RAID/LVM residue regression scenario."""

from __future__ import annotations

import pytest

from tests.vm.cleanup_plan import build_raid_residue_plan
from tests.vm.controller import BootImageVM

pytestmark = [pytest.mark.vm, pytest.mark.slow]


def test_pre_nixos_cleans_raid_lvm_residue(
    boot_image_vm_with_additional_disks: BootImageVM,
) -> None:
    plan = build_raid_residue_plan()
    boot_image_vm_with_additional_disks.assert_commands_available(
        "mdadm", "pvcreate", "vgcreate", "lvcreate", "blkid"
    )

    for command in plan.preseed_commands:
        boot_image_vm_with_additional_disks.run_as_root_checked(
            command, timeout=300
        )

    device_listing = boot_image_vm_with_additional_disks.run_as_root_checked(
        "ls -l /dev/vd[abc] /dev/md127 /dev/vg_residue || true", timeout=180
    )
    assert "/dev/vdb" in device_listing
    assert "/dev/vdc" in device_listing

    sentinel_content = boot_image_vm_with_additional_disks.run_as_root_checked(
        (
            f"dd if={plan.sentinel_path} bs=1 count=64 status=none 2>/dev/null "
            "| hexdump -C"
        ),
        timeout=180,
    )
    assert "residue-marker" in sentinel_content

    boot_image_vm_with_additional_disks.run_as_root(
        "systemctl restart pre-nixos.service", timeout=240
    )
    boot_image_vm_with_additional_disks.wait_for_unit_inactive(
        "pre-nixos", timeout=240
    )

    verification_outputs = [
        boot_image_vm_with_additional_disks.run_as_root(command, timeout=240)
        for command in plan.verification_commands
    ]
    combined_output = "\n".join(verification_outputs)

    assert "/dev/md127" not in combined_output
    assert "vg_residue" not in combined_output
    assert "lv_residue" not in combined_output

    sentinel_after_cleanup = boot_image_vm_with_additional_disks.run_as_root(
        (
            f"if [ -e {plan.sentinel_path} ]; then "
            f"dd if={plan.sentinel_path} bs=1 count=64 status=none 2>/dev/null "
            "| hexdump -C; fi"
        ),
        timeout=180,
    )
    assert "residue-marker" not in sentinel_after_cleanup
