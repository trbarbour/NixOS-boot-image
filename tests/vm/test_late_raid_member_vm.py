"""The boot image never starts a RAID array degraded on its own (#344).

User report (2026-11-10): on the first BIOS PC, the installed system's HDD
mirror ran "active with 1 out of 2 mirrors".  One member sits behind an LSI
SAS1068E HBA whose driver is not in the boot image's initrd: in the installer
the disk appears only at 67.8 s.  mdadm's ``mdadm-last-resort@.timer`` (30 s)
then ran ``mdadm --run``, which started the array without it and marked it
missing in the other member's superblock, so the late member stayed out for
good, also on the installed system.

The machine is ``raid_scsi_disks`` (an SSD plus an HDD pair, which pre-nixos
mirrors at boot).  The test stops the mirror and unplugs one member, then lets
udev's incremental assembly see the other member alone, as the installer does
when the HBA disk is late.  After more than the timer's 30 s:

* the array must still be inactive (the image starts nothing degraded); and
* once the late member is plugged back, the array runs with both members.
"""

from __future__ import annotations

import re
import time
from typing import Dict, List

import pytest

from tests.vm.controller import BootImageVM
from tests.vm.qmp import QmpClient, plug_scsi_disk, unplug_device
from tests.vm.scsi_disks import ScsiDisk, scsi_device_id, scsi_hd_properties

pytestmark = [pytest.mark.vm, pytest.mark.slow]

# mdadm-last-resort@.timer: OnActiveSec=30 (nixpkgs mdadm 4.4).
LAST_RESORT_SECONDS = 30
MARGIN_SECONDS = 30
LATE_MEMBER_SERIAL = "hddb"


def _names_by_serial(vm: BootImageVM) -> Dict[str, str]:
    listing = vm.run_as_root_checked("lsblk -dnro NAME,SERIAL", timeout=120)
    return {serial: name for name, serial in (line.split() for line in listing.splitlines() if len(line.split()) == 2)}


def _mirror(mdstat: str) -> str:
    """The name of the RAID-1 array in /proc/mdstat (there is exactly one)."""

    (name,) = re.findall(r"^(md\S+) : .*raid1", mdstat, flags=re.MULTILINE)
    return name


def _array_with(mdstat: str, member: str) -> str:
    """The /proc/mdstat line of the array holding partition ``member``.

    Found by member, not by name: the array the image provisions is ``md127``,
    and incremental reassembly names it ``md0`` (first run, 2026-11-11).
    """

    lines: List[str] = [
        line for line in mdstat.splitlines()
        if line.startswith("md") and re.search(rf"\b{re.escape(member)}\[", line)
    ]
    assert len(lines) <= 1, mdstat
    return lines[0] if lines else ""


def test_late_member_does_not_degrade_the_mirror(
    boot_image_vm_with_raid_disks: BootImageVM, raid_scsi_disks: List[ScsiDisk]
) -> None:
    vm = boot_image_vm_with_raid_disks
    status = vm.wait_for_storage_status()
    assert status.get("STATE") == "applied", status

    names = _names_by_serial(vm)
    early, late = names["hdda"], names[LATE_MEMBER_SERIAL]
    mdstat = vm.run_as_root_checked("cat /proc/mdstat", timeout=60)
    md = _mirror(mdstat)
    assert f"{early}1" in mdstat and f"{late}1" in mdstat, mdstat

    # Release the mirror: swap and the VGs on it, then the array itself.
    vm.run_as_root(
        "swapoff -a; umount -R /mnt 2>/dev/null; vgchange -an >/dev/null; "
        f"mdadm --stop /dev/{md}",
        timeout=300,
    )
    assert md not in vm.run_as_root_checked("cat /proc/mdstat", timeout=60)

    # The late member disappears, as the HBA disk is absent at first.
    (index,) = [i for i, disk in enumerate(raid_scsi_disks) if disk.serial == LATE_MEMBER_SERIAL]
    assert vm.qmp_socket is not None
    with QmpClient(vm.qmp_socket) as client:
        unplug_device(client, scsi_device_id(index))
    deadline = time.monotonic() + 120
    while LATE_MEMBER_SERIAL in _names_by_serial(vm):
        assert time.monotonic() < deadline, "the late member was not unplugged"
        time.sleep(2)

    # udev's incremental assembly sees the early member alone, as at boot.
    vm.run_as_root_checked(
        f"udevadm trigger --action=add /sys/class/block/{early}1 && udevadm settle", timeout=120
    )
    time.sleep(LAST_RESORT_SECONDS + MARGIN_SECONDS)
    waited = vm.run_as_root_checked("cat /proc/mdstat", timeout=60)
    journal = vm.run_as_root("journalctl -b --no-pager | grep -i 'last-resort\\|degraded' | tail -n 20", timeout=60)
    line = _array_with(waited, f"{early}1")
    assert line and "inactive" in line and "active raid1" not in line, (
        f"the boot image started the mirror without its late member:\n{waited}\n{journal}"
    )

    # The late member arrives: incremental assembly completes the mirror.
    late_disk = raid_scsi_disks[index]
    with QmpClient(vm.qmp_socket) as client:
        plug_scsi_disk(
            client,
            image=late_disk.path,
            node_name=f"late-{LATE_MEMBER_SERIAL}",
            properties=scsi_hd_properties(late_disk, index=index, drive="unused"),
        )
    deadline = time.monotonic() + 180
    while True:
        mdstat = vm.run_as_root_checked("udevadm settle; cat /proc/mdstat", timeout=120)
        line = _array_with(mdstat, f"{early}1")
        if "active raid1" in line and line.count("[") >= 2:
            break
        assert time.monotonic() < deadline, f"the mirror did not assemble with both members:\n{mdstat}"
        time.sleep(5)
    assembled = line.split()[0]
    detail = vm.run_as_root_checked(f"mdadm --detail /dev/{assembled}", timeout=60)
    assert re.search(r"Active Devices : 2", detail), detail
    assert "removed" not in detail, detail
