"""Disks backing the running system must never be planned, wiped or counted.

Regression for trbarbour/NixOS-boot-image#306: the boot disk was excluded only
from the existing-storage scan, while the storage plan excluded only RM=1
devices, so a USB boot stick reporting RM=0 was planned and then wiped by the
boot-time auto-provisioning (which the scan's exclusion let proceed).
Requirement: automated-pre-nixos-reqs.md §2.3 (boot medium).
"""
from __future__ import annotations

from pathlib import Path
from typing import Collection, Dict, Mapping, Optional, Sequence, Tuple

import pytest

from pre_nixos import apply, inventory, planner, storage_detection
from pre_nixos.storage_detection import CommandOutput, DetectionEnvironment
# Bound at import: the autouse storage stub replaces the module attribute.
from pre_nixos.storage_detection import resolve_protected_disks

MOUNT_LISTING = ("findmnt", "-rn", "-o", "TARGET,SOURCE")
SWAP_LISTING = ("swapon", "--show=NAME", "--noheadings", "--raw")


def make_env(
    *,
    mounts: Mapping[str, str],
    swaps: Sequence[str] = (),
    stacks: Mapping[str, Sequence[str]],
    block_devices: Optional[Collection[str]] = None,
) -> DetectionEnvironment:
    """Fake host given its mount table, active swaps and block-device stacks.

    ``stacks`` maps a device to its ``lsblk -s`` rows (itself, then what it
    sits on), e.g. ``{"/dev/sda1": ["/dev/sda1 part", "/dev/sda disk"]}``.
    ``block_devices`` defaults to the devices in ``stacks``; every absolute
    path "exists", as it would for a directory used as a mount source.
    """

    blocks = set(stacks) if block_devices is None else set(block_devices)

    def run(cmd):  # type: ignore[no-untyped-def]
        key = tuple(cmd)
        if key == MOUNT_LISTING:
            return CommandOutput(stdout="".join(f"{t} {s}\n" for t, s in mounts.items()))
        if key == SWAP_LISTING:
            return CommandOutput(stdout="".join(f"{s}\n" for s in swaps))
        if key[:4] == ("findmnt", "-n", "-o", "SOURCE"):  # resolve_boot_disk probes
            source = mounts.get(key[4])
            return CommandOutput(stdout=f"{source}\n") if source else CommandOutput("", 1)
        if key[:2] == ("findmnt", "-nr"):  # squashfs / iso9660 probes
            return CommandOutput("", 1)
        if key[:3] == ("lsblk", "-npo", "PKNAME"):
            rows = stacks.get(key[3], [])
            parents = [r.split()[0] for r in rows[1:] if r.split()[1] == "disk"]
            # -p prints full paths, as observed in the guest (spike run2, #306).
            return CommandOutput(stdout=(parents[0] + "\n") if parents else "\n")
        if key[:3] == ("lsblk", "-nrspo", "NAME,TYPE"):
            rows = stacks.get(key[3])
            if rows is None:
                return CommandOutput("", 32)
            return CommandOutput(stdout="\n".join(rows) + "\n")
        raise AssertionError(f"unexpected command invocation: {cmd}")

    return DetectionEnvironment(
        run=run,
        path_exists=lambda path: path.startswith("/"),
        realpath=lambda path: path,
        read_cmdline=lambda: [],
        is_block_device=lambda path: path in blocks,
    )


def test_iso_on_usb_stick_is_protected() -> None:
    env = make_env(
        mounts={"/": "tmpfs", "/iso": "/dev/sda", "/nix/store": "overlay"},
        stacks={"/dev/sda": ["/dev/sda disk"]},
    )
    assert resolve_protected_disks(env) == frozenset({"/dev/sda"})


def test_sd_card_root_is_protected() -> None:
    """AArch64 SD image: root is an ext4 partition on the card."""

    env = make_env(
        mounts={"/": "/dev/mmcblk0p2", "/boot/firmware": "/dev/mmcblk0p1"},
        stacks={
            "/dev/mmcblk0p2": ["/dev/mmcblk0p2 part", "/dev/mmcblk0 disk"],
            "/dev/mmcblk0p1": ["/dev/mmcblk0p1 part", "/dev/mmcblk0 disk"],
        },
    )
    assert resolve_protected_disks(env) == frozenset({"/dev/mmcblk0"})


