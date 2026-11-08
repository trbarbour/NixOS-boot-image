"""SCSI disks whose rotational flag the guest reports as chosen.

QEMU virtio-blk disks always appear rotational in the guest (``rotational=1``,
RAID spike 2026-10-19), so they cannot model an SSD.  ``scsi-hd`` takes a
``rotation_rate``: 1 means "non-rotating medium" (guest: ``rotational=0``) and
7200 a spinning disk (``rotational=1``); both verified in that spike
(notes/2026-10-19T003559Z-raid-spike.md).  0 means "not reported": the guest
kernel then defaults to ``rotational=1``, like an SSD that reports no rate
(``rotational=None``; task queue item 34, notes/2026-11-07T165520Z-u1-scsi-unreported-rotation.md).
``model`` sets the model name the guest sees.

``Bus.SATA`` disks attach instead to an ``ich9-ahci`` controller as ``ide-hd``,
whose ``model`` takes up to 40 characters: the guest's libata truncates
``device/model`` to 16, as on real SATA disks, and keeps the full name in
``device/vpd_pg89`` (#336, notes/2026-11-08T003000Z-u2-sata-model-truncation.md).
``ide-hd`` takes the same ``rotation_rate`` values.  Disks attach to one virtio-scsi
controller in list order (``scsi-id`` = index).  The guest does **not**
reliably name them ``/dev/sda``, ``/dev/sdb``, … in that order: names follow
probe completion (2026-11-07, notes/2026-11-07T171600Z-vm-run: target 0 became
``sdb``).  Identify a disk by its model or serial.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Sequence

SSD_ROTATION_RATE = 1
HDD_ROTATION_RATE = 7200
UNREPORTED_ROTATION_RATE = 0
SATA_CONTROLLER_ID = "ahci0"
# ich9-ahci has six ports.
SATA_PORTS = 6


class Bus(enum.Enum):
    SCSI = "scsi"
    SATA = "sata"

    @property
    def max_model_length(self) -> int:
        # SCSI INQUIRY product identification: 16 bytes; ATA model: 40.
        return 16 if self is Bus.SCSI else 40
CONTROLLER_ID = "scsi0"


@dataclass(frozen=True)
class ScsiDisk:
    path: Path
    # ``None``: the disk reports no rotation rate.
    rotational: Optional[bool]
    serial: str
    model: str = ""
    bus: Bus = Bus.SCSI

    def __post_init__(self) -> None:
        assert self.serial and self.serial.isalnum(), self.serial
        # A comma would end QEMU's option value.
        assert len(self.model) <= self.bus.max_model_length and "," not in self.model, self.model

    @property
    def rotation_rate(self) -> int:
        if self.rotational is None:
            return UNREPORTED_ROTATION_RATE
        return HDD_ROTATION_RATE if self.rotational else SSD_ROTATION_RATE


def scsi_disk_args(disks: Sequence[ScsiDisk]) -> List[str]:
    """QEMU arguments attaching ``disks``: SCSI ones to one virtio-scsi
    controller, SATA ones to one AHCI controller, each in list order."""

    args: List[str] = []
    scsi = [disk for disk in disks if disk.bus is Bus.SCSI]
    sata = [disk for disk in disks if disk.bus is Bus.SATA]
    assert len(sata) <= SATA_PORTS, len(sata)
    if scsi:
        args += ["-device", f"virtio-scsi-pci,id={CONTROLLER_ID}"]
    for index, disk in enumerate(scsi):
        drive = f"scsidisk{index}"
        product = f"product={disk.model}," if disk.model else ""
        args += [
            "-drive",
            f"file={disk.path},if=none,id={drive},format=raw",
            "-device",
            f"scsi-hd,bus={CONTROLLER_ID}.0,drive={drive},rotation_rate={disk.rotation_rate},"
            f"{product}serial={disk.serial},scsi-id={index}",
        ]
    if sata:
        args += ["-device", f"ich9-ahci,id={SATA_CONTROLLER_ID}"]
    for index, disk in enumerate(sata):
        drive = f"satadisk{index}"
        model = f"model={disk.model}," if disk.model else ""
        args += [
            "-drive",
            f"file={disk.path},if=none,id={drive},format=raw",
            "-device",
            f"ide-hd,bus={SATA_CONTROLLER_ID}.{index},drive={drive},rotation_rate={disk.rotation_rate},"
            f"{model}serial={disk.serial}",
        ]
    return args


__all__ = [
    "Bus",
    "HDD_ROTATION_RATE",
    "SSD_ROTATION_RATE",
    "UNREPORTED_ROTATION_RATE",
    "ScsiDisk",
    "scsi_disk_args",
]
