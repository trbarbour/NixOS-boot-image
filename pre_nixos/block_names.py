"""Kernel block-device naming rules shared by inventory, planning and detection.

Verified against Linux 6.18.56 (nixpkgs 26.05); see tests/test_block_names.py
for the source lines.  AArch64 plan §3.5; reqs §2.1 R-S2 and §2.3.
"""

from __future__ import annotations

import re

# eMMC hardware areas: boot0/boot1 (read-only by default) and general-purpose
# gp0..gp3 are separate block disks of the same chip, never planning targets.
_EMMC_HARDWARE_AREA = re.compile(r"mmcblk\d+(boot|gp)\d+")


def partition_name(disk: str, number: int) -> str:
    """Return the kernel's name for partition ``number`` of ``disk``.

    The kernel inserts ``p`` when the disk name ends in a digit
    (``nvme0n1p1``, ``mmcblk0p1``) and appends the number otherwise (``sda1``).
    """

    assert disk and number >= 1, (disk, number)
    return f"{disk}p{number}" if disk[-1].isdigit() else f"{disk}{number}"


def is_emmc_hardware_area(name: str) -> bool:
    """True for ``mmcblkNbootM`` / ``mmcblkNgpM`` (a bare name, no ``/dev/``)."""

    return _EMMC_HARDWARE_AREA.fullmatch(name) is not None


__all__ = ["is_emmc_hardware_area", "partition_name"]
