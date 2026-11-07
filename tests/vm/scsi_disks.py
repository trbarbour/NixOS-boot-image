"""SCSI disks whose rotational flag the guest reports as chosen.

QEMU virtio-blk disks always appear rotational in the guest (``rotational=1``,
RAID spike 2026-10-19), so they cannot model an SSD.  ``scsi-hd`` takes a
``rotation_rate``: 1 means "non-rotating medium" (guest: ``rotational=0``) and
7200 a spinning disk (``rotational=1``); both verified in that spike
(notes/2026-10-19T003559Z-raid-spike.md).  0 means "not reported": the guest
kernel then defaults to ``rotational=1``, like an SSD that reports no rate
(``rotational=None``; task queue item 34, notes/2026-11-07T165520Z-u1-scsi-unreported-rotation.md).
``product`` sets the model name the guest sees (``device/model``).  Disks attach to one virtio-scsi
controller in list order (``scsi-id`` = index).  The guest does **not**
reliably name them ``/dev/sda``, ``/dev/sdb``, … in that order: names follow
probe completion (2026-11-07, notes/2026-11-07T171600Z-vm-run: target 0 became
``sdb``).  Identify a disk by its model or serial.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Sequence

SSD_ROTATION_RATE = 1
HDD_ROTATION_RATE = 7200
UNREPORTED_ROTATION_RATE = 0
# SCSI INQUIRY product identification: 16 bytes.
MAX_PRODUCT_LENGTH = 16
CONTROLLER_ID = "scsi0"


@dataclass(frozen=True)
class ScsiDisk:
    path: Path
    # ``None``: the disk reports no rotation rate.
    rotational: Optional[bool]
    serial: str
    product: str = ""

    def __post_init__(self) -> None:
        assert self.serial and self.serial.isalnum(), self.serial
        # A comma would end QEMU's option value.
        assert len(self.product) <= MAX_PRODUCT_LENGTH and "," not in self.product, self.product

    @property
    def rotation_rate(self) -> int:
        if self.rotational is None:
            return UNREPORTED_ROTATION_RATE
        return HDD_ROTATION_RATE if self.rotational else SSD_ROTATION_RATE


def scsi_disk_args(disks: Sequence[ScsiDisk]) -> List[str]:
    """QEMU arguments attaching ``disks`` to one virtio-scsi controller."""

    if not disks:
        return []
    args = ["-device", f"virtio-scsi-pci,id={CONTROLLER_ID}"]
    for index, disk in enumerate(disks):
        drive = f"scsidisk{index}"
        product = f"product={disk.product}," if disk.product else ""
        args += [
            "-drive",
            f"file={disk.path},if=none,id={drive},format=raw",
            "-device",
            f"scsi-hd,bus={CONTROLLER_ID}.0,drive={drive},rotation_rate={disk.rotation_rate},"
            f"{product}serial={disk.serial},scsi-id={index}",
        ]
    return args


__all__ = [
    "HDD_ROTATION_RATE",
    "SSD_ROTATION_RATE",
    "UNREPORTED_ROTATION_RATE",
    "ScsiDisk",
    "scsi_disk_args",
]
