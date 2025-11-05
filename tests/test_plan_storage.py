"""Tests for storage plan generation."""

from pre_nixos.inventory import Disk
from pre_nixos.planner import (
    plan_storage,
    ROOT_LV_SIZE,
    EFI_PARTITION_SIZE,
    _parse_size,
    _format_size,
    MI_BYTE,
    LVM_EXTENT_BYTES,
)


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
    assert {"slash", "swap", "home", "var_tmp", "var_log"} <= lv_names
    slash_lv = next(lv for lv in plan["lvs"] if lv["name"] == "slash")
    assert slash_lv["size"] == ROOT_LV_SIZE
    home_lv = next(lv for lv in plan["lvs"] if lv["name"] == "home")
    assert _parse_size(home_lv["size"]) <= _parse_size("16G")
    assert set(plan["partitions"]) == {"sda", "sdb", "sdc"}
    # sda is a single SSD, sdb and sdc form a RAID1 array
    assert [p["type"] for p in plan["partitions"]["sda"]][:1] == ["efi"]
    assert all(p["type"] == "lvm" for p in plan["partitions"]["sda"][1:])
    assert all(p["type"] == "linux-raid" for p in plan["partitions"]["sdb"])
    assert all(p["type"] == "linux-raid" for p in plan["partitions"]["sdc"])


def test_home_lv_uses_quarter_or_less_of_remaining_space() -> None:
    disks = [Disk(name="sda", size=60, rotational=False)]
    plan = plan_storage("fast", disks, ram_gb=4)

    home_lv = next(lv for lv in plan["lvs"] if lv["name"] == "home")
    slash_lv = next(lv for lv in plan["lvs"] if lv["name"] == "slash")

    capacity = _parse_size("60G") - EFI_PARTITION_SIZE
    capacity -= capacity % MI_BYTE
    free_after_slash = max(capacity - _parse_size(slash_lv["size"]), 0)
    free_after_slash -= free_after_slash % LVM_EXTENT_BYTES
    quarter = free_after_slash // 4
    quarter -= quarter % LVM_EXTENT_BYTES
    expected = min(_parse_size("16G"), quarter)
    assert _parse_size(home_lv["size"]) == expected


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
    assert "main" in vg_names and "main_1" in vg_names
    lv_vgs = {lv["vg"] for lv in plan["lvs"]}
    assert lv_vgs == {"main"}
    # only the disks in the main VG should have an EFI partition
    assert [p["type"] for p in plan["partitions"]["sda"]][:1] == ["efi"]
    assert [p["type"] for p in plan["partitions"]["sdb"]][:1] == ["efi"]
    # sda and sdb participate in a RAID array, while sdc is a single disk
    assert all(p["type"] == "linux-raid" for p in plan["partitions"]["sda"][1:])
    assert all(p["type"] == "linux-raid" for p in plan["partitions"]["sdb"][1:])
    assert all(p["type"] == "lvm" for p in plan["partitions"]["sdc"])

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


def test_hdd_only_promotes_main_with_efi() -> None:
    disks = [
        Disk(name="sda", size=2000, rotational=True),
        Disk(name="sdb", size=2000, rotational=True),
        Disk(name="sdc", size=2000, rotational=True),
    ]
    plan = plan_storage("fast", disks)
    vg_names = {vg["name"] for vg in plan["vgs"]}
    assert "main" in vg_names
    slash_lv = next(lv for lv in plan["lvs"] if lv["name"] == "slash")
    assert slash_lv["vg"] == "main"
    assert any(arr["level"] == "raid5" for arr in plan["arrays"])
    for disk in ["sda", "sdb", "sdc"]:
        parts = plan["partitions"][disk]
        assert parts[0]["type"] == "efi"
        assert parts[1]["type"] == "linux-raid"

