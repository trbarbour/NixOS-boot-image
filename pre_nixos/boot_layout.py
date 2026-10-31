"""Which disks get the boot partitions, and which boot partitions (R-B1, R-B4).

Design: plans/2026-10-31T010024Z-x86-bios-support-plan.md (D2, D6).
"""

from __future__ import annotations

import enum
from typing import List, Optional, Sequence, Tuple

from .inventory import Disk

# GRUB's core image on a GPT disk under legacy BIOS (GPT type EF02).
BIOS_BOOT_PARTITION_SIZE = "1M"


class BootLayout(enum.Enum):
    """The boot partitions a plan creates, and where."""

    # ESP on the main disks (the Raspberry Pi: its EEPROM finds the ESP by type).
    ESP = "esp"
    # ESP and a BIOS boot partition on the main disks (x86 booted with UEFI):
    # the disk also boots if moved to a BIOS machine (D2).
    X86_UEFI = "x86-uefi"
    # ESP and a BIOS boot partition on the first disk set the BIOS can boot
    # (x86 booted in legacy BIOS mode); old BIOSes cannot boot NVMe (D6).
    X86_BIOS = "x86-bios"

    @property
    def has_bios_boot_partition(self) -> bool:
        return self is not BootLayout.ESP


def _bios_bootable(bucket: Sequence[Disk]) -> bool:
    return bool(bucket) and not any(disk.nvme for disk in bucket)


def _preference(vg_name: str) -> Tuple[int, str]:
    """D6 order: main, the other SSD groups, swap (the user's habit), large."""

    if vg_name == "main":
        return (0, vg_name)
    if vg_name.startswith("main_"):
        return (1, vg_name)
    if vg_name == "swap":
        return (2, vg_name)
    return (3, vg_name)


def choose_boot_disks(
    roles: Sequence[Tuple[str, List[Disk]]], layout: BootLayout
) -> Optional[List[Disk]]:
    """The disk set (one plan bucket) that gets the boot partitions.

    ``roles`` pairs each bucket with the volume group it becomes.  Under UEFI
    (and on the Pi) that is the ``main`` bucket.  Under legacy BIOS it is the
    first BIOS-bootable bucket in D6 order, or ``None`` when there is none;
    the install is then refused (R-B4).
    """

    if layout is not BootLayout.X86_BIOS:
        return next((bucket for name, bucket in roles if name == "main"), None)
    for _name, bucket in sorted(roles, key=lambda role: _preference(role[0])):
        if _bios_bootable(bucket):
            return bucket
    return None
