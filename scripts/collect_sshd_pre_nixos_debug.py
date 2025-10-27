#!/usr/bin/env python3
"""Collect debug data for the sshd/pre-nixos dependency deadlock."""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

import pexpect

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tests.test_boot_image_vm import (  # type: ignore  # noqa: E402
    BootImageBuild,
    BootImageVM,
    SHELL_PROMPT,
    _resolve_iso_path,
    probe_qemu_version,
    write_boot_image_metadata,
)


def _run(cmd: List[str], *, env: Dict[str, str] | None = None, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        check=True,
        capture_output=True,
        text=True,
        cwd=str(cwd) if cwd else None,
        env=env,
    )


def build_boot_image(public_key: Path) -> BootImageBuild:
    env = os.environ.copy()
    env["PRE_NIXOS_ROOT_KEY"] = str(public_key)
    result = _run(
        [
            "nix",
            "build",
            ".#bootImage",
            "--impure",
            "--no-link",
            "--print-out-paths",
        ],
        env=env,
        cwd=REPO_ROOT,
    )
    store_paths = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    if not store_paths:
        raise RuntimeError("nix build did not return a store path")
    store_path = Path(store_paths[-1])
    iso_path = _resolve_iso_path(store_path)

    info_result = _run(["nix", "path-info", "--json", str(store_path)])
    info_json = info_result.stdout.strip()
    deriver = None
    nar_hash = None
    if info_json:
        parsed = json.loads(info_json)
        entries: List[Dict[str, str]]
        if isinstance(parsed, list):
            entries = parsed
        elif isinstance(parsed, dict):
            entries = [value for value in parsed.values() if isinstance(value, dict)]
        else:
            entries = []
        if entries:
            entry = entries[0]
            deriver = entry.get("deriver")
            nar_hash = entry.get("narHash")

    fingerprint_result = _run(["ssh-keygen", "-lf", str(public_key)])
    fingerprint_lines = [line.strip() for line in fingerprint_result.stdout.splitlines() if line.strip()]
    fingerprint = fingerprint_lines[0] if fingerprint_lines else ""

    return BootImageBuild(
        iso_path=iso_path,
        store_path=store_path,
        deriver=deriver,
        nar_hash=nar_hash,
        root_key_fingerprint=fingerprint,
    )


def generate_ssh_key(temp_dir: Path) -> tuple[Path, Path]:
    private_key = temp_dir / "id_ed25519"
    public_key = temp_dir / "id_ed25519.pub"
    _run(
        [
            "ssh-keygen",
            "-t",
            "ed25519",
            "-N",
            "",
            "-C",
            "boot-image-debug",
            "-f",
            str(private_key),
        ]
    )
    return private_key, public_key


def allocate_disk(temp_dir: Path) -> Path:
    disk = temp_dir / "disk.img"
    with disk.open("wb") as handle:
        handle.truncate(4 * 1024 * 1024 * 1024)
    return disk


def reserve_ssh_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def collect_outputs(vm: BootImageVM) -> Dict[str, str]:
    # Issue a no-op first to ensure any prompt reconfiguration artefacts are
    # flushed before we start capturing command output.
    vm.run(":")

    commands = {
        "systemctl_show_sshd": "systemctl show -p After sshd",
        "systemctl_list_jobs": "systemctl list-jobs",
        "systemctl_status_pre_nixos": "systemctl status pre-nixos --no-pager",
        "systemctl_status_sshd": "systemctl status sshd --no-pager",
        "journalctl_pre_nixos": "journalctl --no-pager -u pre-nixos.service -b",
        "networkctl_status_lan": "networkctl status lan",
        "storage_status": "cat /run/pre-nixos/storage-status 2>/dev/null || true",
    }
    outputs: Dict[str, str] = {}
    for key, command in commands.items():
        if command.startswith(("systemctl", "journalctl", "networkctl")):
            command = (
                "SYSTEMD_COLORS=0 SYSTEMD_PAGER='cat' SYSTEMD_LESS=FRSX "
                "PAGER=cat "
                + command
            )
        output_text = vm.run(command, timeout=240)
        if output_text and not output_text.endswith("\n"):
            output_text = output_text + "\n"
        outputs[key] = output_text
    return outputs


def ensure_prompt(vm: BootImageVM) -> None:
    vm.child.sendline(":")
    vm.child.expect(SHELL_PROMPT, timeout=60)


