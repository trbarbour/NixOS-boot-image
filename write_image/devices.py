"""Which block devices the image writer may write (requirement R-W2).

Pure over a :class:`SystemView` (a sysfs ``block`` directory, the mounted
sources and the system's own disks), so the list, the CLI's check and the
root helper's re-check are one function (R-W5), testable on fake trees.

A device is eligible when it is a whole disk with a medium, its transport is
USB or MMC/SD, or the kernel marks it removable, and it is not:
- on a SATA, NVMe or virtio transport (unless the kernel says removable);
- mounted, or holding a mounted partition;
- in use by device-mapper or md (a partition with holders);
- one of the system's own disks (holding ``/`` or ``/nix``).
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import FrozenSet, Iterable, List, Literal, Sequence, Set, Tuple, Union

Transport = Literal["usb", "mmc", "sata", "nvme", "virtio", "other"]
Format = Literal["iso", "sd"]
_NAME = re.compile(r"^[a-z][a-z0-9]*$")


@dataclass(frozen=True)
class Candidate:
    """An eligible device."""

    name: str
    model: str
    serial: str
    size_bytes: int
    transport: Transport
    removable: bool

    @property
    def path(self) -> str:
        return f"/dev/{self.name}"

    def describe(self) -> str:
        size = f"{self.size_bytes / 1000**3:.1f} GB"
        serial = f", serial {self.serial}" if self.serial else ""
        return f"{self.path}: {self.model or 'unknown model'}{serial}, {size}, {self.transport}"


@dataclass(frozen=True)
class Refusal:
    """A device that may not be written, and why."""

    name: str
    reason: str


Verdict = Union[Candidate, Refusal]


@dataclass(frozen=True)
class SystemView:
    """What the eligibility rules look at."""

    sys_block: Path
    mounted_sources: FrozenSet[str]
    system_devices: FrozenSet[str]


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return ""


def transport(sys_block: Path, name: str) -> Transport:
    """The bus a disk hangs off, from its sysfs device path."""

    target = os.path.realpath(sys_block / name)
    if "/usb" in target:
        return "usb"
    if "/mmc_host/" in target or name.startswith("mmcblk"):
        return "mmc"
    if "/nvme" in target or name.startswith("nvme"):
        return "nvme"
    if "/virtio" in target or name.startswith("vd"):
        return "virtio"
    if "/ata" in target:
        return "sata"
    return "other"


def _partitions(sys_block: Path, name: str) -> List[str]:
    disk = sys_block / name
    try:
        return sorted(entry.name for entry in disk.iterdir() if entry.name.startswith(name) and entry.is_dir())
    except OSError:
        return []


def _holders(path: Path) -> List[str]:
    try:
        return sorted(entry.name for entry in (path / "holders").iterdir())
    except OSError:
        return []


def check(view: SystemView, name: str) -> Verdict:
    """The verdict for one whole-disk kernel name (``sdb``, ``mmcblk0``)."""

    if not _NAME.match(name) or not (view.sys_block / name).exists():
        return Refusal(name, "no such whole-disk device")
    disk = view.sys_block / name
    if not (disk / "device").exists():
        return Refusal(name, "not a physical disk")
    removable = _read(disk / "removable") == "1"
    bus = transport(view.sys_block, name)
    if not removable and bus not in ("usb", "mmc"):
        return Refusal(name, f"not removable ({bus} disk)")
    if name in view.system_devices:
        return Refusal(name, "holds the running system (/ or /nix)")
    parts = _partitions(view.sys_block, name)
    mounted = [p for p in (name, *parts) if f"/dev/{p}" in view.mounted_sources]
    if mounted:
        return Refusal(name, f"mounted ({', '.join('/dev/' + p for p in mounted)})")
    held = [p for p in (name, *parts) if _holders(disk if p == name else disk / p)]
    if held:
        return Refusal(name, f"in use by device-mapper or md ({', '.join(held)})")
    try:
        size = int(_read(disk / "size") or "0") * 512
    except ValueError:
        size = 0
    if size == 0:
        return Refusal(name, "no medium")
    return Candidate(
        name=name,
        model=_read(disk / "device/model"),
        serial=_read(disk / "device/serial"),
        size_bytes=size,
        transport=bus,
        removable=removable,
    )


def scan(view: SystemView) -> Tuple[List[Candidate], List[Refusal]]:
    """Every whole disk's verdict, split into candidates and refusals."""

    candidates: List[Candidate] = []
    refusals: List[Refusal] = []
    try:
        names = sorted(entry.name for entry in view.sys_block.iterdir())
    except OSError:
        names = []
    for name in names:
        if name.startswith(("loop", "ram", "zram", "dm-", "md", "sr")):
            continue
        verdict = check(view, name)
        if isinstance(verdict, Candidate):
            candidates.append(verdict)
        else:
            refusals.append(verdict)
    return candidates, refusals


def preferred(candidates: Sequence[Candidate], fmt: Format) -> List[Candidate]:
    """Candidates in the order to offer: USB first for the ISO, MMC/SD for the SD image."""

    first: Transport = "usb" if fmt == "iso" else "mmc"
    return sorted(candidates, key=lambda c: (c.transport != first, c.name))


def disks_of(sys_block: Path, name: str) -> Set[str]:
    """The whole disks under a block device: itself, a partition's disk, or a
    device-mapper/md device's slaves, recursively."""

    entry = sys_block / name
    if entry.exists():
        slaves = entry / "slaves"
        if slaves.is_dir() and any(slaves.iterdir()):
            found: Set[str] = set()
            for slave in slaves.iterdir():
                found |= disks_of(sys_block, slave.name)
            return found
        return {name}
    # A partition: its directory sits inside the disk's.
    for disk in sys_block.iterdir():
        if (disk / name).is_dir():
            return {disk.name}
    return set()


def _mount_table(mounts: str) -> List[Tuple[str, str]]:
    table = []
    for line in mounts.splitlines():
        fields = line.split()
        if len(fields) >= 2:
            table.append((fields[0], fields[1].replace("\\040", " ")))
    return table


def live_view(sys_block: Path = Path("/sys/block"), mounts_file: Path = Path("/proc/self/mounts")) -> SystemView:
    """The running system's view."""

    table = _mount_table(_read(mounts_file))
    sources = frozenset(source for source, _ in table)
    system: Set[str] = set()
    for source, target in table:
        if target in ("/", "/nix", "/nix/store") and source.startswith("/dev/"):
            real = os.path.realpath(source)
            system |= disks_of(sys_block, Path(real).name)
    resolved = frozenset({os.path.realpath(s) for s in sources if s.startswith("/dev/")}) | sources
    return SystemView(sys_block=sys_block, mounted_sources=resolved, system_devices=frozenset(system))


__all__ = [
    "Candidate",
    "Format",
    "Refusal",
    "SystemView",
    "Transport",
    "Verdict",
    "check",
    "disks_of",
    "live_view",
    "preferred",
    "scan",
    "transport",
]
