"""Tests for detecting existing storage signatures."""

from __future__ import annotations

from typing import Callable, Dict, Sequence, Tuple

from pre_nixos.storage_detection import (
    CommandOutput,
    DetectionEnvironment,
    ExistingStorageDevice,
    detect_existing_storage,
    format_existing_storage_reasons,
    has_existing_storage,
    resolve_boot_disk,
    scan_existing_storage,
)


CommandMap = Dict[Tuple[str, ...], CommandOutput]


def make_env(
    commands: CommandMap,
    *,
    path_exists: Callable[[str], bool] | None = None,
    realpath: Callable[[str], str] | None = None,
    read_cmdline: Callable[[], Sequence[str]] | None = None,
) -> DetectionEnvironment:
    base_commands: CommandMap = {
        ("findmnt", "-n", "-o", "SOURCE", "/iso"): CommandOutput(
            stdout="", returncode=1
        ),
        (
            "findmnt",
            "-n",
            "-o",
            "SOURCE",
            "/run/archiso/bootmnt",
        ): CommandOutput(stdout="", returncode=1),
        ("findmnt", "-n", "-o", "SOURCE", "/nix/.ro-store"): CommandOutput(
            stdout="", returncode=1
        ),
        ("findmnt", "-nr", "-t", "squashfs", "-o", "SOURCE"): CommandOutput(
            stdout="", returncode=1
        ),
        ("findmnt", "-nr", "-t", "iso9660", "-o", "SOURCE"): CommandOutput(
            stdout="", returncode=1
        ),
    }
    merged_commands = {**base_commands, **commands}

    def run(cmd: Sequence[str]) -> CommandOutput:
        key = tuple(cmd)
        if key not in merged_commands:
            raise AssertionError(f"unexpected command invocation: {cmd}")
        return merged_commands[key]

    return DetectionEnvironment(
        run=run,
        path_exists=path_exists or (lambda _path: False),
        realpath=realpath or (lambda path: path),
        read_cmdline=read_cmdline or (lambda: []),
    )


def test_detects_partitions_as_existing() -> None:
    commands = {
        ("lsblk", "-dnpo", "NAME,TYPE,RM"): CommandOutput(
            stdout="/dev/sdb disk 0\n", returncode=0
        ),
        ("lsblk", "-rno", "TYPE", "/dev/sdb"): CommandOutput(
            stdout="disk\npart\n", returncode=0
        ),
        ("wipefs", "-n", "/dev/sdb"): CommandOutput(stdout="", returncode=0),
    }
    env = make_env(commands)
    devices = scan_existing_storage(env, boot_disk=None)
    assert devices == [ExistingStorageDevice(device="/dev/sdb", reasons=("partitions",))]
    assert has_existing_storage(env, boot_disk=None)


def test_detects_wipefs_signature_without_partitions() -> None:
    commands = {
        ("lsblk", "-dnpo", "NAME,TYPE,RM"): CommandOutput(
            stdout="/dev/sdc disk 0\n", returncode=0
        ),
        ("lsblk", "-rno", "TYPE", "/dev/sdc"): CommandOutput(stdout="disk\n", returncode=0),
        (
            "wipefs",
            "-n",
            "/dev/sdc",
        ): CommandOutput(stdout="0x1234\tfilesystem", returncode=0),
    }
    env = make_env(commands)
    devices = scan_existing_storage(env, boot_disk=None)
    assert devices == [ExistingStorageDevice(device="/dev/sdc", reasons=("signatures",))]
    assert has_existing_storage(env, boot_disk=None)


def test_only_boot_disk_is_ignored() -> None:
    commands = {
        ("lsblk", "-npo", "PKNAME", "/dev/sda1"): CommandOutput(
            stdout="sda\n", returncode=0
        ),
        ("findmnt", "-n", "-o", "SOURCE", "/iso"): CommandOutput(stdout="", returncode=1),
        ("lsblk", "-dnpo", "NAME,TYPE,RM"): CommandOutput(
            stdout="/dev/sda disk 0\n", returncode=0
        ),
    }
    known_paths = {"/dev/disk/by-label/BOOT", "/dev/sda1", "/dev/sda"}

    def path_exists(path: str) -> bool:
        return path in known_paths

    def realpath(path: str) -> str:
        if path == "/dev/disk/by-label/BOOT":
            return "/dev/sda1"
        return path

    env = make_env(
        commands,
        path_exists=path_exists,
        realpath=realpath,
        read_cmdline=lambda: ["boot=LABEL=BOOT"],
    )
    boot_disk = resolve_boot_disk(env)
    assert boot_disk == "/dev/sda"
    assert scan_existing_storage(env, boot_disk=boot_disk) == []
    assert not has_existing_storage(env, boot_disk=boot_disk)


