"""Cleanup helpers for RAID/LVM residue regression scenarios.

Document the RAID/LVM residue seeding recipe for cleanup regression tests.

This module will eventually host helpers for executing the residue plan inside
the VM. Keeping the canonical commands here ensures ad-hoc debugging flows and
regression tests exercise the same behavior.
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
            "mdadm --create /dev/md127 --force --level=1 --metadata=1.2 "
            "--raid-devices=2 /dev/vdb /dev/vdc"
        ),
        "mdadm --detail /dev/md127",
        "pvcreate /dev/md127",
        "vgcreate vg_residue /dev/md127",
        "lvcreate -n lv_residue -l 100%FREE vg_residue",
        (
            "printf 'residue-marker' | "
            "dd of=/dev/vg_residue/lv_residue bs=1 conv=fsync status=none"
        ),
        (
            "dd if=/dev/vg_residue/lv_residue bs=1 count=64 status=none | "
            "hexdump -C"
        ),
        # Intentionally avoid wiping to mimic real-world leftovers left behind
        # by failed installer runs.
    ]

    verification_commands = [
        "lsblk --output NAME,TYPE,SIZE,MOUNTPOINT --paths",
        "mdadm --detail --scan || true",
        "ls /dev/vg_residue /dev/vg_residue/lv_residue 2>/dev/null || true",
        "blkid || true",
        (
            "dd if=/dev/vg_residue/lv_residue bs=1 count=64 status=none "
            "2>/dev/null | hexdump -C || true"
        ),
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

    mdadm --create /dev/md127 --force --level=1 --metadata=1.2 \
      --raid-devices=2 /dev/vdb /dev/vdc
    mdadm --detail /dev/md127

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