def collect_debug_data(output_dir: Path, public_key: Optional[Path] = None) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="boot-image-debug-") as temp_root:
        temp_path = Path(temp_root)

        generated_key = False
        if public_key is None:
            key_dir = temp_path / "key"
            key_dir.mkdir()
            _priv_key, pub_key_path = generate_ssh_key(key_dir)
            generated_key = True
        else:
            pub_key_path = public_key
            if not pub_key_path.exists():
                raise FileNotFoundError(f"public key not found: {pub_key_path}")

        pub_key_path = pub_key_path.resolve()

        public_key_text = Path(pub_key_path).read_text(encoding="utf-8").strip()
        build = build_boot_image(pub_key_path)

        disk_dir = temp_path / "disk"
        disk_dir.mkdir()
        disk = allocate_disk(disk_dir)

        log_dir = temp_path / "logs"
        log_dir.mkdir()
        harness_log = log_dir / "harness.log"
        harness_log.write_text("", encoding="utf-8")
        serial_log = log_dir / "serial.log"
        metadata_path = log_dir / "metadata.json"

        ssh_port = reserve_ssh_port()
        cmd = [
            "qemu-system-x86_64",
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
            str(build.iso_path),
            "-drive",
            f"file={disk},if=virtio,format=raw",
            "-device",
            "virtio-rng-pci",
            "-netdev",
            f"user,id=net0,hostfwd=tcp:127.0.0.1:{ssh_port}-:22",
            "-device",
            "virtio-net-pci,netdev=net0",
        ]

        qemu_version = probe_qemu_version(qemu)

        outputs: Dict[str, str] = {}
        failure: Optional[Dict[str, str]] = None
        child: Optional[pexpect.spawn] = None
        log_handle = None
        vm: Optional[BootImageVM] = None

        try:
            log_handle = serial_log.open("w", encoding="utf-8")
            write_boot_image_metadata(
                metadata_path,
                artifact=build,
                harness_log=harness_log,
                serial_log=serial_log,
                qemu_command=cmd,
                qemu_version=qemu_version,
                disk_image=disk,
                ssh_host="127.0.0.1",
                ssh_port=ssh_port,
                ssh_executable="ssh",
            )
            child = pexpect.spawn(
                cmd[0],
                cmd[1:],
                encoding="utf-8",
                codec_errors="ignore",
                timeout=600,
            )
            child.logfile = log_handle

            vm = BootImageVM(
                child=child,
                log_path=serial_log,
                harness_log_path=harness_log,
                metadata_path=metadata_path,
                ssh_port=ssh_port,
                ssh_host="127.0.0.1",
                ssh_executable="ssh",
                artifact=build,
                qemu_version=qemu_version,
            )

            ensure_prompt(vm)
            outputs = collect_outputs(vm)
        except Exception as exc:
            failure = {
                "type": exc.__class__.__name__,
                "message": str(exc),
            }
            raise
        finally:
            try:
                if vm is not None:
                    vm.shutdown()
                elif child is not None:
                    child.close(force=True)
            except Exception:
                if child is not None:
                    child.close(force=True)
            if log_handle is not None:
                log_handle.close()

            for name, content in outputs.items():
                (output_dir / f"{name}.txt").write_text(content, encoding="utf-8")
            if harness_log.exists():
                shutil.copy2(harness_log, output_dir / "harness.log")
            if serial_log.exists():
                shutil.copy2(serial_log, output_dir / "serial.log")
            diagnostics_dir = log_dir / "diagnostics"
            if diagnostics_dir.exists():
                shutil.copytree(
                    diagnostics_dir,
                    output_dir / "diagnostics",
                    dirs_exist_ok=True,
                )
            if metadata_path.exists():
                shutil.copy2(metadata_path, output_dir / "metadata.json")
            harness_metadata: Dict[str, Any] = {}
            if metadata_path.exists():
                harness_metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            metadata = {
                "boot_image_vm": harness_metadata,
                "iso_path": str(build.iso_path),
                "store_path": str(build.store_path),
                "deriver": build.deriver,
                "nar_hash": build.nar_hash,
                "root_key_fingerprint": build.root_key_fingerprint,
                "public_key": public_key_text,
                "public_key_path": str(pub_key_path),
                "public_key_generated": generated_key,
                "temporary_directory": str(temp_path),
                "failure": failure,
            }
            (output_dir / "metadata.json").write_text(
                json.dumps(metadata, indent=2), encoding="utf-8"
            )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=REPO_ROOT / "debug-output" / _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ"),
        help="Directory to store collected outputs",
    )
    parser.add_argument(
        "--public-key",
        type=Path,
        help=(
            "Use an existing SSH public key instead of generating a temporary key. "
            "Reusing a key allows nix to reuse the cached boot image build."
        ),
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    try:
        collect_debug_data(args.output_dir, args.public_key)
    except Exception as exc:
        print(
            f"Collection failed ({exc.__class__.__name__}: {exc}); logs preserved in {args.output_dir}",
            file=sys.stderr,
        )
        raise
    else:
        print(f"Collected debug artefacts in {args.output_dir}")


if __name__ == "__main__":
    main()
