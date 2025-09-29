"""Tests for filesystem related commands in apply_plan."""

from pre_nixos.inventory import Disk
from pre_nixos.planner import plan_storage
from pre_nixos.apply import apply_plan


def test_filesystem_commands_for_lvs() -> None:
    disks = [
        Disk(name="sda", size=1000, rotational=False),
        Disk(name="sdb", size=2000, rotational=True),
        Disk(name="sdc", size=2000, rotational=True),
        Disk(name="sdd", size=1000, rotational=True),
    ]
    plan = plan_storage("fast", disks)
    commands = apply_plan(plan, dry_run=True)

    # mkfs.ext4 uses a 2 KiB bytes-per-inode ratio to avoid inode exhaustion
    # in the Nix store which contains many small files.
    assert f"mkfs.ext4 -i 2048 /dev/main/slash" in commands
    assert f"e2label /dev/main/slash slash" in commands
    assert f"mount -L slash /mnt" in commands

    assert f"mkfs.ext4 -i 2048 /dev/large/data" in commands
    assert f"e2label /dev/large/data data" in commands
    assert f"mount -L data /mnt/data" in commands

    # Ensure the EFI system partition is created, labeled and mounted.
    assert any(cmd.startswith("mkfs.vfat -F 32 -n EFI") for cmd in commands)
    assert "mount -L EFI /mnt/boot" in commands


def test_mount_points_created_for_non_slash_lvs() -> None:
    disks = [
        Disk(name="sda", size=1000, rotational=False),
        Disk(name="sdb", size=2000, rotational=True),
        Disk(name="sdc", size=2000, rotational=True),
        Disk(name="sdd", size=1000, rotational=True),
    ]
    plan = plan_storage("fast", disks)
    commands = apply_plan(plan)

    for lv in plan["lvs"]:
        if lv["name"] in {"slash", "swap"}:
            continue
        mount_point = f"/mnt/{lv['name']}"
        mkdir_cmd = f"mkdir -p {mount_point}"
        mount_cmd = f"mount -L {lv['name']} {mount_point}"
        assert mkdir_cmd in commands
        assert commands.index(mkdir_cmd) < commands.index(mount_cmd)
