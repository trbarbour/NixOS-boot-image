"""Disk partitioning utilities."""

from __future__ import annotations

import re
import subprocess
from typing import List


def create_partitions(
    device: str,
    *,
    with_efi: bool = True,
    efi_size: str = "512MiB",
    dry_run: bool = False,
) -> List[str]:
    """Create a GPT with optional EFI and LVM partitions.

    When ``with_efi`` is ``True`` the layout is:
    * Partition 1: EFI System (type EF00) of ``efi_size``.
    * Partition 2: Linux LVM (type 8E00) using the remaining space.

    Otherwise a single Linux LVM partition spanning the whole disk is
    created.

    Parameters:
        device: Disk device path (e.g. ``/dev/sda``).
        with_efi: Whether to create a small EFI partition.
        efi_size: Size of the EFI system partition.
        dry_run: If ``True``, commands are returned instead of executed.

    Returns:
        List of shell command strings representing the operations.
    """

    if not re.fullmatch(r"/dev/[A-Za-z0-9_/-]+", device):
        raise ValueError("Unsafe device path")

    cmds: List[list[str]] = [["sgdisk", "--zap-all", device]]

    if with_efi:
        cmds.extend(
            [
                ["sgdisk", f"-n1:0:+{efi_size}", "-t1:EF00", device],
                ["sgdisk", "-n2:0:0", "-t2:8E00", device],
                ["parted", "-s", device, "set", "1", "boot", "on"],
                ["parted", "-s", device, "set", "2", "lvm", "on"],
            ]
        )
    else:
        cmds.extend(
            [
                ["sgdisk", "-n1:0:0", "-t1:8E00", device],
                ["parted", "-s", device, "set", "1", "lvm", "on"],
            ]
        )

    if dry_run:
        return [" ".join(cmd) for cmd in cmds]

    for cmd in cmds:
        subprocess.check_call(cmd)
    return []
