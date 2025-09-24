"""Tests for detecting existing storage signatures."""

from __future__ import annotations

from typing import Callable, Dict, Sequence, Tuple

from pre_nixos.storage_detection import (
    CommandOutput,
    DetectionEnvironment,
    has_existing_storage,
    resolve_boot_disk,
)


CommandMap = Dict[Tuple[str, ...], CommandOutput]


def make_env(
    commands: CommandMap,
    *,
    path_exists: Callable[[str], bool] | None = None,
    realpath: Callable[[str], str] | None = None,
    read_cmdline: Callable[[], Sequence[str]] | None = None,
) -> DetectionEnvironment:
    def run(cmd: Sequence[str]) -> CommandOutput:
        key = tuple(cmd)
        if key not in commands:
            raise AssertionError(f"unexpected command invocation: {cmd}")
        return commands[key]

    return DetectionEnvironment(
        run=run,
        path_exists=path_exists or (lambda _path: False),
        realpath=realpath or (lambda path: path),
        read_cmdline=read_cmdline or (lambda: []),
    )


def test_detects_partitions_as_existing() -> None:
    commands = {
        ("lsblk", "-dnpo", "NAME,TYPE"): CommandOutput(
            stdout="/dev/sdb disk\n", returncode=0
        ),
        ("lsblk", "-rno", "TYPE", "/dev/sdb"): CommandOutput(
            stdout="disk\npart\n", returncode=0
        ),
        ("wipefs", "-n", "/dev/sdb"): CommandOutput(stdout="", returncode=0),
    }
    env = make_env(commands)
    assert has_existing_storage(env, boot_disk=None)


def test_detects_wipefs_signature_without_partitions() -> None:
    commands = {
        ("lsblk", "-dnpo", "NAME,TYPE"): CommandOutput(
            stdout="/dev/sdc disk\n", returncode=0
        ),
        ("lsblk", "-rno", "TYPE", "/dev/sdc"): CommandOutput(stdout="disk\n", returncode=0),
        (
            "wipefs",
            "-n",
            "/dev/sdc",
        ): CommandOutput(stdout="0x1234\tfilesystem", returncode=0),
    }
    env = make_env(commands)
    assert has_existing_storage(env, boot_disk=None)


def test_only_boot_disk_is_ignored() -> None:
    commands = {
        ("lsblk", "-npo", "PKNAME", "/dev/sda1"): CommandOutput(
            stdout="sda\n", returncode=0
        ),
        ("findmnt", "-n", "-o", "SOURCE", "/iso"): CommandOutput(stdout="", returncode=1),
        ("lsblk", "-dnpo", "NAME,TYPE"): CommandOutput(
            stdout="/dev/sda disk\n", returncode=0
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
    assert not has_existing_storage(env, boot_disk=boot_disk)