def test_root_on_lvm_on_raid_protects_every_member_disk() -> None:
    env = make_env(
        mounts={"/": "/dev/mapper/main-slash"},
        stacks={
            "/dev/mapper/main-slash": [
                "/dev/mapper/main-slash lvm",
                "/dev/md0 raid1",
                "/dev/sda2 part",
                "/dev/sda disk",
                "/dev/sdb2 part",
                "/dev/sdb disk",
            ]
        },
    )
    assert resolve_protected_disks(env) == frozenset({"/dev/sda", "/dev/sdb"})


def test_separate_system_filesystems_on_other_disks_are_protected() -> None:
    """Every mount of the running system counts, not a fixed list (Codex review)."""

    env = make_env(
        mounts={"/": "/dev/sda2", "/home": "/dev/sdb1", "/var": "/dev/sdc1[/var]"},
        stacks={
            "/dev/sda2": ["/dev/sda2 part", "/dev/sda disk"],
            "/dev/sdb1": ["/dev/sdb1 part", "/dev/sdb disk"],
            "/dev/sdc1": ["/dev/sdc1 part", "/dev/sdc disk"],
        },
    )
    assert resolve_protected_disks(env) == frozenset({"/dev/sda", "/dev/sdb", "/dev/sdc"})


def test_active_swap_on_another_disk_is_protected() -> None:
    env = make_env(
        mounts={"/": "tmpfs"},
        swaps=["/dev/sdd2"],
        stacks={"/dev/sdd2": ["/dev/sdd2 part", "/dev/sdd disk"]},
    )
    assert resolve_protected_disks(env) == frozenset({"/dev/sdd"})


def test_install_target_and_its_swap_are_not_protected() -> None:
    """After auto-apply, disko leaves the *target* mounted on /mnt with its swap on."""

    env = make_env(
        mounts={
            "/": "tmpfs",
            "/mnt": "/dev/mapper/main-slash",
            "/mnt/boot": "/dev/vda1",
        },
        swaps=["/dev/dm-1"],
        stacks={
            "/dev/mapper/main-slash": ["/dev/mapper/main-slash lvm", "/dev/vda2 part", "/dev/vda disk"],
            "/dev/vda1": ["/dev/vda1 part", "/dev/vda disk"],
            "/dev/dm-1": ["/dev/dm-1 lvm", "/dev/vda2 part", "/dev/vda disk"],
        },
    )
    assert resolve_protected_disks(env) == frozenset()


def test_unresolvable_system_mount_is_an_error_not_unprotected() -> None:
    """Fail safe: if a system mount's disks cannot be determined, refuse."""

    env = make_env(mounts={"/": "/dev/sda1"}, stacks={}, block_devices={"/dev/sda1"})
    with pytest.raises(RuntimeError, match="/dev/sda1"):
        resolve_protected_disks(env)


def test_special_filesystems_do_not_confuse_protection() -> None:
    """Review question on #308: pseudo/special mounts must be ignored.

    Bare-word sources (tmpfs, proc, cgroup2, overlay, nsfs[...]) name no
    device; a path-like source that is not a block device (here a tmpfs
    mounted with a directory as its "device") must be skipped, not treated
    as an untraceable system disk (which would refuse to run).
    """

    env = make_env(
        mounts={
            "/": "/dev/sda2",
            "/proc": "proc",
            "/dev": "devtmpfs",
            "/sys/fs/cgroup": "cgroup2",
            "/run/netns/x": "nsfs[net:[4026532]]",
            "/nix/store": "overlay",
            "/srv/scratch": "/run/scratch-dir",
        },
        stacks={"/dev/sda2": ["/dev/sda2 part", "/dev/sda disk"]},
    )
    assert resolve_protected_disks(env) == frozenset({"/dev/sda"})


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


def _plan_targeting(device: str) -> Dict[str, object]:
    return {"partitions": {}, "disko": {"disk": {"boot": {"device": device}}}}


