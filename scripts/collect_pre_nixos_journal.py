#!/usr/bin/env python3
"""Boot the pre-NixOS image and capture `journalctl -u pre-nixos.service`."""
from __future__ import annotations

import argparse
import os
import shutil
import socket
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tests.test_boot_image_vm import BootImageVM, _resolve_iso_path


def ensure_executable(name: str) -> Path:
    path = shutil.which(name)
    if path is None:
        raise RuntimeError(f"Required executable '{name}' not found in PATH")
    return Path(path)


def build_boot_image(pubkey: Path) -> Path:
    env = os.environ.copy()
    env["PRE_NIXOS_ROOT_KEY"] = str(pubkey)
    result = subprocess.run(
        [
            ensure_executable("nix"),
            "build",
            ".#bootImage",
            "--impure",
            "--no-link",
            "--print-out-paths",
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
        env=env,
    )
    paths = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    if not paths:
        raise RuntimeError("nix build did not produce an output path")
    return _resolve_iso_path(Path(paths[-1]))


def allocate_forward_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def run_qemu(iso_path: Path, disk_path: Path, ssh_port: int, serial_path: Path) -> BootImageVM:
    import pexpect

    qemu = ensure_executable("qemu-system-x86_64")
    ssh = ensure_executable("ssh")
    child = None
    log_handle = serial_path.open("w", encoding="utf-8")
    try:
        child = pexpect.spawn(
            str(qemu),
            [
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
                str(iso_path),
                "-drive",
                f"file={disk_path},if=virtio,format=raw",
                "-device",
                "virtio-rng-pci",
                "-netdev",
                f"user,id=net0,hostfwd=tcp:127.0.0.1:{ssh_port}-:22",
                "-device",
                "virtio-net-pci,netdev=net0",
            ],
            encoding="utf-8",
            codec_errors="ignore",
            timeout=600,
        )
        child.logfile = log_handle
        return BootImageVM(
            child=child,
            log_path=serial_path,
            ssh_port=ssh_port,
            ssh_host="127.0.0.1",
            ssh_executable=str(ssh),
        )
    except Exception:
        log_handle.close()
        if child is not None:
            child.close(force=True)
        raise


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--journal-output",
        type=Path,
        help="Path to write the captured journal; defaults to stdout",
    )
    parser.add_argument(
        "--serial-output",
        type=Path,
        help="Optional path to copy the serial console log",
    )
    parser.add_argument(
        "--iso-path",
        type=Path,
        help="Use an existing boot image ISO instead of building",
    )
    parser.add_argument(
        "--disk-size",
        type=int,
        default=4 * 1024 * 1024 * 1024,
        help="Disk image size in bytes (default: 4 GiB)",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()

    with tempfile.TemporaryDirectory(prefix="pre-nixos-journal-") as tmp_dir:
        tmp_path = Path(tmp_dir)
        if args.iso_path:
            iso_path = _resolve_iso_path(args.iso_path)
        else:
            key_dir = tmp_path / "ssh-key"
            key_dir.mkdir()
            private_key = key_dir / "id_ed25519"
            public_key = key_dir / "id_ed25519.pub"
            subprocess.run(
                [
                    ensure_executable("ssh-keygen"),
                    "-t",
                    "ed25519",
                    "-N",
                    "",
                    "-C",
                    "collect-pre-nixos-journal",
                    "-f",
                    str(private_key),
                ],
                check=True,
                capture_output=True,
                text=True,
            )

            iso_path = build_boot_image(public_key)

        disk_path = tmp_path / "disk.img"
        with disk_path.open("wb") as disk_handle:
            disk_handle.truncate(args.disk_size)

        ssh_port = allocate_forward_port()
        serial_path = tmp_path / "serial.log"
        vm = run_qemu(iso_path, disk_path, ssh_port, serial_path)

        try:
            journal = vm.collect_journal("pre-nixos.service")
        finally:
            vm.shutdown()

        if args.serial_output:
            shutil.copy(serial_path, args.serial_output)

        if args.journal_output:
            write_text(args.journal_output, journal + "\n")
        else:
            sys.stdout.write(journal)
            if not journal.endswith("\n"):
                sys.stdout.write("\n")
