#!/usr/bin/env python3
"""Boot the pre-NixOS image and capture `journalctl -u pre-nixos.service`."""
from __future__ import annotations

import argparse
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Iterable

REPO_ROOT = Path(__file__).resolve().parents[1]

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.manual_vm_debug import (  # noqa: E402
    DEFAULT_DISK_SIZE_BYTES,
    allocate_ssh_port,
    build_boot_image,
    describe_boot_image,
    generate_ssh_keypair,
    launch_vm,
    prepare_disk_image,
)


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def parse_args(argv: Iterable[str]) -> argparse.Namespace:
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
        help="Use an existing boot image (its Nix store path) instead of building",
    )
    parser.add_argument(
        "--disk-size",
        type=int,
        default=DEFAULT_DISK_SIZE_BYTES,
        help="Disk image size in bytes (default: 4 GiB)",
    )
    return parser.parse_args(list(argv))


def main(argv: Iterable[str]) -> int:
    args = parse_args(argv)

    with tempfile.TemporaryDirectory(prefix="pre-nixos-journal-") as tmp_dir:
        tmp_path = Path(tmp_dir)
        if args.iso_path:
            artifact = describe_boot_image(args.iso_path, public_key=None)
        else:
            key_dir = tmp_path / "ssh-key"
            key_dir.mkdir()
            _private_key, public_key = generate_ssh_keypair(key_dir)
            artifact = build_boot_image(public_key)

        disk_image = prepare_disk_image(tmp_path / "disk.img", args.disk_size)
        serial_log = tmp_path / "serial.log"

        vm, child, serial_handle = launch_vm(
            artifact=artifact,
            disk_image=disk_image,
            ssh_port=allocate_ssh_port(),
            harness_log=tmp_path / "harness.log",
            serial_log=serial_log,
            metadata_path=tmp_path / "metadata.json",
        )
        try:
            journal = vm.collect_journal("pre-nixos.service")
        finally:
            try:
                vm.shutdown()
            finally:
                if child.isalive():
                    child.close(force=True)
                serial_handle.close()

        if args.serial_output:
            shutil.copy(serial_log, args.serial_output)

        if args.journal_output:
            write_text(args.journal_output, journal + "\n")
        else:
            sys.stdout.write(journal)
            if not journal.endswith("\n"):
                sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
