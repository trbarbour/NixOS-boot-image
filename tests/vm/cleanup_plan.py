"""Cleanup helpers for RAID/LVM residue regression scenarios.

This module documents (and will eventually execute) the recipe used to create
mdadm and LVM residue inside the VM before running ``pre-nixos``. The recipe is
kept here so both the regression test and any ad-hoc debugging flows can reuse
the same commands and expectations.
"""

from __future__ import annotations

from dataclasses import dataclass
from textwrap import dedent
from typing import List


@dataclass(frozen=True)
class RaidResiduePlan:
    """Declarative description of how we seed and verify RAID/LVM leftovers."""

    preseed_commands: List[str]
    verification_commands: List[str]
    teardown_expectations: List[str]
    sentinel_path: str


def build_raid_residue_plan() -> RaidResiduePlan:
    """Return the canonical RAID/LVM residue creation and verification plan."""

    preseed_commands = [
        (
            "mdadm --create /dev/md127 --force --raid1 --level=1 --metadata=1.2 "
            "--raid-devices=2 /dev/vdb /dev/vdc"
        ),
        "pvcreate /dev/md127",
        "vgcreate vg_residue /dev/md127",
        "lvcreate -n lv_residue -l 100%FREE vg_residue",
        (
            "bash -c 'echo residue-marker >/dev/vg_residue/lv_residue && "
            "sync'"
        ),
        # Intentionally avoid wiping to mimic real-world leftovers left behind
        # by failed installer runs.
    ]

    verification_commands = [
        "lsblk --output NAME,TYPE,SIZE,MOUNTPOINT --paths",
        "mdadm --detail --scan || true",
        "ls /dev/vg_residue /dev/vg_residue/lv_residue || true",
        "blkid || true",
    ]

    teardown_expectations = [
        "no /dev/md127 array should remain after pre-nixos cleanup",
        "VG vg_residue and LV lv_residue should be absent",
        "no residue-marker content should persist on any block device",
    ]

    return RaidResiduePlan(
        preseed_commands=preseed_commands,
        verification_commands=verification_commands,
        teardown_expectations=teardown_expectations,
        sentinel_path="/dev/vg_residue/lv_residue",
    )


RAID_LVM_RESIDUE_SCRIPT = dedent(
    """
    set -euo pipefail

    mdadm --create /dev/md127 --force --raid1 --level=1 --metadata=1.2 \
      --raid-devices=2 /dev/vdb /dev/vdc

    pvcreate /dev/md127
    vgcreate vg_residue /dev/md127
    lvcreate -n lv_residue -l 100%FREE vg_residue

    echo residue-marker >/dev/vg_residue/lv_residue
    sync

    lsblk --output NAME,TYPE,SIZE,MOUNTPOINT --paths
    mdadm --detail --scan || true
    ls /dev/vg_residue /dev/vg_residue/lv_residue || true
    blkid || true
    """
)


__all__ = ["RAID_LVM_RESIDUE_SCRIPT", "RaidResiduePlan", "build_raid_residue_plan"]
