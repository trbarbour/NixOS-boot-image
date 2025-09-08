"""Tests for apply module."""

from pre_nixos.inventory import Disk
from pre_nixos.planner import plan_storage
from pre_nixos.apply import apply_plan


def test_apply_plan_returns_commands() -> None:
    disks = [
        Disk(name="sda", size=1000, rotational=False),
        Disk(name="sdb", size=2000, rotational=True),
        Disk(name="sdc", size=2000, rotational=True),
    ]
    plan = plan_storage("fast", disks)
    commands = apply_plan(plan)
    assert any(cmd.startswith("mdadm") for cmd in commands)
    assert any(cmd.startswith("pvcreate") for cmd in commands)
    assert any("vgcreate main" in cmd for cmd in commands)
    assert any("lvcreate -n root" in cmd for cmd in commands)
    assert any(cmd.startswith("mkswap") for cmd in commands)
    assert any(cmd.startswith("sgdisk") for cmd in commands)
    # only disks in the main VG should receive an EFI partition
    assert sum("EF00" in cmd for cmd in commands) == 1
    assert any(cmd.startswith("pvcreate") for cmd in commands)

def test_apply_plan_handles_swap() -> None:
    plan = {
        "arrays": [
            {"name": "md0", "level": "raid1", "devices": ["sdb", "sdc"]}
        ],
        "vgs": [
            {"name": "swap", "devices": ["md0"]}
        ],
        "lvs": [
            {"name": "swap", "vg": "swap", "size": "8G"}
        ],
    }
    commands = apply_plan(plan)
    assert "pvcreate /dev/md0" in commands
    assert "vgcreate swap /dev/md0" in commands
    assert "lvcreate -n swap swap -L 8G" in commands
    assert commands.index("pvcreate /dev/md0") < commands.index(
        "vgcreate swap /dev/md0"
    )
