#!/usr/bin/env python3
"""Run the boot-image VM manually and capture investigative evidence."""

from __future__ import annotations

import argparse
import datetime
import json
import os
import shutil
import socket
import subprocess
import sys
from pathlib import Path
from typing import Iterable, Tuple

import pexpect

from tests.test_boot_image_vm import (
    BootImageBuild,
    BootImageVM,
    _resolve_iso_path,
    probe_qemu_version,
    write_boot_image_metadata,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = REPO_ROOT / "docs" / "work-notes" / "manual-debug"


def require_executable(name: str) -> str:
    path = shutil.which(name)
    if path is None:
        raise SystemExit(f"required executable '{name}' is not available in PATH")
    return path


def build_boot_image(public_key: Path) -> BootImageBuild:
    nix = require_executable("nix")
    ssh_keygen = require_executable("ssh-keygen")

    env = os.environ.copy()
    env["PRE_NIXOS_ROOT_KEY"] = str(public_key)

    build = subprocess.run(
        [
            nix,
            "build",
            ".#bootImage",
            "--impure",
            "--no-link",
            "--print-out-paths",
        ],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
        env=env,
    )
    paths = [line.strip() for line in build.stdout.splitlines() if line.strip()]
    if not paths:
        raise SystemExit("nix build did not produce a store path")
    store_path = Path(paths[-1])
    iso_path = _resolve_iso_path(store_path)

    info_proc = subprocess.run(
        [nix, "path-info", "--json", str(store_path)],
        check=True,
        capture_output=True,
        text=True,
    )
    info_text = info_proc.stdout.strip()
    deriver = None
    nar_hash = None
    if info_text:
        info_json = json.loads(info_text)
        if isinstance(info_json, list) and info_json:
            entry = info_json[0]
        elif isinstance(info_json, dict):
            entry = next(iter(info_json.values()), None)
        else:
            entry = None
        if isinstance(entry, dict):
            deriver = entry.get("deriver")
            nar_hash = entry.get("narHash")

    fingerprint_proc = subprocess.run(
        [ssh_keygen, "-lf", str(public_key)],
        check=True,
        capture_output=True,
        text=True,
    )
    fingerprint_lines = [
        line.strip()
        for line in fingerprint_proc.stdout.splitlines()
        if line.strip()
    ]
    fingerprint = fingerprint_lines[0] if fingerprint_lines else ""

    return BootImageBuild(
        iso_path=iso_path,
        store_path=store_path,
        deriver=deriver,
        nar_hash=nar_hash,
        root_key_fingerprint=fingerprint,
    )


def generate_ssh_keypair(output_dir: Path) -> Tuple[Path, Path]:
    ssh_keygen = require_executable("ssh-keygen")
    private_key = output_dir / "id_ed25519"
    public_key = output_dir / "id_ed25519.pub"
    subprocess.run(
        [
            ssh_keygen,
            "-t",
            "ed25519",
            "-N",
            "",
            "-C",
            "boot-image-vm-manual-debug",
            "-f",
            str(private_key),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return private_key, public_key


def allocate_ssh_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def ensure_output_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def prepare_disk_image(path: Path) -> Path:
    with path.open("wb") as handle:
        handle.truncate(4 * 1024 * 1024 * 1024)
    return path


def launch_vm(
    artifact: BootImageBuild,
    disk_image: Path,
    ssh_port: int,
    harness_log: Path,
    serial_log: Path,
    metadata_path: Path,
) -> Tuple[BootImageVM, "pexpect.spawn", object]:
    ssh = require_executable("ssh")
    qemu = require_executable("qemu-system-x86_64")

    harness_log.write_text("", encoding="utf-8")
    serial_handle = serial_log.open("w", encoding="utf-8")

    cmd = [
        qemu,
        "-m",
        "2048",
        "-smp",
        "2",
        "-display",
        "none",
        "-no-reboot",
        "-boot",
        "d",
        "-serial",
        "stdio",
        "-cdrom",
        str(artifact.iso_path),
        "-drive",
        f"file={disk_image},if=virtio,format=raw",
        "-device",
        "virtio-rng-pci",
        "-netdev",
        f"user,id=net0,hostfwd=tcp:127.0.0.1:{ssh_port}-:22",
        "-device",
        "virtio-net-pci,netdev=net0",
    ]

    qemu_version = probe_qemu_version(qemu)

    write_boot_image_metadata(
        metadata_path,
        artifact=artifact,
        harness_log=harness_log,
        serial_log=serial_log,
        qemu_command=cmd,
        qemu_version=qemu_version,
        disk_image=disk_image,
        ssh_host="127.0.0.1",
        ssh_port=ssh_port,
        ssh_executable=ssh,
    )

    child = pexpect.spawn(
        cmd[0],
        cmd[1:],
        encoding="utf-8",
        codec_errors="ignore",
        timeout=600,
    )
    child.logfile = serial_handle

    vm = BootImageVM(
        child=child,
        log_path=serial_log,
        harness_log_path=harness_log,
        metadata_path=metadata_path,
        ssh_port=ssh_port,
        ssh_host="127.0.0.1",
        ssh_executable=ssh,
        artifact=artifact,
        qemu_version=qemu_version,
        qemu_command=tuple(cmd),
        disk_image=disk_image,
    )
    return vm, child, serial_handle


def record_command(
    vm: BootImageVM,
    label: str,
    command: str,
    note: Path,
    *,
    timeout: int = 240,
) -> None:
    output = vm.run(command, timeout=timeout)
    with note.open("a", encoding="utf-8") as handle:
        handle.write(f"\n## {label}\n")
        handle.write("```shell\n")
        handle.write(f"{command}\n")
        handle.write("```\n")
        if output:
            handle.write("```\n")
            handle.write(output + "\n")
            handle.write("```\n")
        else:
            handle.write("_(no output)_\n")


def collect_evidence(vm: BootImageVM, note: Path) -> None:
    commands: Iterable[Tuple[str, str]] = (
        ("storage_status", "cat /run/pre-nixos/storage-status 2>/dev/null || true"),
        ("systemctl_status", "systemctl status pre-nixos --no-pager 2>&1 || true"),
        ("journalctl_pre_nixos", "journalctl --no-pager -u pre-nixos.service -b || true"),
        ("ps_pre_nixos", "ps -ef | grep pre-nixos || true"),
        ("networkctl", "networkctl status lan || true"),
        (
            "journalctl_networkd",
            "journalctl --no-pager -u systemd-networkd -b || true",
        ),
        ("ip_link", "ip -o link || true"),
        ("ip_addr", "ip -o -4 addr show dev lan 2>/dev/null || true"),
    )
    for label, command in commands:
        record_command(vm, label, command, note)


def write_header(note: Path, artifact: BootImageBuild, ssh_port: int, disk: Path) -> None:
    timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat()
    with note.open("w", encoding="utf-8") as handle:
        handle.write(f"Captured at {timestamp}\n")
        handle.write("\n")
        handle.write("## Artifact\n")
        handle.write("- ISO: " + str(artifact.iso_path) + "\n")
        handle.write("- Store path: " + str(artifact.store_path) + "\n")
        handle.write("- Deriver: " + str(artifact.deriver) + "\n")
        handle.write("- narHash: " + str(artifact.nar_hash) + "\n")
        handle.write(
            "- Embedded root key fingerprint: "
            + artifact.root_key_fingerprint
            + "\n"
        )
        handle.write(f"- SSH forward port: {ssh_port}\n")
        handle.write("- Disk image: " + str(disk) + "\n")


def parse_args(argv: Iterable[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Boot the debug image in QEMU and collect diagnostic evidence",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="Directory where logs and command output will be written",
    )
    parser.add_argument(
        "--skip-shutdown",
        action="store_true",
        help="Leave the VM running after evidence collection for manual investigation",
    )
    return parser.parse_args(list(argv))


def main(argv: Iterable[str]) -> int:
    args = parse_args(argv)
    output_dir = ensure_output_dir(args.output_dir)

    private_key, public_key = generate_ssh_keypair(output_dir)
    artifact = build_boot_image(public_key)

    disk_image = prepare_disk_image(output_dir / "disk.img")
    ssh_port = allocate_ssh_port()

    harness_log = output_dir / "harness.log"
    serial_log = output_dir / "serial.log"
    metadata_path = output_dir / "metadata.json"
    note_path = output_dir / "manual-debug-output.txt"

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
            metadata_path=metadata_path,
        )
        collect_evidence(vm, note_path)
        if not args.skip_shutdown:
            vm.shutdown()
        else:
            print("VM left running; use Ctrl-] to detach from the serial console.")
    finally:
        if args.skip_shutdown and vm is not None and vm.child.isalive():
            vm.interact()
        if vm is not None and not args.skip_shutdown:
            pass  # shutdown handled above
        if child is not None and (vm is None or not vm.child.isalive()):
            try:
                child.close()
            except Exception:
                pass
        if serial_handle is not None:
            serial_handle.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
