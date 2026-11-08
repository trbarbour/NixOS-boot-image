"""Disk inventory utilities."""

from dataclasses import dataclass
from pathlib import Path
from typing import Collection, List, Optional
import math

from .block_names import is_non_candidate_device


@dataclass
class Disk:
    """Representation of a block device."""

    name: str
    model: str = ""
    size: int = 0
    rotational: bool = False
    serial: str = ""
    nvme: bool = False


def _read_text(path: Path) -> str:
    try:
        return path.read_text().strip()
    except FileNotFoundError:
        return ""


# SAT "ATA Information" VPD page (/sys/block/<d>/device/vpd_pg89): the
# kernel's copy of the drive's IDENTIFY data.  Layout: page code at byte 1,
# the ATA command code at byte 56, IDENTIFY data (512 bytes) from byte 60.
_VPD_ATA_INFORMATION = 0x89
_VPD89_COMMAND_CODE = 56
_VPD89_IDENTIFY = 60
_IDENTIFY_LENGTH = 512
# IDENTIFY DEVICE and IDENTIFY PACKET DEVICE; both carry the model here.
_IDENTIFY_COMMANDS = {0xEC, 0xA1}
# Model number: IDENTIFY words 27-46 (40 ASCII characters, bytes swapped
# within each word).
_MODEL_FIRST_WORD = 27
_MODEL_WORDS = 20


def ata_model_from_vpd_pg89(page: bytes) -> Optional[str]:
    """The full ATA model in an ATA Information VPD page, or ``None``.

    For a SATA disk, ``device/model`` is the 16-character SCSI product field
    libata fills in, so ``G.SKILL 128GB SSD`` reads as ``G.SKILL 128GB SS``
    and the disk-class rule (reqs R-S3) never sees "SSD" (#336).
    """

    if len(page) < _VPD89_IDENTIFY + _IDENTIFY_LENGTH:
        return None
    if page[1] != _VPD_ATA_INFORMATION or page[_VPD89_COMMAND_CODE] not in _IDENTIFY_COMMANDS:
        return None
    start = _VPD89_IDENTIFY + 2 * _MODEL_FIRST_WORD
    raw = page[start : start + 2 * _MODEL_WORDS]
    swapped = bytes(byte for i in range(0, len(raw), 2) for byte in (raw[i + 1], raw[i]))
    model = swapped.decode("ascii", errors="replace").strip(" \x00")
    return model or None


def _ata_model(device: Path) -> Optional[str]:
    """The full ATA model of ``device`` (a sysfs ``device`` directory), if any."""

    try:
        page = (device / "vpd_pg89").read_bytes()
    except OSError:
        # No ATA page (SAS, virtio, NVMe) or unreadable: use device/model.
        return None
    return ata_model_from_vpd_pg89(page)


def enumerate_disks(sys_block: Path = Path("/sys/block")) -> List[Disk]:
    """Enumerate available disks.

    Args:
        sys_block: Path to ``/sys/block`` (overridable for tests).

    Returns:
        A list of :class:`Disk` objects for non-removable, non-virtual devices.
    """
    disks: List[Disk] = []
    try:
        entries = list(sys_block.iterdir())
    except (FileNotFoundError, NotADirectoryError, PermissionError):
        return disks

    for entry in entries:
        name = entry.name
        if is_non_candidate_device(name):
            continue
        if _read_text(entry / "removable") == "1":
            continue
        model = _ata_model(entry / "device") or _read_text(entry / "device" / "model")
        rotational = _read_text(entry / "queue" / "rotational") == "1"
        size_str = _read_text(entry / "size")
        try:
            size = int(size_str) * 512
        except ValueError:
            size = 0
        serial = _read_text(entry / "device" / "serial")
        nvme = name.startswith("nvme")
        disks.append(
            Disk(
                name=name,
                model=model,
                size=size,
                rotational=rotational,
                serial=serial,
                nvme=nvme,
            )
        )
    return disks


def exclude_disks(disks: List[Disk], protected: Collection[str]) -> List[Disk]:
    """Return *disks* without those whose ``/dev`` path is in *protected*.

    Used to keep the disks backing the running system (the boot medium) out
    of the storage plan; see ``storage_detection.resolve_protected_disks``.
    """

    return [disk for disk in disks if f"/dev/{disk.name}" not in protected]


def detect_ram_gb(meminfo: Path = Path("/proc/meminfo")) -> int:
    """Detect total system RAM in GiB.

    Args:
        meminfo: Path to ``/proc/meminfo`` (overridable for tests).

    Returns:
        Total RAM rounded up to the nearest GiB. Returns ``0`` if the
        information cannot be determined.
    """

    try:
        for line in meminfo.read_text().splitlines():
            if line.startswith("MemTotal:"):
                parts = line.split()
                if len(parts) >= 2:
                    kb = int(parts[1])
                    # Convert kB to GiB, rounding up
                    return int(math.ceil(kb / (1024 * 1024)))
    except FileNotFoundError:
        pass
    return 0
