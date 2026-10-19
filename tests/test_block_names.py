"""Kernel block-device naming rules (AArch64 plan §3.5, reqs R-S2, §2.3).

Verified against Linux 6.18.56 (the nixpkgs 26.05 kernel):
- block/partitions/core.c:335-338: a partition is ``"%sp%d"`` when the disk
  name ends in a digit, else ``"%s%d"``.
- drivers/mmc/core/block.c:2525-2539, 2637-2638: eMMC hardware areas are extra
  *block* disks ``mmcblk<N>boot0/1`` and ``mmcblk<N>gp0..3`` (boot areas are
  read-only by default); RPMB is a character device (line 2978).
"""
from __future__ import annotations

from pathlib import Path

import pytest

from pre_nixos import inventory, planner
from pre_nixos.block_names import is_emmc_hardware_area, partition_name


@pytest.mark.parametrize(
    "disk,expected",
    [
        ("sda", "sda1"),
        ("vda", "vda1"),
        ("nvme0n1", "nvme0n1p1"),
        ("mmcblk0", "mmcblk0p1"),
        ("loop0", "loop0p1"),
        ("md127", "md127p1"),
    ],
)
def test_partition_name_follows_the_kernel_digit_rule(disk: str, expected: str) -> None:
    assert partition_name(disk, 1) == expected


@pytest.mark.parametrize(
    "name,expected",
    [
        ("mmcblk0boot0", True),
        ("mmcblk0boot1", True),
        ("mmcblk1gp3", True),
        ("mmcblk0", False),
        ("mmcblk0p1", False),
        ("nvme0n1", False),
        ("sda", False),
    ],
)
def test_emmc_hardware_areas_are_recognised(name: str, expected: bool) -> None:
    assert is_emmc_hardware_area(name) is expected


def _sys_block(root: Path, names: list[str]) -> Path:
    for name in names:
        entry = root / name
        (entry / "queue").mkdir(parents=True)
        (entry / "device").mkdir()
        (entry / "removable").write_text("0")
        (entry / "queue" / "rotational").write_text("0")
        (entry / "size").write_text(str(32 * 1024**3 // 512))
    return root


def test_enumerate_disks_skips_emmc_hardware_areas(tmp_path: Path) -> None:
    root = _sys_block(tmp_path, ["mmcblk0", "mmcblk0boot0", "mmcblk0boot1", "nvme0n1"])
    assert sorted(d.name for d in inventory.enumerate_disks(root)) == ["mmcblk0", "nvme0n1"]


def test_plan_on_emmc_uses_p_separated_partitions(tmp_path: Path) -> None:
    """A single eMMC is a valid system disk (R-S2); its partitions are mmcblk0pN."""

    disks = inventory.enumerate_disks(_sys_block(tmp_path, ["mmcblk0"]))
    plan = planner.plan_storage("fast", disks, ram_gb=2)
    names = [p["name"] for p in plan["partitions"]["mmcblk0"]]
    assert names and all(n.startswith("mmcblk0p") for n in names), names
    assert any(lv["name"] == "slash" and lv["vg"] == "main" for lv in plan["lvs"])


def test_existing_storage_scan_ignores_emmc_hardware_areas() -> None:
    """Only candidate disks count (reqs §2.3); boot0 may hold a vendor bootloader."""

    from pre_nixos.storage_detection import CommandOutput, DetectionEnvironment, scan_existing_storage

    commands = {
        ("lsblk", "-dnpo", "NAME,TYPE,RM"): CommandOutput(
            stdout="/dev/mmcblk0 disk 0\n/dev/mmcblk0boot0 disk 0\n/dev/mmcblk0boot1 disk 0\n"
        ),
        ("lsblk", "-rno", "TYPE", "/dev/mmcblk0"): CommandOutput(stdout="disk\n"),
        ("wipefs", "-n", "/dev/mmcblk0"): CommandOutput(stdout=""),
    }
    env = DetectionEnvironment(
        run=lambda cmd: commands[tuple(cmd)],
        path_exists=lambda path: True,
        realpath=lambda path: path,
        read_cmdline=lambda: [],
    )
    assert scan_existing_storage(env) == []
