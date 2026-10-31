"""Boot partitions per firmware (R-B1, R-B4; D2, D6 of
plans/2026-10-31T010024Z-x86-bios-support-plan.md)."""

from __future__ import annotations

from pre_nixos.boot_layout import BootLayout, choose_boot_disks
from pre_nixos.inventory import Disk
from pre_nixos.planner import plan_storage

GIB = 1024**3
NVME = Disk(name="nvme0n1", size=500 * GIB, rotational=False, nvme=True)
HDD_A = Disk(name="sda", size=1000 * GIB, rotational=True)
HDD_B = Disk(name="sdb", size=1000 * GIB, rotational=True)
SATA_SSD = Disk(name="sdc", size=250 * GIB, rotational=False)


def _types(plan: dict, disk: str) -> list[str]:
    return [part["type"] for part in plan["partitions"][disk]]


def _disko_parts(plan: dict, disk: str) -> dict:
    return plan["disko"]["disk"][disk]["content"]["partitions"]


def test_pi_layout_is_unchanged() -> None:
    plan = plan_storage("fast", [NVME], boot_layout=BootLayout.ESP)
    assert _types(plan, "nvme0n1") == ["efi", "lvm"]
    assert plan["boot"] == {"layout": "esp", "disks": ["nvme0n1"]}


def test_x86_uefi_adds_a_bios_boot_partition_first() -> None:
    """D2: on x86 the disk boots either way.  The BIOS boot partition is
    partition 1, as disko creates it (some BIOSes require it first)."""

    plan = plan_storage("fast", [NVME], boot_layout=BootLayout.X86_UEFI)
    assert _types(plan, "nvme0n1") == ["bios_grub", "efi", "lvm"]
    parts = _disko_parts(plan, "nvme0n1")
    assert parts["nvme0n1p1"] == {"size": "1M", "type": "EF02"}
    assert parts["nvme0n1p2"]["type"] == "EF00"
    assert "content" in parts["nvme0n1p3"]
    assert plan["boot"] == {"layout": "x86-uefi", "disks": ["nvme0n1"]}


def test_bios_with_nvme_main_boots_from_the_swap_pair() -> None:
    """D6, the user's old machines: one NVMe (not bootable by their BIOS) and
    a pair of HDDs for swap.  The root stays on NVMe; /boot and GRUB go on
    both swap disks, as the user used to do by hand."""

    plan = plan_storage("fast", [NVME, HDD_A, HDD_B], boot_layout=BootLayout.X86_BIOS)
    assert {vg["name"] for vg in plan["vgs"]} >= {"main", "swap"}
    assert _types(plan, "nvme0n1") == ["lvm"]
    assert _types(plan, "sda") == ["bios_grub", "efi", "linux-raid"]
    assert _types(plan, "sdb") == ["bios_grub", "efi", "linux-raid"]
    assert plan["boot"] == {"layout": "x86-bios", "disks": ["sda", "sdb"]}
    # The first ESP is /boot; the swap pair's data partitions still form the mirror.
    assert _disko_parts(plan, "sda")["sda2"]["content"]["mountpoint"] == "/boot"
    assert "mountpoint" not in _disko_parts(plan, "sdb")["sdb2"]["content"]
    (swap_array,) = [arr for arr in plan["arrays"] if arr["level"] == "raid1"]
    assert sorted(swap_array["devices"]) == ["sda3", "sdb3"]


def test_bios_with_sata_main_boots_from_main() -> None:
    plan = plan_storage("fast", [SATA_SSD], boot_layout=BootLayout.X86_BIOS)
    assert _types(plan, "sdc") == ["bios_grub", "efi", "lvm"]
    assert plan["boot"]["disks"] == ["sdc"]


def test_bios_with_only_nvme_has_no_boot_disks() -> None:
    """R-B4: nothing the BIOS can boot; the install is refused (not planned here)."""

    plan = plan_storage("fast", [NVME], boot_layout=BootLayout.X86_BIOS)
    assert _types(plan, "nvme0n1") == ["lvm"]
    assert plan["boot"] == {"layout": "x86-bios", "disks": []}


def test_bios_boot_partition_is_deducted_from_capacity() -> None:
    uefi = plan_storage("fast", [SATA_SSD], boot_layout=BootLayout.X86_UEFI, ram_gb=512)
    esp_only = plan_storage("fast", [SATA_SSD], boot_layout=BootLayout.ESP, ram_gb=512)

    def main_lvs(plan: dict) -> int:
        from pre_nixos.planner import _parse_size

        return sum(_parse_size(lv["size"]) for lv in plan["lvs"] if lv["vg"] == "main")

    # 1 MiB less for LVM; allocation is in 4 MiB extents, so at most one extent less.
    assert 0 <= main_lvs(esp_only) - main_lvs(uefi) <= 4 * 1024**2


