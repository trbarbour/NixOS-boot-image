"""Boot from a writable USB stick: it is protected and does not block provisioning.

Regression for trbarbour/NixOS-boot-image#306 and #309; requirement
automated-pre-nixos-reqs.md §2.3 (the boot medium is never planned, wiped or
provisioned, and does not count as existing storage).  Before 0.10.8 the
boot-time gate ``pre-nixos-detect-storage`` resolved the stick as
``/dev/dev/sda`` and counted its ISO partitions as existing storage, so the
empty target was left unprovisioned (spike notes/2026-10-18T190817Z-usb-stick-spike.md).
"""

from __future__ import annotations

import pytest

from tests.vm.boot_medium import UsbStick, file_sha256
from tests.vm.controller import BootImageVM

pytestmark = [pytest.mark.vm, pytest.mark.slow]


def test_usb_stick_is_untouched_and_empty_target_is_provisioned(
    boot_image_vm_from_usb_stick: BootImageVM,
    usb_boot_stick: UsbStick,
) -> None:
    vm = boot_image_vm_from_usb_stick

    # The scenario is only meaningful if the guest sees an RM=0 USB disk
    # carrying the image (otherwise the RM=1 filter would hide it).
    stick_row = vm.run_as_root_checked("lsblk -dnro NAME,TRAN,RM /dev/sda", timeout=120)
    assert stick_row.split() == ["sda", "usb", "0"], stick_row
    iso_source = vm.run_as_root_checked("findmnt -n -o SOURCE /iso", timeout=120)
    assert iso_source.strip() == "/dev/sda1", iso_source

    status = vm.wait_for_storage_status()
    if status.get("STATE") != "applied" or status.get("DETAIL") != "auto-applied":
        journal = vm.collect_journal("pre-nixos.service")
        pytest.fail(
            "the boot stick blocked auto-provisioning of the empty target:\n"
            f"status={status}\njournalctl -u pre-nixos.service:\n{journal}"
        )
    pv_names = vm.run_as_root_checked("pvs --noheadings -o pv_name", timeout=120)
    assert pv_names.split(), "no physical volume was created on the target"
    assert not any(pv.startswith("/dev/sda") for pv in pv_names.split()), pv_names

    vm.shutdown()
    assert file_sha256(usb_boot_stick.path) == usb_boot_stick.sha256_before
