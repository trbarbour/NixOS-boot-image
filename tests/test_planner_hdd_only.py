"""HDD-only machines must still get main/slash; swap needs room in its group.

Regression for trbarbour/NixOS-boot-image#313 (RAID VM spike, 2026-10-19):
with no SSD and more than one disk-size group, the bucket chosen for ``main``
was also chosen for ``swap``, and ``swap`` won, so the plan had no root
filesystem.  The swap-room check also compared bytes with GiB.
Requirements: automated-pre-nixos-reqs.md §2.4 (main/slash mandatory; swap
fallback large → main) and §2.1 R-S2 (machines may have no SSD).
"""
from __future__ import annotations

from typing import Any, Dict, List

from pre_nixos import planner
from pre_nixos.inventory import Disk

GIB = 1024**3


def _hdd(name: str, gib: int) -> Disk:
    return Disk(name=name, size=gib * GIB, rotational=True)


def _vg_devices(plan: Dict[str, Any], name: str) -> List[str]:
    return next(vg["devices"] for vg in plan["vgs"] if vg["name"] == name)


def _lv_vgs(plan: Dict[str, Any]) -> Dict[str, str]:
    return {lv["name"]: lv["vg"] for lv in plan["lvs"]}


def test_hdd_only_with_two_size_groups_keeps_main_and_slash() -> None:
    """The spike's disk set: one 4G HDD plus an equal pair of 6G HDDs."""

    plan = planner.plan_storage("fast", [_hdd("vda", 4), _hdd("sda", 6), _hdd("sdb", 6)], ram_gb=2)
    assert _lv_vgs(plan)["slash"] == "main"
    assert _vg_devices(plan, "main") == ["md0"], "main should be on the redundant pair"
    assert [(a["name"], a["level"]) for a in plan["arrays"]] == [("md0", "raid1")]


def test_hdd_only_spike_layout_with_small_pair_keeps_main() -> None:
    """Exact spike sizes (bytes): 4G + 2x2G, 2 GiB RAM."""

    plan = planner.plan_storage("fast", [_hdd("vda", 4), _hdd("sda", 2), _hdd("sdb", 2)], ram_gb=2)
    assert _lv_vgs(plan)["slash"] == "main"


def test_swap_group_needs_room_for_twice_ram_in_bytes() -> None:
    """A 2 GiB pair cannot hold 4 GiB of swap, so it is not the swap group."""

    ssd = Disk(name="nvme0n1", size=32 * GIB, rotational=False, nvme=True)
    plan = planner.plan_storage("fast", [ssd, _hdd("sda", 2), _hdd("sdb", 2)], ram_gb=2)
    assert all(vg["name"] != "swap" for vg in plan["vgs"])


def test_swap_group_is_used_when_it_has_room() -> None:
    ssd = Disk(name="nvme0n1", size=32 * GIB, rotational=False, nvme=True)
    plan = planner.plan_storage("fast", [ssd, _hdd("sda", 6), _hdd("sdb", 6)], ram_gb=2)
    assert _vg_devices(plan, "swap") == ["md0"]
    assert _lv_vgs(plan)["swap"] == "swap"