def test_two_hdd_only_becomes_main_with_swap_lv() -> None:
    disks = [
        Disk(name="sdb", size=2000, rotational=True),
        Disk(name="sdc", size=2000, rotational=True),
    ]
    plan = plan_storage("fast", disks)
    vg_names = {vg["name"] for vg in plan["vgs"]}
    assert vg_names == {"main"}
    lv_info = {(lv["name"], lv["vg"]) for lv in plan["lvs"]}
    assert ("slash", "main") in lv_info and ("swap", "main") in lv_info
    assert any(arr["level"] == "raid1" for arr in plan["arrays"])
    assert set(plan["partitions"]) == {"sdb", "sdc"}


def test_single_hdd_only_becomes_main_with_swap_lv() -> None:
    disks = [Disk(name="sda", size=2000, rotational=True)]
    plan = plan_storage("fast", disks)
    vg_names = {vg["name"] for vg in plan["vgs"]}
    assert vg_names == {"main"}
    lv_info = {(lv["name"], lv["vg"]) for lv in plan["lvs"]}
    assert ("slash", "main") in lv_info and ("swap", "main") in lv_info
    assert plan["arrays"] == []
    assert set(plan["partitions"]) == {"sda"}
    assert all(p["type"] == "lvm" for p in plan["partitions"]["sda"][1:])


def test_hdd_only_plan_populates_disko_devices() -> None:
    disks = [Disk(name="sda", size=2000, rotational=True)]
    plan = plan_storage("fast", disks)
    disko = plan["disko"]
    disk_cfg = disko["disk"]["sda"]
    partitions = disk_cfg["content"]["partitions"]
    efi = partitions["sda1"]
    assert efi["type"] == "EF00"
    assert efi["content"]["mountpoint"] == "/boot"
    data = partitions["sda2"]
    assert data["content"] == {"type": "lvm_pv", "vg": "main"}
    vg_cfg = disko["lvm_vg"]["main"]
    lvs = vg_cfg["lvs"]
    assert {"slash", "swap", "home"} <= set(lvs)
    assert lvs["slash"]["content"]["mountpoint"] == "/"
    assert lvs["swap"]["content"]["type"] == "swap"


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
    assert all(p["type"] == "lvm" for p in plan["partitions"]["sdb"])


def test_swap_vg_populates_additional_volumes() -> None:
    disks = [
        Disk(name="sda", size=1000, rotational=False),
        Disk(name="sdb", size=2000, rotational=True),
        Disk(name="sdc", size=2000, rotational=True),
    ]
    plan = plan_storage("fast", disks)

    swap_lv = next(lv for lv in plan["lvs"] if lv["name"] == "swap")
    var_tmp = next(lv for lv in plan["lvs"] if lv["name"] == "var_tmp")
    var_log = next(lv for lv in plan["lvs"] if lv["name"] == "var_log")

    assert var_tmp["vg"] == "swap"
    assert var_log["vg"] == "swap"
    assert var_tmp["size"] == swap_lv["size"]
    expected_log = min(_parse_size("4G"), _parse_size(swap_lv["size"]))
    assert _parse_size(var_log["size"]) == expected_log

    assert plan.get("post_apply_commands") == ["chmod 1777 /mnt/var/tmp"]


def test_ssd_only_has_swap_lv_in_main() -> None:
    disks = [
        Disk(name="sda", size=1000, rotational=False),
        Disk(name="sdb", size=1000, rotational=False),
    ]
    plan = plan_storage("fast", disks)
    vg_names = {vg["name"] for vg in plan["vgs"]}
    assert vg_names == {"main"}
    swap_lv = next(lv for lv in plan["lvs"] if lv["name"] == "swap")
    assert swap_lv["vg"] == "main"


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
    assert all(lv["name"] != "var_tmp" for lv in plan["lvs"])
    assert all(lv["name"] != "var_log" for lv in plan["lvs"])
    assert plan.get("post_apply_commands") is None


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
    assert swap_lv["size"] == f"{5 * 2}G"


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
    assert all(p["type"] == "lvm" for p in plan["partitions"]["sdb"])
    assert all(p["type"] == "lvm" for p in plan["partitions"]["sdc"])


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


