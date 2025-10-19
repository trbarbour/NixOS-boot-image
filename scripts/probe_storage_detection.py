#!/usr/bin/env python3
"""Probe the storage-detection path from inside the boot-image VM."""

from __future__ import annotations

import argparse
import datetime
from pathlib import Path
import sys
from typing import Iterable, Tuple

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.manual_vm_debug import (
    allocate_ssh_port,
    build_boot_image,
    ensure_output_dir,
    generate_ssh_keypair,
    launch_vm,
    prepare_disk_image,
    record_command,
    write_header,
)
from tests.test_boot_image_vm import BootImageVM


def default_output_dir() -> Path:
    timestamp = datetime.datetime.now(datetime.timezone.utc).strftime(
        "%Y-%m-%dT%H-%M-%SZ"
    )
    return (
        Path(__file__).resolve().parents[1]
        / "docs"
        / "work-notes"
        / f"{timestamp}-storage-detection-probe"
    )


def parse_args(argv: Iterable[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run storage-detection diagnostics inside the boot-image VM.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Directory for captured logs and command output.",
    )
    parser.add_argument(
        "--skip-shutdown",
        action="store_true",
        help="Leave the VM running for manual inspection after automated probes.",
    )
    return parser.parse_args(list(argv))


def run_probes(vm: BootImageVM, note: Path) -> None:
    commands: Tuple[Tuple[str, str], ...] = (
        ("pre_nixos_detect_storage", "pre-nixos-detect-storage"),
        ("pre_nixos_plan_only", "pre-nixos --plan-only"),
        ("storage_status", "cat /run/pre-nixos/storage-status 2>/dev/null || true"),
        (
            "disko_config",
            "cat /var/log/pre-nixos/disko-config.nix 2>/dev/null || true",
        ),
        (
            "running_disko_processes",
            "ps -ef | grep -E 'disko|wipefs' | grep -v grep || true",
        ),
        ("lsblk", "lsblk --output NAME,TYPE,SIZE,MOUNTPOINT"),
    )
    for label, command in commands:
        record_command(vm, label, command, note, timeout=600)


def main(argv: Iterable[str]) -> int:
    args = parse_args(argv)
    output_dir = ensure_output_dir(args.output_dir or default_output_dir())

    private_key, public_key = generate_ssh_keypair(output_dir)
    artifact = build_boot_image(public_key)

    disk_image = prepare_disk_image(output_dir / "disk.img")
    ssh_port = allocate_ssh_port()

    harness_log = output_dir / "harness.log"
    serial_log = output_dir / "serial.log"
    note_path = output_dir / "storage-detection-probe.md"

    write_header(note_path, artifact, ssh_port, disk_image)

    vm = None
    child = None
    serial_handle = None
    try:
        vm, child, serial_handle = launch_vm(
            artifact=artifact,
            disk_image=disk_image,
            ssh_port=ssh_port,
            harness_log=harness_log,
            serial_log=serial_log,
        )
        run_probes(vm, note_path)
        if not args.skip_shutdown:
            vm.shutdown()
        else:
            print("VM left running; attach manually if needed (Ctrl-] to detach).")
    finally:
        if args.skip_shutdown and vm is not None and vm.child.isalive():
            vm.interact()
        if vm is not None and not args.skip_shutdown:
            pass
        if child is not None and (vm is None or not vm.child.isalive()):
            try:
                child.close()
            except Exception:
                pass
        if serial_handle is not None:
            serial_handle.close()
    return 0


if __name__ == "__main__":
    import sys

    raise SystemExit(main(sys.argv[1:]))
