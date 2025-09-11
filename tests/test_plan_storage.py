"""Tests for storage plan generation."""

from pre_nixos.inventory import Disk
from pre_nixos.planner import plan_storage, ROOT_LV_SIZE


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
    root_lv = next(lv for lv in plan["lvs"] if lv["name"] == "root")
    assert root_lv["size"] == ROOT_LV_SIZE
    assert set(plan["partitions"]) == {"sda", "sdb", "sdc"}


def test_plan_single_disk() -> None:
    disks = [Disk(name="nvme0n1", size=1000, rotational=False)]
    plan = plan_storage("fast", disks)
    assert plan["arrays"] == []
    assert plan["vgs"] == [{"name": "main", "devices": ["nvme0n1p2"]}]


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
    # only the disks in the main VG should have an EFI partition
    assert [p["type"] for p in plan["partitions"]["sda"]][:1] == ["efi"]
    assert [p["type"] for p in plan["partitions"]["sdb"]][:1] == ["efi"]
    assert all(p["type"] == "linux-raid" for p in plan["partitions"]["sdc"])

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

def test_two_hdd_only_becomes_main_with_swap_lv() -> None:
    disks = [
        Disk(name="sdb", size=2000, rotational=True),
        Disk(name="sdc", size=2000, rotational=True),
    ]
    plan = plan_storage("fast", disks)
    vg_names = {vg["name"] for vg in plan["vgs"]}
    assert vg_names == {"main"}
    lv_info = {(lv["name"], lv["vg"]) for lv in plan["lvs"]}
    assert ("root", "main") in lv_info and ("swap", "main") in lv_info
    assert any(arr["level"] == "raid1" for arr in plan["arrays"])
    assert set(plan["partitions"]) == {"sdb", "sdc"}


def test_single_hdd_only_becomes_main_with_swap_lv() -> None:
    disks = [Disk(name="sda", size=2000, rotational=True)]
    plan = plan_storage("fast", disks)
    vg_names = {vg["name"] for vg in plan["vgs"]}
    assert vg_names == {"main"}
    lv_info = {(lv["name"], lv["vg"]) for lv in plan["lvs"]}
    assert ("root", "main") in lv_info and ("swap", "main") in lv_info
    assert plan["arrays"] == []
    assert set(plan["partitions"]) == {"sda"}


def test_single_hdd_with_ssd_gets_swap_vg() -> None:
    disks = [
        Disk(name="sda", size=1000, rotational=False),
        Disk(name="sdb", size=2000, rotational=True),
    ]
    plan = plan_storage("fast", disks)
    vg_names = {vg["name"] for vg in plan["vgs"]}
    assert {"main", "swap"} <= vg_names
    swap_vg = next(vg for vg in plan["vgs"] if vg["name"] == "swap")
    assert swap_vg["devices"] == ["sdb1"]
    lv_info = {(lv["name"], lv["vg"]) for lv in plan["lvs"]}
    assert ("swap", "swap") in lv_info
    # only the SSD in main VG gets an EFI partition
    assert [p["type"] for p in plan["partitions"]["sda"]][:1] == ["efi"]
    assert all(p["type"] == "linux-raid" for p in plan["partitions"]["sdb"])


def test_ssd_only_has_no_swap() -> None:
    disks = [
        Disk(name="sda", size=1000, rotational=False),
        Disk(name="sdb", size=1000, rotational=False),
    ]
    plan = plan_storage("fast", disks)
    vg_names = {vg["name"] for vg in plan["vgs"]}
    lv_names = {lv["name"] for lv in plan["lvs"]}
    assert "swap" not in vg_names
    assert "swap" not in lv_names


def test_swap_lv_falls_back_to_large_vg() -> None:
    disks = [
        Disk(name="sda", size=1000, rotational=False),
        Disk(name="sdb", size=2000, rotational=True),
        Disk(name="sdc", size=2000, rotational=True),
        Disk(name="sdd", size=2000, rotational=True),
    ]
    plan = plan_storage("fast", disks)
    vg_names = {vg["name"] for vg in plan["vgs"]}
    assert "swap" not in vg_names
    assert "large" in vg_names
    swap_lv = next(lv for lv in plan["lvs"] if lv["name"] == "swap")
    assert swap_lv["vg"] == "large"


def test_only_one_swap_lv() -> None:
    disks = [
        Disk(name="sda", size=1000, rotational=False),
        Disk(name="sdb", size=2000, rotational=True),
        Disk(name="sdc", size=2000, rotational=True),
        Disk(name="sdd", size=1000, rotational=True),
    ]
    plan = plan_storage("fast", disks)
    swap_lvs = [lv for lv in plan["lvs"] if lv["name"] == "swap"]
    assert len(swap_lvs) == 1


def test_swap_size_matches_double_ram() -> None:
    disks = [
        Disk(name="sda", size=1000, rotational=False),
        Disk(name="sdb", size=2000, rotational=True),
        Disk(name="sdc", size=2000, rotational=True),
    ]
    plan = plan_storage("fast", disks, ram_gb=5)
    swap_lv = next(lv for lv in plan["lvs"] if lv["name"] == "swap")
    assert swap_lv["size"] == f"{5 * 2 * 1024}M"


def test_efi_partitions_only_for_main_vg() -> None:
    disks = [
        Disk(name="sda", size=1000, rotational=False),
        Disk(name="sdb", size=2000, rotational=True),
        Disk(name="sdc", size=1000, rotational=True),
    ]
    plan = plan_storage("fast", disks)
    vg_names = {vg["name"] for vg in plan["vgs"]}
    assert {"main", "swap", "large"} <= vg_names
    # verify partition types per disk
    assert [p["type"] for p in plan["partitions"]["sda"]][:1] == ["efi"]
    assert all(p["type"] == "linux-raid" for p in plan["partitions"]["sdb"])
    assert all(p["type"] == "linux-raid" for p in plan["partitions"]["sdc"])


def test_prefer_raid6_on_four_disks() -> None:
    disks = [
        Disk(name="sda", size=2000, rotational=True),
        Disk(name="sdb", size=2000, rotational=True),
        Disk(name="sdc", size=2000, rotational=True),
        Disk(name="sdd", size=2000, rotational=True),
    ]
    plan = plan_storage("fast", disks, prefer_raid6_on_four=True)
    assert any(arr["level"] == "raid6" for arr in plan["arrays"])


def test_small_hdd_pair_preferred_for_swap() -> None:
    disks = [
        Disk(name="sda", size=1000, rotational=False),
        Disk(name="sdb", size=2000, rotational=True),
        Disk(name="sdc", size=2000, rotational=True),
        Disk(name="sdd", size=1000, rotational=True),
        Disk(name="sde", size=1000, rotational=True),
    ]
    plan = plan_storage("fast", disks)
    swap_vg = next(vg for vg in plan["vgs"] if vg["name"] == "swap")
    swap_array = next(arr for arr in plan["arrays"] if arr["name"] == swap_vg["devices"][0])
    assert set(swap_array["devices"]) == {"sdd1", "sde1"}
