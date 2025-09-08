"""Tests for storage plan generation."""

from pre_nixos.inventory import Disk
from pre_nixos.planner import plan_storage


def test_plan_storage_basic() -> None:
    disks = [
        Disk(name="sda", size=1000, rotational=False),
        Disk(name="sdb", size=2000, rotational=True),
        Disk(name="sdc", size=2000, rotational=True),
    ]
    plan = plan_storage("fast", disks)
    assert any(arr["level"] == "raid1" for arr in plan["arrays"])
    vg_names = {vg["name"] for vg in plan["vgs"]}
    assert {"main", "swap"} <= vg_names
    lv_names = {lv["name"] for lv in plan["lvs"]}
    assert {"root", "swap"} <= lv_names


def test_plan_single_disk() -> None:
    disks = [Disk(name="nvme0n1", size=1000, rotational=False)]
    plan = plan_storage("fast", disks)
    assert plan["arrays"] == []
    assert plan["vgs"] == [{"name": "main", "devices": ["nvme0n1"]}]


def test_multiple_ssd_buckets_named_separately() -> None:
    disks = [
        Disk(name="sda", size=1000, rotational=False),
        Disk(name="sdb", size=1000, rotational=False),
        Disk(name="sdc", size=500, rotational=False),
    ]
    plan = plan_storage("fast", disks)
    vg_names = {vg["name"] for vg in plan["vgs"]}
    assert "main" in vg_names and "main-1" in vg_names
    lv_vgs = {lv["vg"] for lv in plan["lvs"]}
    assert lv_vgs == {"main"}

def test_multiple_hdd_buckets_named_separately() -> None:
    disks = [
        Disk(name="sda", size=2000, rotational=True),
        Disk(name="sdb", size=2000, rotational=True),
        Disk(name="sdc", size=1000, rotational=True),
    ]
    plan = plan_storage("fast", disks)
    vg_names = {vg["name"] for vg in plan["vgs"]}
    assert "swap" in vg_names and "large" in vg_names
    lv_vgs = {lv["vg"] for lv in plan["lvs"]}
    assert lv_vgs == {"swap", "large"}

def test_prefer_raid6_on_four_disks() -> None:
    disks = [
        Disk(name="sda", size=2000, rotational=True),
        Disk(name="sdb", size=2000, rotational=True),
        Disk(name="sdc", size=2000, rotational=True),
        Disk(name="sdd", size=2000, rotational=True),
    ]
    plan = plan_storage("fast", disks, prefer_raid6_on_four=True)
    assert any(arr["level"] == "raid6" for arr in plan["arrays"])
