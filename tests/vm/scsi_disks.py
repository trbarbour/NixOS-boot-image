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
controller in list order (``scsi-id`` = index).  ``Bus.MPTSAS`` disks attach
the same way to one ``mptsas1068`` (LSI SAS1068) controller.  The guest does **not**
reliably name them ``/dev/sda``, ``/dev/sdb``, … in that order: names follow
probe completion (2026-11-07, notes/2026-11-07T171600Z-vm-run: target 0 became
``sdb``).  Identify a disk by its model or serial.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Union

SSD_ROTATION_RATE = 1
HDD_ROTATION_RATE = 7200
UNREPORTED_ROTATION_RATE = 0
SATA_CONTROLLER_ID = "ahci0"
MPTSAS_CONTROLLER_ID = "mptsas0"
# ich9-ahci has six ports.
SATA_PORTS = 6


class Bus(enum.Enum):
    SCSI = "scsi"
    SATA = "sata"
    # An LSI SAS1068 HBA (QEMU ``mptsas1068``, kernel ``mptsas``), the
    # controller of the user's late HDD (#344, task queue item 48).
    MPTSAS = "mptsas"

    @property
    def max_model_length(self) -> int:
        # SCSI INQUIRY product identification: 16 bytes; ATA model: 40.
        return 40 if self is Bus.SATA else 16
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


def sas_wwn(index: int) -> str:
    """A SAS address (NAA 5) for the ``index``-th disk on the ``mptsas1068``.

    Linux's mptsas discovers no disk that QEMU presents without one
    (experiment 2026-11-11, notes/2026-11-11T053000Z-mptsas-wwn-experiment.md).
    """

    assert 0 <= index < 0x10000, index
    return f"0x5000c5000000{index + 1:04x}"


def scsi_device_id(index: int) -> str:
    """The QEMU device id of the SCSI disk at ``index`` (for QMP ``device_del``)."""

    return f"scsihd{index}"


def scsi_hd_properties(disk: ScsiDisk, *, index: int, drive: str) -> Dict[str, Union[str, int]]:
    """``scsi-hd`` properties, shared by the command line and QMP hot-plug.

    The order is the command line's; ``id`` lets a test unplug the disk
    (#344: a RAID member that appears late).
    """

    assert disk.bus is Bus.SCSI, disk
    properties: Dict[str, Union[str, int]] = {
        "bus": f"{CONTROLLER_ID}.0",
        "drive": drive,
        "rotation_rate": disk.rotation_rate,
    }
    if disk.model:
        properties["product"] = disk.model
    properties.update({"serial": disk.serial, "scsi-id": index, "id": scsi_device_id(index)})
    return properties


def scsi_disk_args(disks: Sequence[ScsiDisk]) -> List[str]:
    """QEMU arguments attaching ``disks``: SCSI ones to one virtio-scsi
    controller, SATA ones to one AHCI controller, each in list order."""

    args: List[str] = []
    scsi = [disk for disk in disks if disk.bus is Bus.SCSI]
    sata = [disk for disk in disks if disk.bus is Bus.SATA]
    sas = [disk for disk in disks if disk.bus is Bus.MPTSAS]
    assert len(sata) <= SATA_PORTS, len(sata)
    if scsi:
        args += ["-device", f"virtio-scsi-pci,id={CONTROLLER_ID}"]
    for index, disk in enumerate(scsi):
        drive = f"scsidisk{index}"
        properties = scsi_hd_properties(disk, index=index, drive=drive)
        args += [
            "-drive",
            f"file={disk.path},if=none,id={drive},format=raw",
            "-device",
            "scsi-hd," + ",".join(f"{key}={value}" for key, value in properties.items()),
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
    if sas:
        args += ["-device", f"mptsas1068,id={MPTSAS_CONTROLLER_ID}"]
    for index, disk in enumerate(sas):
        drive = f"sasdisk{index}"
        product = f"product={disk.model}," if disk.model else ""
        args += [
            "-drive",
            f"file={disk.path},if=none,id={drive},format=raw",
            "-device",
            f"scsi-hd,bus={MPTSAS_CONTROLLER_ID}.0,drive={drive},rotation_rate={disk.rotation_rate},"
            f"{product}serial={disk.serial},scsi-id={index},wwn={sas_wwn(index)}",
        ]
    return args


__all__ = [
    "Bus",
    "HDD_ROTATION_RATE",
    "SSD_ROTATION_RATE",
    "UNREPORTED_ROTATION_RATE",
    "ScsiDisk",
    "sas_wwn",
    "scsi_device_id",
    "scsi_disk_args",
    "scsi_hd_properties",
]
