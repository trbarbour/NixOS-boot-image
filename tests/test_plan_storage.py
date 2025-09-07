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
    assert {"main", "large"} <= vg_names
    lv_names = {lv["name"] for lv in plan["lvs"]}
    assert {"root", "data"} <= lv_names


def test_plan_single_disk() -> None:
    disks = [Disk(name="nvme0n1", size=1000, rotational=False)]
    plan = plan_storage("fast", disks)
    assert plan["arrays"] == []
    assert plan["vgs"] == [{"name": "main", "devices": ["nvme0n1"]}]
