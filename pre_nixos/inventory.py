"""Disk inventory utilities."""

from dataclasses import dataclass
from pathlib import Path
from typing import List


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


def enumerate_disks(sys_block: Path = Path("/sys/block")) -> List[Disk]:
    """Enumerate available disks.

    Args:
        sys_block: Path to ``/sys/block`` (overridable for tests).

    Returns:
        A list of :class:`Disk` objects for non-removable, non-virtual devices.
    """
    disks: List[Disk] = []
    for entry in sys_block.iterdir():
        name = entry.name
        if name.startswith(("loop", "ram", "dm", "sr", "md")):
            continue
        if _read_text(entry / "removable") == "1":
            continue
        model = _read_text(entry / "device" / "model")
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
