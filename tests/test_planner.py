"""Tests for planner grouping and RAID decisions."""

from pre_nixos.inventory import Disk
from pre_nixos.planner import (
    group_by_rotational_and_size,
    decide_ssd_array,
    decide_hdd_array,
)


def test_t1_nvme_only() -> None:
    disks = [Disk(name="nvme0n1", size=1000, rotational=False, nvme=True)]
    groups = group_by_rotational_and_size(disks)
    assert len(groups["ssd"]) == 1
    arr = decide_ssd_array(groups["ssd"][0], "fast")
    assert arr["level"] == "single"


def test_t2_two_ssd() -> None:
    disks = [Disk(name="sda", size=1000, rotational=False), Disk(name="sdb", size=1000, rotational=False)]
    groups = group_by_rotational_and_size(disks)
    arr_fast = decide_ssd_array(groups["ssd"][0], "fast")
    arr_careful = decide_ssd_array(groups["ssd"][0], "careful")
    assert arr_fast["level"] == "raid0"
    assert arr_careful["level"] == "raid1"


def test_t3_ssd_and_two_hdd() -> None:
    disks = [
        Disk(name="sda", size=1000, rotational=False),
        Disk(name="sdb", size=2000, rotational=True),
        Disk(name="sdc", size=2000, rotational=True),
    ]
    groups = group_by_rotational_and_size(disks)
    assert len(groups["ssd"][0]) == 1
    hdd_group = groups["hdd"][0]
    assert decide_hdd_array(hdd_group)["level"] == "raid1"


def test_t4_four_hdd_plus_ssd() -> None:
    disks = [Disk(name="sda", size=1000, rotational=False)]
    disks += [Disk(name=n, size=2000, rotational=True) for n in ["sdb", "sdc", "sdd", "sde"]]
    groups = group_by_rotational_and_size(disks)
    hdd_group = groups["hdd"][0]
    assert decide_hdd_array(hdd_group)["level"] == "raid5"


def test_t5_mixed_hdd_groups() -> None:
    disks = [Disk(name="sda", size=1000, rotational=False)]
    disks += [Disk(name=n, size=2000, rotational=True) for n in ["sdb", "sdc", "sdd", "sde"]]
    disks += [Disk(name="sdf", size=1000, rotational=True), Disk(name="sdg", size=1000, rotational=True)]
    groups = group_by_rotational_and_size(disks)
    assert len(groups["hdd"]) == 2
    large_group = max(groups["hdd"], key=len)
    small_group = min(groups["hdd"], key=len)
    assert decide_hdd_array(large_group)["level"] == "raid5"
    assert decide_hdd_array(small_group)["level"] == "raid1"


def test_t6_heterogeneous_hdd_sizes() -> None:
    disks = [Disk(name=n, size=s, rotational=True) for n, s in zip(["sda", "sdb", "sdc"], [1000, 2000, 3000])]
    groups = group_by_rotational_and_size(disks)
    assert len(groups["hdd"]) == 3
    for bucket in groups["hdd"]:
        assert decide_hdd_array(bucket)["level"] == "single"