def test_missing_device_during_inspection_is_ignored() -> None:
    commands = {
        ("lsblk", "-dnpo", "NAME,TYPE,RM"): CommandOutput(
            stdout="/dev/sdd disk 0\n", returncode=0
        ),
        ("lsblk", "-rno", "TYPE", "/dev/sdd"): CommandOutput(stdout="", returncode=32),
        ("wipefs", "-n", "/dev/sdd"): CommandOutput(stdout="", returncode=32),
    }
    env = make_env(commands)
    assert scan_existing_storage(env, boot_disk=None) == []
    assert not has_existing_storage(env, boot_disk=None)


def test_floppy_device_is_ignored_during_detection() -> None:
    """Legacy floppy controllers should not trigger detection errors."""

    commands = {
        ("lsblk", "-dnpo", "NAME,TYPE,RM"): CommandOutput(
            stdout="/dev/fd0 disk 1\n/dev/vda disk 0\n"
        ),
        ("lsblk", "-rno", "TYPE", "/dev/vda"): CommandOutput(stdout="disk\n"),
        ("wipefs", "-n", "/dev/vda"): CommandOutput(stdout=""),
    }

    env = make_env(commands, path_exists=lambda _path: True, realpath=lambda path: path)
    assert scan_existing_storage(env, boot_disk=None) == []
    assert not has_existing_storage(env, boot_disk=None)


def test_detects_multiple_reasons_for_device() -> None:
    commands = {
        ("lsblk", "-dnpo", "NAME,TYPE,RM"): CommandOutput(
            stdout="/dev/sde disk 0\n", returncode=0
        ),
        ("lsblk", "-rno", "TYPE", "/dev/sde"): CommandOutput(
            stdout="disk\npart\n", returncode=0
        ),
        (
            "wipefs",
            "-n",
            "/dev/sde",
        ): CommandOutput(stdout="0x2345\tlvm", returncode=0),
    }
    env = make_env(commands)
    devices = scan_existing_storage(env, boot_disk=None)
    assert devices == [
        ExistingStorageDevice(device="/dev/sde", reasons=("partitions", "signatures"))
    ]


def test_detect_existing_storage_excludes_boot_disk() -> None:
    commands = {
        ("lsblk", "-dnpo", "NAME,TYPE,RM"): CommandOutput(
            stdout="/dev/sda disk 0\n/dev/sdb disk 0\n", returncode=0
        ),
        ("lsblk", "-npo", "PKNAME", "/dev/sda1"): CommandOutput(
            stdout="sda\n", returncode=0
        ),
        ("lsblk", "-rno", "TYPE", "/dev/sdb"): CommandOutput(
            stdout="disk\npart\n", returncode=0
        ),
        ("wipefs", "-n", "/dev/sdb"): CommandOutput(
            stdout="0x2345\tlvm", returncode=0
        ),
        ("findmnt", "-n", "-o", "SOURCE", "/iso"): CommandOutput(stdout="", returncode=1),
    }

    known_paths = {"/dev/disk/by-label/BOOT", "/dev/sda1", "/dev/sda", "/dev/sdb"}

    def path_exists(path: str) -> bool:
        return path in known_paths

    def realpath(path: str) -> str:
        if path == "/dev/disk/by-label/BOOT":
            return "/dev/sda1"
        return path

    env = make_env(
        commands,
        path_exists=path_exists,
        realpath=realpath,
        read_cmdline=lambda: ["boot=LABEL=BOOT"],
    )

    devices = detect_existing_storage(env)
    assert devices == [
        ExistingStorageDevice(device="/dev/sdb", reasons=("partitions", "signatures"))
    ]