def test_slash_lv_size_capped() -> None:
    disks = [Disk(name="sda", size=15, rotational=False)]
    plan = plan_storage("fast", disks)
    slash_lv = next(lv for lv in plan["lvs"] if lv["name"] == "slash")
    expected_max = _parse_size("14G")
    actual = _parse_size(slash_lv["size"])
    assert actual <= expected_max
    assert expected_max - actual <= 2 * LVM_EXTENT_BYTES


def test_swap_lv_accounts_for_efi_partition() -> None:
    disk_size = 500_107_862_016
    disks = [Disk(name="nvme0n1", size=disk_size, rotational=False, nvme=True)]
    plan = plan_storage("fast", disks, ram_gb=512)
    swap_lv = next(lv for lv in plan["lvs"] if lv["name"] == "swap")
    home_lv = next((lv for lv in plan["lvs"] if lv["name"] == "home"), None)

    # Capacity available to LVM is the disk size minus the 1G EFI partition.
    efi = _parse_size("1G")
    capacity = disk_size - efi
    # Align down to the nearest MiB to match planner rounding.
    capacity -= capacity % (1024 ** 2)
    slash_size = _parse_size(ROOT_LV_SIZE)
    expected_swap = max(capacity - slash_size, 0)
    if home_lv is not None:
        expected_swap = max(expected_swap - _parse_size(home_lv["size"]), 0)
    expected_swap -= expected_swap % (1024 ** 2)
    actual_swap = _parse_size(swap_lv["size"])
    assert actual_swap <= expected_swap
    assert expected_swap - actual_swap <= 2 * LVM_EXTENT_BYTES


def test_data_lv_size_capped() -> None:
    disks = [
        Disk(name="sda", size=100, rotational=False),
        Disk(name="sdb", size=60, rotational=True),
        Disk(name="sdc", size=50, rotational=True),
    ]
    plan = plan_storage("fast", disks)
    data_lv = next(lv for lv in plan["lvs"] if lv["name"] == "data")
    expected_max = _parse_size("60G")
    actual = _parse_size(data_lv["size"])
    assert actual <= expected_max
    assert expected_max - actual <= 2 * LVM_EXTENT_BYTES


def test_plan_emits_disko_config() -> None:
    disks = [
        Disk(name="sda", size=1000, rotational=False),
        Disk(name="sdb", size=2000, rotational=True),
        Disk(name="sdc", size=2000, rotational=True),
    ]
    plan = plan_storage("fast", disks)
    devices = plan["disko"]
    assert devices["disk"]["sda"]["content"]["partitions"]["sda1"]["content"]["mountpoint"] == "/boot"
    md0 = devices["mdadm"]["md0"]
    assert md0["level"] == 1
    assert md0["content"]["vg"] == "swap"
    assert "devices" not in md0
    arrays = {arr["name"]: arr for arr in plan["arrays"]}
    assert set(arrays["md0"]["devices"]) == {"sdb1", "sdc1"}
    slash = devices["lvm_vg"]["main"]["lvs"]["slash"]
    assert slash["content"]["mountpoint"] == "/"
    home = devices["lvm_vg"]["main"]["lvs"]["home"]
    assert home["content"]["mountpoint"] == "/home"
    swap = devices["lvm_vg"]["swap"]["lvs"]["swap"]
    assert swap["content"]["type"] == "swap"
    var_tmp = devices["lvm_vg"]["swap"]["lvs"]["var_tmp"]
    assert var_tmp["content"]["mountpoint"] == "/var/tmp"
    var_log = devices["lvm_vg"]["swap"]["lvs"]["var_log"]
    assert var_log["content"]["mountpoint"] == "/var/log"


def test_secondary_efi_partition_not_mounted() -> None:
    disks = [
        Disk(name="sda", size=1000, rotational=False),
        Disk(name="sdb", size=1000, rotational=False),
    ]
    plan = plan_storage("fast", disks)
    partitions = plan["disko"]["disk"]["sdb"]["content"]["partitions"]
    assert "mountpoint" not in partitions["sdb1"]["content"]
