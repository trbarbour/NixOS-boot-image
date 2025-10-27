#!/usr/bin/env python3
"""Collect sshd dependency evidence from a manual BootImageVM session."""

from __future__ import annotations

import argparse
import datetime
from pathlib import Path
import sys
from typing import Iterable, Tuple

import pexpect

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts import manual_vm_debug as manual  # type: ignore  # noqa: E402
from tests.test_boot_image_vm import (  # type: ignore  # noqa: E402
    BootImageBuild,
    BootImageVM as BaseBootImageVM,
    SHELL_PROMPT,
    probe_qemu_version,
    write_boot_image_metadata,
)

DEFAULT_PREFIX = REPO_ROOT / "docs" / "work-notes"
DEFAULT_SUFFIX = "sshd-dependency-audit"


class PatchedBootImageVM(BaseBootImageVM):
    """Boot image controller with a longer prompt configuration timeout."""

    def _set_shell_prompt(self) -> None:  # type: ignore[override]
        self.child.sendline(f"export PS1='{SHELL_PROMPT}'")
        self._expect_normalised([SHELL_PROMPT], timeout=240)
        self._log_step("Shell prompt configured for interaction (extended timeout)")


def _default_output_dir() -> Path:
    timestamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ")
    return DEFAULT_PREFIX / f"{timestamp}-{DEFAULT_SUFFIX}"


def parse_args(argv: Iterable[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Boot the debug VM and capture sshd dependency information.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help=(
            "Absolute directory path where artefacts will be written. "
            "Defaults to docs/work-notes/<timestamp>-sshd-dependency-audit."
        ),
    )
    parser.add_argument(
        "--skip-shutdown",
        action="store_true",
        help="Leave the VM running after evidence collection for manual inspection.",
    )
    return parser.parse_args(list(argv))


def launch_vm(
    artifact: BootImageBuild,
    disk_image: Path,
    ssh_port: int,
    harness_log: Path,
    serial_log: Path,
    metadata_path: Path,
) -> Tuple[PatchedBootImageVM, pexpect.spawn, object]:
    ssh = manual.require_executable("ssh")
    qemu = manual.require_executable("qemu-system-x86_64")

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

    vm = PatchedBootImageVM(
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


def record_command(note_path: Path, label: str, command: str, output: str) -> None:
    with note_path.open("a", encoding="utf-8") as handle:
        handle.write(f"\n## {label}\n")
        handle.write("```shell\n")
        handle.write(f"{command}\n")
        handle.write("```\n")
        if output.strip():
            handle.write("```\n")
            handle.write(output.strip() + "\n")
            handle.write("```\n")
        else:
            handle.write("_(no output)_\n")


def collect_evidence(vm: PatchedBootImageVM, note_path: Path) -> None:
    vm.run(":")
    commands: Iterable[Tuple[str, str, bool]] = (
        ("systemctl_list_dependencies_sshd", "systemctl list-dependencies sshd --no-pager", True),
        (
            "systemctl_list_dependencies_reverse_sshd",
            "systemctl list-dependencies --reverse sshd --no-pager",
            True,
        ),
        (
            "systemctl_status_secure_ssh",
            "systemctl status secure_ssh --no-pager",
            True,
        ),
        ("systemctl_status_sshd", "systemctl status sshd --no-pager", True),
        (
            "systemctl_show_wantedby_sshd",
            "systemctl show -p WantedBy sshd.service",
            True,
        ),
        (
            "journalctl_secure_ssh",
            "journalctl --no-pager -u secure_ssh -b",
            True,
        ),
    )
    for label, command, as_root in commands:
        run_command = command
        if as_root:
            run_command = f"{command} 2>&1 || true"
            output = vm.run_as_root(run_command, timeout=240)
        else:
            output = vm.run(command, timeout=240)
        record_command(note_path, label, command, output)


def main(argv: Iterable[str]) -> int:
    args = parse_args(argv)
    output_dir = args.output_dir.resolve() if args.output_dir else _default_output_dir().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    private_key, public_key = manual.generate_ssh_keypair(output_dir)
    artifact = manual.build_boot_image(public_key)
    disk_image = manual.prepare_disk_image(output_dir / "disk.img")
    ssh_port = manual.allocate_ssh_port()

    harness_log = output_dir / "harness.log"
    serial_log = output_dir / "serial.log"
    metadata_path = output_dir / "metadata.json"
    note_path = output_dir / "sshd-dependency-notes.md"

    manual.write_header(note_path, artifact, ssh_port, disk_image)

    vm: PatchedBootImageVM | None = None
    child: pexpect.spawn | None = None
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
        vm.wait_for_unit_inactive("pre-nixos", timeout=420)
        collect_evidence(vm, note_path)
        if not args.skip_shutdown:
            vm.shutdown()
        else:
            print("VM left running; use Ctrl-] to detach from the serial console.")
    except Exception:
        if vm is not None:
            try:
                vm.interact()
            except Exception:
                pass
        elif child is not None:
            try:
                child.interact(escape_character=chr(29))
            except Exception:
                pass
        raise
    finally:
        if vm is None and child is not None:
            try:
                child.close(force=True)
            except Exception:
                pass
        if serial_handle is not None:
            serial_handle.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