def test_detect_existing_storage_ignores_iso_label_source() -> None:
    commands = {
        ("findmnt", "-n", "-o", "SOURCE", "/iso"): CommandOutput(
            stdout="LABEL=NIXOS\\040MINIMAL\n", returncode=0
        ),
        ("lsblk", "-npo", "PKNAME", "/dev/sdc"): CommandOutput(stdout="\n", returncode=0),
        ("lsblk", "-dnpo", "NAME,TYPE,RM"): CommandOutput(
            stdout="/dev/sdc disk 1\n/dev/nvme0n1 disk 0\n", returncode=0
        ),
        ("lsblk", "-rno", "TYPE", "/dev/nvme0n1"): CommandOutput(
            stdout="disk\npart\n", returncode=0
        ),
        ("wipefs", "-n", "/dev/nvme0n1"): CommandOutput(
            stdout="0x2345\tlvm", returncode=0
        ),
    }

    known_paths = {
        "/dev/sdc",
        "/dev/disk/by-label/NIXOS MINIMAL",
        "/dev/disk/by-label/NIXOS\\x20MINIMAL",
    }

    def path_exists(path: str) -> bool:
        return path in known_paths

    def realpath(path: str) -> str:
        if path in {
            "/dev/disk/by-label/NIXOS MINIMAL",
            "/dev/disk/by-label/NIXOS\\x20MINIMAL",
        }:
            return "/dev/sdc"
        return path

    env = make_env(commands, path_exists=path_exists, realpath=realpath)
    boot_disk = resolve_boot_disk(env)
    assert boot_disk == "/dev/sdc"

    devices = detect_existing_storage(env)
    assert devices == [
        ExistingStorageDevice(device="/dev/nvme0n1", reasons=("partitions", "signatures"))
    ]


def test_scan_existing_storage_skips_removable_when_boot_unknown() -> None:
    commands = {
        ("lsblk", "-dnpo", "NAME,TYPE,RM"): CommandOutput(
            stdout="/dev/sdb disk 1\n/dev/nvme0n1 disk 0\n", returncode=0
        ),
        ("lsblk", "-rno", "TYPE", "/dev/nvme0n1"): CommandOutput(
            stdout="disk\npart\n", returncode=0
        ),
        ("wipefs", "-n", "/dev/nvme0n1"): CommandOutput(
            stdout="0x2345\tlvm", returncode=0
        ),
    }
    env = make_env(commands)
    devices = scan_existing_storage(env, boot_disk=None)
    assert devices == [
        ExistingStorageDevice(device="/dev/nvme0n1", reasons=("partitions", "signatures"))
    ]


def test_format_existing_storage_reasons() -> None:
    assert format_existing_storage_reasons(()) == "unknown"
    assert (
        format_existing_storage_reasons(("partitions", "signatures"))
        == "partitions, signatures"
    )


def test_logs_boot_resolution_and_device_filtering(monkeypatch) -> None:
    events: list[tuple[str, dict[str, object]]] = []

    def record_event(event: str, **fields: object) -> None:
        events.append((event, fields))

    commands = {
        ("findmnt", "-n", "-o", "SOURCE", "/run/archiso/bootmnt"): CommandOutput(
            stdout="/dev/sda1\n", returncode=0
        ),
        ("lsblk", "-npo", "PKNAME", "/dev/sda1"): CommandOutput(
            stdout="sda\n", returncode=0
        ),
        ("lsblk", "-dnpo", "NAME,TYPE,RM"): CommandOutput(
            stdout="/dev/sda disk 0\n/dev/nvme0n1 disk 0\n", returncode=0
        ),
        ("lsblk", "-rno", "TYPE", "/dev/nvme0n1"): CommandOutput(
            stdout="disk\npart\n", returncode=0
        ),
        ("wipefs", "-n", "/dev/nvme0n1"): CommandOutput(
            stdout="0x2345\tlvm", returncode=0
        ),
    }

    known_paths = {"/dev/sda1", "/dev/sda", "/dev/nvme0n1"}

    def path_exists(path: str) -> bool:
        return path in known_paths

    env = make_env(commands, path_exists=path_exists, realpath=lambda path: path)
    monkeypatch.setattr("pre_nixos.storage_detection.log_event", record_event)

    devices = detect_existing_storage(env)

    boot_events = [event for event in events if event[0] == "pre_nixos.storage.resolve_boot_disk"]
    assert boot_events
    boot_fields = boot_events[-1][1]
    assert boot_fields["boot_disk"] == "/dev/sda"

    device_events = [event for event in events if event[0] == "pre_nixos.storage.device_filtered"]
    assert any("boot_disk" in record[1].get("reasons", []) for record in device_events)

    detection_events = [
        event for event in events if event[0] == "pre_nixos.storage.device_detected"
    ]
    assert detection_events
    assert detection_events[0][1]["reasons"] == ["partitions", "signatures"]

    assert devices == [
        ExistingStorageDevice(device="/dev/nvme0n1", reasons=("partitions", "signatures"))
    ]
