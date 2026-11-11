"""A disk behind a SAS HBA is found in the boot image's initrd (task queue item 48).

User report (#344, 2026-11-11): on the first BIOS PC one HDD sits behind an
LSI SAS1068E HBA.  The ISO's initrd has ``mptspi`` but not ``mptsas``, so the
driver loaded only in stage 2 (54.9 s) and the disk appeared at 67.8 s, after
mdadm's 30 s last-resort timer had started that disk's array degraded.  The
installed system, whose initrd has ``mptsas``, found it at about 15 s.

The machine is ``hba_scsi_disks``: an SSD on virtio-scsi and an HDD behind
QEMU's ``mptsas1068`` (the same LSI SAS1068 chip).  The HDD must be attached
before the initrd switches to the real root, and visible to the system.
"""

from __future__ import annotations

import re
from typing import List, Optional

import pytest

from tests.vm.controller import BootImageVM

pytestmark = [pytest.mark.vm, pytest.mark.slow]

HBA_SERIAL = "hbahdd"
# The initrd's PID 1 logs one of these when it hands over to the real root.
SWITCH_ROOT_MARKERS = ("Switching root", "Starting Switch Root", "initrd-switch-root.service")
_STAMP = re.compile(r"^\[\s*(\d+\.\d+)\]")


def _stamp(line: str) -> Optional[float]:
    match = _STAMP.match(line)
    return float(match.group(1)) if match else None


def _first(lines: List[str], *needles: str) -> Optional[float]:
    for line in lines:
        if any(needle in line for needle in needles):
            stamp = _stamp(line)
            if stamp is not None:
                return stamp
    return None


# Evidence when the disk is missing: whether the driver is loaded, bound to
# the controller (QEMU's SAS1068 is PCI 1000:0054), and loadable at all.
DRIVER_DIAGNOSTICS = (
    "echo '--- lsmod'; lsmod | grep -iE 'mpt|scsi_transport_sas' || echo none;"
    " echo '--- controller'; for d in /sys/bus/pci/devices/*; do"
    " if grep -q v00001000d00000054 $d/modalias 2>/dev/null; then"
    " echo $d modalias=$(cat $d/modalias) driver=$(readlink $d/driver || echo none); fi; done;"
    " echo '--- modprobe -n -v mptsas'; modprobe -n -v mptsas 2>&1;"
    " echo '--- udev trigger'; systemctl status systemd-udev-trigger.service --no-pager 2>&1 | head -n 5;"
    " echo '--- kernel'; journalctl -b -k -o short-monotonic --no-pager | grep -iE 'mpt|fusion|scsi host' | head -n 20"
)


def test_hba_disk_is_found_in_the_initrd(boot_image_vm_with_hba_disk: BootImageVM) -> None:
    vm = boot_image_vm_with_hba_disk
    listing = vm.run_as_root_checked("lsblk -dnro NAME,SERIAL", timeout=120)
    names = [line.split()[0] for line in listing.splitlines() if line.split()[1:] == [HBA_SERIAL]]
    if len(names) != 1:
        diagnostics = vm.run_as_root(DRIVER_DIAGNOSTICS, timeout=120)
        pytest.fail(f"the HBA disk is not visible:\n{listing}\n{diagnostics}")
    (name,) = names

    journal = vm.run_as_root(
        "journalctl -b -o short-monotonic --no-pager"
        f" | grep -E 'Switching root|Switch Root|initrd-switch-root|mptsas|Fusion MPT|\\[{name}\\]'",
        timeout=120,
    )
    lines = [line.strip() for line in journal.splitlines()]
    switch = _first(lines, *SWITCH_ROOT_MARKERS)
    attached = _first(lines, f"[{name}] Attached SCSI disk")
    assert switch is not None, f"no switch-root marker in the journal:\n{journal}"
    assert attached is not None, f"no attach line for {name}:\n{journal}"
    assert attached < switch, (
        f"the HBA disk {name} was attached at {attached} s, after the switch to the real root"
        f" at {switch} s: its driver is not in the initrd\n{journal}"
    )
