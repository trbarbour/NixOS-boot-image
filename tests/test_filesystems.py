"""Tests for filesystem related commands in apply_plan."""

from pre_nixos.inventory import Disk
from pre_nixos.planner import plan_storage
from pre_nixos.apply import apply_plan


def test_filesystem_commands_for_lvs() -> None:
    disks = [
        Disk(name="sda", size=1000, rotational=False),
        Disk(name="sdb", size=2000, rotational=True),
        Disk(name="sdc", size=2000, rotational=True),
    ]
    plan = plan_storage("fast", disks)
    commands = apply_plan(plan)

    # mkfs.ext4 uses a 2 KiB bytes-per-inode ratio to avoid inode exhaustion
    # in the Nix store which contains many small files.
    assert f"mkfs.ext4 -i 2048 /dev/main/root" in commands
    assert f"e2label /dev/main/root root" in commands
    assert f"mount -L root /mnt" in commands

    assert f"mkfs.ext4 -i 2048 /dev/large/data" in commands
    assert f"e2label /dev/large/data data" in commands
    assert f"mount -L data /mnt/data" in commands