def test_apply_plan_refuses_a_plan_touching_a_protected_disk() -> None:
    """Runtime precondition at the destructive boundary (defence in depth)."""

    with pytest.raises(RuntimeError, match="protected"):
        apply.apply_plan(_plan_targeting("/dev/sda"), dry_run=True, protected_disks=frozenset({"/dev/sda"}))


def test_apply_plan_refuses_a_protected_disk_named_by_an_alias(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A loaded plan may name the disk via /dev/disk/by-id (Codex review)."""

    alias = "/dev/disk/by-id/usb-Stick_0123-0:0"
    monkeypatch.setattr(apply.os.path, "realpath", lambda p: "/dev/sda" if p == alias else p)
    with pytest.raises(RuntimeError, match="protected"):
        apply.apply_plan(_plan_targeting(alias), dry_run=True, protected_disks=frozenset({"/dev/sda"}))


def test_scan_does_not_count_protected_disks_as_existing_storage() -> None:
    """The boot medium's own data must not block auto-provisioning (§2.3)."""

    commands: Dict[Tuple[str, ...], CommandOutput] = {
        ("lsblk", "-dnpo", "NAME,TYPE,RM"): CommandOutput(stdout="/dev/mmcblk0 disk 0\n/dev/nvme0n1 disk 0\n"),
        ("lsblk", "-rno", "TYPE", "/dev/nvme0n1"): CommandOutput(stdout="disk\n"),
        ("wipefs", "-n", "/dev/nvme0n1"): CommandOutput(stdout=""),
    }
    env = DetectionEnvironment(
        run=lambda cmd: commands[tuple(cmd)],
        path_exists=lambda path: True,
        realpath=lambda path: path,
        read_cmdline=lambda: [],
    )
    found = storage_detection.scan_existing_storage(env, protected_disks=frozenset({"/dev/mmcblk0"}))
    assert found == []


def test_boot_disk_is_not_doubly_prefixed() -> None:
    """``lsblk -p`` prints ``/dev/sda``; the probe used to yield ``/dev/dev/sda``."""

    env = make_env(
        mounts={"/": "tmpfs", "/iso": "/dev/sda1"},
        stacks={"/dev/sda1": ["/dev/sda1 part", "/dev/sda disk"]},
    )
    assert storage_detection.resolve_boot_disk(env) == "/dev/sda"


def test_boot_time_gate_ignores_the_boot_stick() -> None:
    """The #306 spike: ISO on an RM=0 USB stick, empty target disk.

    ``pre-nixos-detect-storage`` gates boot-time auto-provisioning; it must
    report no existing storage (exit 1) so the empty target is provisioned
    (reqs §2.3: the boot medium does not count as existing storage).
    """

    base = make_env(
        mounts={"/": "tmpfs", "/iso": "/dev/sda1", "/nix/.ro-store": "/dev/loop0"},
        stacks={
            "/dev/sda1": ["/dev/sda1 part", "/dev/sda disk"],
            "/dev/loop0": ["/dev/loop0 loop"],
        },
    )
    scan = {
        ("lsblk", "-dnpo", "NAME,TYPE,RM"): CommandOutput(
            stdout="/dev/fd0 disk 1\n/dev/sda disk 0\n/dev/vda disk 0\n"
        ),
        ("lsblk", "-rno", "TYPE", "/dev/sda"): CommandOutput(stdout="disk\npart\npart\n"),
        ("wipefs", "-n", "/dev/sda"): CommandOutput(stdout="0x8001 iso9660\n"),
        ("lsblk", "-rno", "TYPE", "/dev/vda"): CommandOutput(stdout="disk\n"),
        ("wipefs", "-n", "/dev/vda"): CommandOutput(stdout=""),
    }
    env = DetectionEnvironment(
        run=lambda cmd: scan.get(tuple(cmd)) or base.run(cmd),
        path_exists=base.path_exists,
        realpath=base.realpath,
        read_cmdline=base.read_cmdline,
        is_block_device=base.is_block_device,
    )
    assert storage_detection.detection_exit_status(env) == 1