def test_choose_boot_disks_order() -> None:
    nvme_main = [NVME]
    ssd_other = [SATA_SSD]
    swap = [HDD_A, HDD_B]
    large = [Disk(name="sdd", size=4000 * GIB, rotational=True)]
    roles = [("large", large), ("swap", swap), ("main_1", ssd_other), ("main", nvme_main)]
    assert choose_boot_disks(roles, BootLayout.X86_BIOS) == ssd_other
    assert choose_boot_disks(roles[:2], BootLayout.X86_BIOS) == swap
    assert choose_boot_disks([("large", large)], BootLayout.X86_BIOS) == large
    assert choose_boot_disks(roles, BootLayout.X86_UEFI) == nvme_main
    assert choose_boot_disks([("main", nvme_main)], BootLayout.X86_BIOS) is None
    # A mixed group: only its BIOS-bootable member (Codex review on #330).
    assert choose_boot_disks([("main", [NVME, SATA_SSD])], BootLayout.X86_BIOS) == [SATA_SSD]


def test_plan_partition_numbers_match_disko(tmp_path) -> None:
    """disko orders GPT partitions by priority (EF02 first, the data
    partition last); the plan's names must be the numbers it creates."""

    plan = plan_storage("fast", [NVME, HDD_A, HDD_B], boot_layout=BootLayout.X86_BIOS)
    for disk, parts in plan["partitions"].items():
        disko = _disko_parts(plan, disk)
        types = [disko[part["name"]].get("type") for part in parts]
        # disko's default priorities: EF02 100, sized partitions 1000, "100%" 9001.
        rank = {"EF02": 0, "EF00": 1, None: 2}
        assert types == sorted(types, key=lambda t: rank.get(t, 2)), (disk, types)


def test_bios_mixed_nvme_and_sata_group_boots_from_the_sata_member() -> None:
    """Codex review on #330: a SATA SSD and an NVMe of near-equal size form one
    group (one array).  The BIOS can boot the SATA member, so it gets the boot
    partitions; the NVMe member keeps only its data partition."""

    nvme = Disk(name="nvme0n1", size=500 * GIB, rotational=False, nvme=True)
    sata = Disk(name="sda", size=500 * GIB, rotational=False)
    plan = plan_storage("careful", [nvme, sata], boot_layout=BootLayout.X86_BIOS)
    assert plan["boot"] == {"layout": "x86-bios", "disks": ["sda"]}
    assert _types(plan, "sda") == ["bios_grub", "efi", "linux-raid"]
    assert _types(plan, "nvme0n1") == ["linux-raid"]
    (array,) = plan["arrays"]
    assert array["level"] == "raid1" and sorted(array["devices"]) == ["nvme0n1p1", "sda3"]
    # The mirror is the smaller member: the SATA disk less its boot partitions.
    assert _disko_parts(plan, "sda")["sda2"]["content"]["mountpoint"] == "/boot"


def test_bios_nvme_plus_one_large_hdd_boots_from_the_swap_hdd() -> None:
    """User question: NVMe and a single HDD.  The HDD becomes the swap VG and
    gets the boot partitions; the root stays on NVMe."""

    plan = plan_storage("fast", [NVME, HDD_A], boot_layout=BootLayout.X86_BIOS)
    assert {vg["name"] for vg in plan["vgs"]} == {"main", "swap"}
    assert plan["boot"]["disks"] == ["sda"]
    assert _types(plan, "sda") == ["bios_grub", "efi", "lvm"]
    assert _types(plan, "nvme0n1") == ["lvm"]


def test_bios_nvme_plus_one_small_hdd_boots_from_the_large_hdd() -> None:
    """Too small for swap (2 x RAM), the HDD becomes `large`, D6's last choice."""

    small = Disk(name="sda", size=20 * GIB, rotational=True)
    plan = plan_storage("fast", [NVME, small], boot_layout=BootLayout.X86_BIOS, ram_gb=16)
    assert {vg["name"] for vg in plan["vgs"]} == {"main", "large"}
    assert plan["boot"]["disks"] == ["sda"]
    assert _types(plan, "sda") == ["bios_grub", "efi", "lvm"]
