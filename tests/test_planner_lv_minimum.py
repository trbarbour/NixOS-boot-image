"""No sliver LVs (task queue item 11).

``add_lv`` gave whatever was left when a request did not fit, so a nearly
full VG produced a one-extent (4 MiB) swap or data LV: neither a real size
nor omitted, as reqs §2.4 allows ("if there is insufficient capacity anywhere,
swap may be omitted").  Now an optional LV (home, swap, var_tmp, var_log,
data) is created only with at least ``OPTIONAL_LV_MINIMUM`` (1 GiB), or its
full request if that is smaller; ``slash`` is required and exempt.
"""

from __future__ import annotations

from typing import Dict, List

import pytest

from pre_nixos.inventory import Disk
from pre_nixos.planner import LVM_EXTENT_BYTES, OPTIONAL_LV_MINIMUM, _parse_size, plan_storage

GIB = 1024**3


def _lvs(plan: dict) -> Dict[str, int]:
    return {f"{lv['vg']}/{lv['name']}": _parse_size(lv["size"]) for lv in plan["lvs"]}


def _ssd(name: str, gib: float) -> Disk:
    return Disk(name=name, size=int(gib * GIB), rotational=False)


def _hdd(name: str, gib: float) -> Disk:
    return Disk(name=name, size=int(gib * GIB), rotational=True)


def test_the_minimum_is_one_gib() -> None:
    assert OPTIONAL_LV_MINIMUM == GIB
    assert OPTIONAL_LV_MINIMUM % LVM_EXTENT_BYTES == 0


@pytest.mark.parametrize(
    "disks,ram_gb,expected",
    [
        # Item 11 as filed: two 4 GiB SSDs (RAID-0), 2 GiB RAM.
        ([_ssd("vda", 4), _ssd("vdb", 4)], 2, ["main/slash"]),
        # The same on one small SSD, and on the HDD-only path.
        ([_ssd("nvme0n1", 6)], 2, ["main/slash"]),
        ([_hdd("sda", 6)], 2, ["main/slash"]),
        # large/data was 4 MiB once swap had taken the small large VG.
        (
            [_ssd("sda", 64), _hdd("sdb", 5), _hdd("sdc", 5), _hdd("sdd", 5)],
            16,
            ["main/slash", "main/home", "large/swap"],
        ),
    ],
)
def test_no_sliver_lv_is_planned(disks: List[Disk], ram_gb: int, expected: List[str]) -> None:
    lvs = _lvs(plan_storage("fast", disks, ram_gb=ram_gb))
    assert sorted(lvs) == sorted(expected), lvs


@pytest.mark.parametrize("gib", [6, 20, 64, 128, 256])
@pytest.mark.parametrize("ram_gb", [1, 2, 16, 64])
@pytest.mark.parametrize("layout", ["ssd", "ssd+3hdd", "hdd-only"])
def test_every_optional_lv_reaches_the_minimum(gib: int, ram_gb: int, layout: str) -> None:
    if layout == "ssd":
        disks = [_ssd("nvme0n1", gib)]
    elif layout == "ssd+3hdd":
        disks = [_ssd("sda", gib)] + [_hdd(f"sd{c}", gib) for c in "bcd"]
    else:
        disks = [_hdd("sda", gib)]
    for name, size in _lvs(plan_storage("fast", disks, ram_gb=ram_gb)).items():
        if name.endswith("/slash"):
            continue
        assert size >= OPTIONAL_LV_MINIMUM, (name, size)


def test_a_useful_partial_swap_is_kept() -> None:
    """Partial swap stays: §2.4 omits swap only without capacity."""

    lvs = _lvs(plan_storage("fast", [_ssd("nvme0n1", 64)], ram_gb=16))
    assert OPTIONAL_LV_MINIMUM <= lvs["main/swap"] < 32 * GIB, lvs


def test_slash_is_still_planned_on_a_tiny_disk() -> None:
    lvs = _lvs(plan_storage("fast", [_ssd("nvme0n1", 2)], ram_gb=2))
    assert "main/slash" in lvs and lvs["main/slash"] < OPTIONAL_LV_MINIMUM * 2, lvs
