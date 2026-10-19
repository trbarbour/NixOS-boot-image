"""SCSI disks whose rotational flag the guest reports as chosen.

QEMU virtio-blk disks always appear rotational in the guest (``rotational=1``,
RAID spike 2026-10-19), so they cannot model an SSD.  ``scsi-hd`` takes a
``rotation_rate``: 1 means "non-rotating medium" (guest: ``rotational=0``) and
7200 a spinning disk (``rotational=1``); both verified in that spike
(notes/2026-10-19T003559Z-raid-spike.md).  Disks attach to one virtio-scsi
controller in list order (``scsi-id`` = index), so the guest names them
``/dev/sda``, ``/dev/sdb``, … in that order.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import List, Sequence

SSD_ROTATION_RATE = 1
HDD_ROTATION_RATE = 7200
CONTROLLER_ID = "scsi0"


@dataclass(frozen=True)
class ScsiDisk:
    path: Path
    rotational: bool
    serial: str

    def __post_init__(self) -> None:
        assert self.serial and self.serial.isalnum(), self.serial


def scsi_disk_args(disks: Sequence[ScsiDisk]) -> List[str]:
    """QEMU arguments attaching ``disks`` to one virtio-scsi controller."""

    if not disks:
        return []
    args = ["-device", f"virtio-scsi-pci,id={CONTROLLER_ID}"]
    for index, disk in enumerate(disks):
        rate = HDD_ROTATION_RATE if disk.rotational else SSD_ROTATION_RATE
        drive = f"scsidisk{index}"
        args += [
            "-drive",
            f"file={disk.path},if=none,id={drive},format=raw",
            "-device",
            f"scsi-hd,bus={CONTROLLER_ID}.0,drive={drive},rotation_rate={rate},"
            f"serial={disk.serial},scsi-id={index}",
        ]
    return args


__all__ = ["HDD_ROTATION_RATE", "SSD_ROTATION_RATE", "ScsiDisk", "scsi_disk_args"]
