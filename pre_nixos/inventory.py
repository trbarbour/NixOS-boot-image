"""Disk inventory utilities."""

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Collection, Dict, FrozenSet, Iterable, List, Mapping, Optional
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


# Unit Serial Number VPD page (SPC; /sys/block/<d>/device/vpd_pg80): page
# code at byte 1, the serial's length at bytes 2-3 (big-endian), the serial
# from byte 4.  The only place SCSI, SAS and SATA disks expose their serial
# (task queue item 53; notes/2026-11-12T014614Z-disk-serial-experiment.md).
_VPD_UNIT_SERIAL_NUMBER = 0x80
_VPD80_HEADER = 4


def serial_from_vpd_pg80(page: bytes) -> Optional[str]:
    """The serial in a Unit Serial Number VPD page, or ``None``."""

    if len(page) < _VPD80_HEADER or page[1] != _VPD_UNIT_SERIAL_NUMBER:
        return None
    length = int.from_bytes(page[2:4], "big")
    if len(page) < _VPD80_HEADER + length:
        return None
    serial = page[_VPD80_HEADER : _VPD80_HEADER + length].decode("ascii", errors="replace").strip(" \x00")
    return serial or None


def _serial(entry: Path) -> str:
    """The disk's serial, from wherever its bus puts it (item 53), in order:
    ``serial`` (virtio-blk), ``device/serial`` (NVMe), ``device/vpd_pg80``
    (SCSI, SAS, SATA).  An empty file does not hide a later one; ``""`` when
    there is none."""

    for text in (_read_text(entry / "serial"), _read_text(entry / "device" / "serial")):
        if text:
            return text
    try:
        page = (entry / "device" / "vpd_pg80").read_bytes()
    except OSError:
        return ""
    return serial_from_vpd_pg80(page) or ""


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
        serial = _serial(entry)
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


# --- the plan's disks (task queue item 50, R-D3, R-D4) -----------------------
# Design: plans/2026-11-11T194943Z-disk-settle-design.md (D2, D5, D6).

# Where a plan records the disks it was made from.
PLAN_KEY = "inventory"
# auto-install-status REASON and storage-status DETAIL for a stopped run.
CHANGED_REASON = "disks-changed"

_GIB = 1024**3


@dataclass(frozen=True, order=True)
class DiskIdentity:
    """What makes a disk the same disk (D2): not its model or rotational flag."""

    name: str
    size: int
    serial: str

    def describe(self) -> str:
        serial = f"serial {self.serial}" if self.serial else "no serial"
        return f"{round(self.size / _GIB, 1):g} GiB, {serial}"


def disk_identities(disks: Iterable[Disk]) -> FrozenSet[DiskIdentity]:
    return frozenset(DiskIdentity(d.name, d.size, d.serial) for d in disks)


def describe_changes(
    before: FrozenSet[DiskIdentity], after: FrozenSet[DiskIdentity]
) -> List[str]:
    """Each disk added, removed or changed between two sets, by name."""

    old = {identity.name: identity for identity in before}
    new = {identity.name: identity for identity in after}
    changes: List[str] = []
    for name in sorted(old.keys() | new.keys()):
        was, now = old.get(name), new.get(name)
        if was == now:
            continue
        if now is None:
            assert was is not None
            changes.append(f"removed {name} ({was.describe()})")
        elif was is None:
            changes.append(f"added {name} ({now.describe()})")
        else:
            changes.append(f"changed {name}: was {was.describe()}; now {now.describe()}")
    return changes


def record_disks(plan: Dict[str, Any], disks: Iterable[Disk]) -> None:
    """Record in *plan* the disks it is made from."""

    plan[PLAN_KEY] = [
        {"name": i.name, "size": i.size, "serial": i.serial}
        for i in sorted(disk_identities(disks))
    ]


def _recorded(plan: Mapping[str, Any]) -> Optional[FrozenSet[DiskIdentity]]:
    """The plan's recorded disks; ``None`` when the record is malformed."""

    record = plan[PLAN_KEY]
    if not isinstance(record, list):
        return None
    identities = set()
    for entry in record:
        if not isinstance(entry, dict):
            return None
        name, size, serial = entry.get("name"), entry.get("size"), entry.get("serial")
        if not (isinstance(name, str) and isinstance(size, int) and isinstance(serial, str)):
            return None
        identities.add(DiskIdentity(name, size, serial))
    return frozenset(identities)


def verify_plan_disks(plan: Mapping[str, Any], protected: Collection[str]) -> List[str]:
    """Why *plan* must not be applied to the disks present now (R-D3, R-D4);
    empty when they are the disks it was made from.

    The inventory is taken as when planning: without the *protected* disks
    backing the running system.
    """

    if PLAN_KEY not in plan:
        return ["this plan does not record its disks (made by an older version, or by hand); re-plan on this machine"]
    recorded = _recorded(plan)
    if recorded is None:
        return ["this plan's record of its disks is malformed; re-plan on this machine"]
    current = disk_identities(exclude_disks(enumerate_disks(), protected))
    return describe_changes(recorded, current)


def changed_disks_message(changes: List[str]) -> str:
    """The message for a run stopped by :func:`verify_plan_disks`."""

    assert changes
    return "The disks are not the ones the plan was made from; nothing was written:\n" + "\n".join(
        f"  - {change}" for change in changes
    )


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
