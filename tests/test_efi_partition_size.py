"""ESP sizing: 3% of the disk, at least 1 GiB, at most 4 GiB (reqs §2.3, R-B3)."""

import pytest

from pre_nixos.inventory import Disk
from pre_nixos.planner import (
    EFI_PARTITION_MAX_SIZE,
    EFI_PARTITION_MIN_SIZE,
    MI_BYTE,
    _parse_size,
    efi_partition_size,
    plan_storage,
)

GIB = 1024**3


@pytest.mark.parametrize(
    ("disk_size", "expected"),
    [
        (0, 1 * GIB),
        (8 * GIB, 1 * GIB),  # SD card / small eMMC: the floor
        (32 * GIB, 1 * GIB),  # 3% = 0.96 GiB, below the floor
        (64 * GIB, 1966 * MI_BYTE),  # 3% = 1966.08 MiB, aligned down
        (100 * GIB, 3072 * MI_BYTE),
        (136 * GIB, 4 * GIB),  # 3% = 4.08 GiB, above the cap
        (500_107_862_016, 4 * GIB),  # a "500 GB" NVMe
        (16 * 1024 * GIB, 4 * GIB),
    ],
)
def test_efi_partition_size_examples(disk_size: int, expected: int) -> None:
    assert efi_partition_size(disk_size) == expected


def test_efi_partition_size_bounds_alignment_and_monotonicity() -> None:
    previous = 0
    for mib in range(0, 200 * 1024, 37):  # 0 .. 200 GiB in odd steps
        size = efi_partition_size(mib * MI_BYTE + 12345)
        assert EFI_PARTITION_MIN_SIZE <= size <= EFI_PARTITION_MAX_SIZE
        assert size % MI_BYTE == 0
        assert size >= previous
        previous = size
    assert previous == EFI_PARTITION_MAX_SIZE


def test_efi_partition_size_rejects_negative() -> None:
    with pytest.raises(AssertionError):
        efi_partition_size(-1)


def _efi_parts(plan: dict) -> dict[str, dict]:
    return {
        part["name"]: part
        for parts in plan["partitions"].values()
        for part in parts
        if part["type"] == "efi"
    }


def test_plan_records_esp_size_and_disko_uses_it() -> None:
    disk = Disk(name="nvme0n1", size=64 * GIB, rotational=False, nvme=True)
    plan = plan_storage("fast", [disk])
    (esp,) = _efi_parts(plan).values()
    assert esp["size"] == "1966M"
    disko_esp = plan["disko"]["disk"]["nvme0n1"]["content"]["partitions"]["nvme0n1p1"]
    assert disko_esp["size"] == "1966M"
    assert disko_esp["type"] == "EF00"


def test_raid_members_get_equal_esps_from_smallest_disk() -> None:
    # Two SSDs within the 1% grouping tolerance: one RAID set, one ESP size.
    small = 100 * GIB
    large = small + small // 200
    disks = [
        Disk(name="sda", size=large, rotational=False),
        Disk(name="sdb", size=small, rotational=False),
    ]
    plan = plan_storage("careful", disks)
    assert [arr["level"] for arr in plan["arrays"]] == ["raid1"]
    sizes = {part["size"] for part in _efi_parts(plan).values()}
    assert sizes == {"3G"}
    disko_sizes = {
        spec["size"]
        for disk in plan["disko"]["disk"].values()
        for spec in disk["content"]["partitions"].values()
        if spec.get("type") == "EF00"
    }
    assert disko_sizes == {"3G"}


def test_esp_is_deducted_from_main_capacity() -> None:
    # 200 GiB disk: the ESP is capped at 4 GiB.  With 512 GiB of RAM the swap
    # LV takes all that remains of main, so main's LVs fill exactly the other
    # 196 GiB, less the planner's margin of at most two 4 MiB extents.
    disk = Disk(name="nvme0n1", size=200 * GIB, rotational=False, nvme=True)
    plan = plan_storage("fast", [disk], ram_gb=512)
    used = sum(_parse_size(lv["size"]) for lv in plan["lvs"] if lv["vg"] == "main")
    available = 200 * GIB - EFI_PARTITION_MAX_SIZE
    assert available - 2 * 4 * MI_BYTE <= used <= available


def test_disks_outside_main_get_no_esp() -> None:
    disks = [
        Disk(name="nvme0n1", size=500 * GIB, rotational=False, nvme=True),
        Disk(name="sda", size=2000 * GIB, rotational=True),
        Disk(name="sdb", size=2000 * GIB, rotational=True),
    ]
    plan = plan_storage("fast", disks)
    assert set(_efi_parts(plan)) == {"nvme0n1p1"}


def test_disko_refuses_esp_without_size() -> None:
    plan = plan_storage("fast", [Disk(name="sda", size=64 * GIB, rotational=False)])
    del plan["partitions"]["sda"][0]["size"]
    with pytest.raises(AssertionError, match="has no size"):
        from pre_nixos.planner import refresh_disko_devices

        refresh_disko_devices(plan)
