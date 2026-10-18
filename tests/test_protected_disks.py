"""Disks backing the running system must never be planned, wiped or counted.

Regression for trbarbour/NixOS-boot-image#306: the boot disk was excluded only
from the existing-storage scan, while the storage plan excluded only RM=1
devices, so a USB boot stick reporting RM=0 was planned and then wiped by the
boot-time auto-provisioning (which the scan's exclusion let proceed).
Requirement: automated-pre-nixos-reqs.md §2.3 (boot medium).
"""
from __future__ import annotations

from pathlib import Path
from typing import Dict, Tuple

import pytest

from pre_nixos import apply, inventory, planner, storage_detection
from pre_nixos.storage_detection import CommandOutput, DetectionEnvironment
# Bound at import: the autouse storage stub replaces the module attribute.
from pre_nixos.storage_detection import resolve_protected_disks

CommandMap = Dict[Tuple[str, ...], CommandOutput]
NOT_MOUNTED = CommandOutput(stdout="", returncode=1)


def make_env(commands: CommandMap) -> DetectionEnvironment:
    """Fake environment: unknown ``findmnt`` targets are not mountpoints."""

    def run(cmd):  # type: ignore[no-untyped-def]
        key = tuple(cmd)
        if key in commands:
            return commands[key]
        if key[0] == "findmnt":
            return NOT_MOUNTED
        raise AssertionError(f"unexpected command invocation: {cmd}")

    return DetectionEnvironment(
        run=run,
        path_exists=lambda path: path.startswith("/dev/"),
        realpath=lambda path: path,
        read_cmdline=lambda: [],
    )


def mount(target: str, source: str) -> Tuple[Tuple[str, ...], CommandOutput]:
    return ("findmnt", "-n", "-o", "SOURCE", target), CommandOutput(stdout=f"{source}\n")


def deps(device: str, *rows: str) -> Tuple[Tuple[str, ...], CommandOutput]:
    return ("lsblk", "-nrspo", "NAME,TYPE", device), CommandOutput(stdout="\n".join(rows) + "\n")


def test_iso_on_usb_stick_is_protected() -> None:
    env = make_env(
        dict(
            [
                mount("/iso", "/dev/sda"),
                (("lsblk", "-npo", "PKNAME", "/dev/sda"), CommandOutput(stdout="")),
                mount("/", "tmpfs"),
                deps("/dev/sda", "/dev/sda disk"),
            ]
        )
    )
    assert resolve_protected_disks(env) == frozenset({"/dev/sda"})


def test_sd_card_root_is_protected() -> None:
    """AArch64 SD image: root is an ext4 partition on the card."""

    env = make_env(
        dict(
            [
                mount("/", "/dev/mmcblk0p2"),
                deps("/dev/mmcblk0p2", "/dev/mmcblk0p2 part", "/dev/mmcblk0 disk"),
                mount("/boot/firmware", "/dev/mmcblk0p1"),
                deps("/dev/mmcblk0p1", "/dev/mmcblk0p1 part", "/dev/mmcblk0 disk"),
            ]
        )
    )
    assert resolve_protected_disks(env) == frozenset({"/dev/mmcblk0"})


def test_root_on_lvm_on_raid_protects_every_member_disk() -> None:
    env = make_env(
        dict(
            [
                mount("/", "/dev/mapper/main-slash"),
                deps(
                    "/dev/mapper/main-slash",
                    "/dev/mapper/main-slash lvm",
                    "/dev/md0 raid1",
                    "/dev/sda2 part",
                    "/dev/sda disk",
                    "/dev/sdb2 part",
                    "/dev/sdb disk",
                ),
            ]
        )
    )
    assert resolve_protected_disks(env) == frozenset({"/dev/sda", "/dev/sdb"})


def test_install_target_mounted_on_mnt_is_not_protected() -> None:
    """After auto-apply, disko leaves the *target* mounted on /mnt; it must stay plannable."""

    env = make_env(dict([mount("/", "tmpfs"), mount("/mnt", "/dev/mapper/main-slash")]))
    assert resolve_protected_disks(env) == frozenset()


def test_unresolvable_system_mount_is_an_error_not_unprotected() -> None:
    """Fail safe: if a system mount's disks cannot be determined, refuse."""

    env = make_env(
        dict(
            [
                mount("/", "/dev/sda1"),
                (("lsblk", "-nrspo", "NAME,TYPE", "/dev/sda1"), CommandOutput(stdout="", returncode=32)),
            ]
        )
    )
    with pytest.raises(RuntimeError, match="/dev/sda1"):
        resolve_protected_disks(env)


def _fake_sys_block(root: Path) -> Path:
    for name, size_gb in (("nvme0n1", 500), ("sda", 64)):
        entry = root / name
        (entry / "queue").mkdir(parents=True)
        (entry / "device").mkdir()
        (entry / "removable").write_text("0")  # the USB stick reports RM=0
        (entry / "queue" / "rotational").write_text("0")
        (entry / "size").write_text(str(size_gb * 1024**3 // 512))
    return root


def test_protected_boot_stick_is_left_out_of_the_storage_plan(tmp_path: Path) -> None:
    """The #306 reproduction: an RM=0 boot stick must not reach disko."""

    disks = inventory.exclude_disks(
        inventory.enumerate_disks(_fake_sys_block(tmp_path)), frozenset({"/dev/sda"})
    )
    plan = planner.plan_storage("fast", disks, ram_gb=8)
    assert [d.name for d in disks] == ["nvme0n1"]
    assert sorted(plan["disko"]["disk"]) == ["nvme0n1"]


def test_apply_plan_refuses_a_plan_touching_a_protected_disk() -> None:
    """Runtime precondition at the destructive boundary (defence in depth)."""

    plan = {"partitions": {"sda": [{"name": "sda1", "type": "efi"}]}, "disko": {"disk": {"sda": {"device": "/dev/sda"}}}}
    with pytest.raises(RuntimeError, match="protected"):
        apply.apply_plan(plan, dry_run=True, protected_disks=frozenset({"/dev/sda"}))


def test_scan_does_not_count_protected_disks_as_existing_storage() -> None:
    """The boot medium's own data must not block auto-provisioning (§2.3)."""

    env = make_env(
        {
            ("lsblk", "-dnpo", "NAME,TYPE,RM"): CommandOutput(stdout="/dev/mmcblk0 disk 0\n/dev/nvme0n1 disk 0\n"),
            ("lsblk", "-rno", "TYPE", "/dev/nvme0n1"): CommandOutput(stdout="disk\n"),
            ("wipefs", "-n", "/dev/nvme0n1"): CommandOutput(stdout=""),
        }
    )
    found = storage_detection.scan_existing_storage(env, protected_disks=frozenset({"/dev/mmcblk0"}))
    assert found == []
