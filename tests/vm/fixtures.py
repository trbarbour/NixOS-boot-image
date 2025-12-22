"""Shared fixtures and configuration helpers for VM-based tests.

This module is the landing zone for code extracted from
``tests/test_boot_image_vm.py``. It hosts tool/host probes, boot-image build
helpers, SSH key generation, and storage for common constants.
"""

from __future__ import annotations
import datetime
import importlib.util
import json
import os
import socket
import subprocess
import shutil
import time
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Dict, List, Optional

import pytest

from tests.vm.metadata import (
    append_run_ledger_entry,
    record_run_timings,
    write_boot_image_metadata,
)

if TYPE_CHECKING:  # pragma: no cover - type checking only
    from tests.vm.controller import BootImageVM

DEFAULT_SPAWN_TIMEOUT = 900
DEFAULT_LOGIN_TIMEOUT = 300
REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_LEDGER_PATH = REPO_ROOT / "notes" / "vm-run-ledger.jsonl"


@dataclass(frozen=True)
class SSHKeyPair:
    """Filesystem paths for a generated SSH key pair."""

    private_key: Path
    public_key: Path


@dataclass(frozen=True)
class BootImageBuild:
    """Metadata describing the built boot image artifact."""

    iso_path: Path
    store_path: Path
    deriver: Optional[str]
    nar_hash: Optional[str]
    root_key_fingerprint: str
    build_duration_seconds: Optional[float] = None


@dataclass
class RunTimings:
    """Wall-clock measurements captured during a VM integration test run."""

    build_seconds: Optional[float] = None
    boot_to_login_seconds: Optional[float] = None
    boot_to_ssh_seconds: Optional[float] = None
    total_seconds: Optional[float] = None
    started_at: Optional[datetime.datetime] = None
    completed_at: Optional[datetime.datetime] = None

    def to_metadata(self) -> Dict[str, object]:
        timings: Dict[str, object] = {}
        if self.started_at:
            timings["start"] = self.started_at.isoformat()
        if self.completed_at:
            timings["end"] = self.completed_at.isoformat()
        if self.build_seconds is not None:
            timings["build_seconds"] = round(self.build_seconds, 3)
        if self.boot_to_login_seconds is not None:
            timings["boot_to_login_seconds"] = round(self.boot_to_login_seconds, 3)
        if self.boot_to_ssh_seconds is not None:
            timings["boot_to_ssh_seconds"] = round(self.boot_to_ssh_seconds, 3)
        if self.total_seconds is not None:
            timings["total_seconds"] = round(self.total_seconds, 3)
        return timings


def _read_timeout_env(name: str, default: int) -> int:
    """Return a positive integer timeout configured via environment variable.

    The defaults are intentionally generous to avoid conflating slow boots with
    test hangs. Values are validated so that misconfiguration surfaces as an
    explicit error rather than silently disabling coverage.
    """

    value = os.environ.get(name)
    if value is None:
        return default
    try:
        parsed = int(value)
    except ValueError as exc:  # pragma: no cover - defensive configuration guard
        raise ValueError(f"{name} must be an integer value") from exc
    if parsed <= 0:  # pragma: no cover - defensive configuration guard
        raise ValueError(f"{name} must be greater than zero")
    return parsed


VM_SPAWN_TIMEOUT: int = _read_timeout_env("BOOT_IMAGE_VM_SPAWN_TIMEOUT", DEFAULT_SPAWN_TIMEOUT)
VM_LOGIN_TIMEOUT: int = _read_timeout_env("BOOT_IMAGE_VM_LOGIN_TIMEOUT", DEFAULT_LOGIN_TIMEOUT)


def _resolve_ledger_path() -> Optional[Path]:
    disabled = os.environ.get("BOOT_IMAGE_VM_DISABLE_LEDGER", "").strip().lower()
    if disabled in {"1", "true", "yes"}:
        return None
    override = os.environ.get("BOOT_IMAGE_VM_LEDGER_PATH")
    if override:
        return Path(override)
    return DEFAULT_LEDGER_PATH


def _require_executable(executable: str) -> str:
    """Ensure an executable exists in ``PATH`` or skip the invoking test."""

    path: Optional[str] = shutil.which(executable)
    if path is None:
        pytest.skip(f"required executable '{executable}' is not available in PATH")
    return path


def probe_qemu_version(executable: str) -> Optional[str]:
    """Return the first line of ``qemu --version`` output when available."""

    try:
        result = subprocess.run(
            [executable, "--version"],
            check=True,
            capture_output=True,
            text=True,
        )
    except (subprocess.CalledProcessError, OSError):
        return None
    output = (result.stdout or "").strip()
    if not output:
        output = (result.stderr or "").strip()
    if not output:
        return None
    return output.splitlines()[0]


@pytest.fixture(scope="session")
def _pexpect() -> "pexpect":
    if importlib.util.find_spec("pexpect") is None:  # pragma: no cover - env specific
        pytest.skip("pexpect is required for VM integration tests")

    import pexpect  # type: ignore
    return pexpect


@pytest.fixture(scope="session")
def nix_executable() -> str:
    return _require_executable("nix")


@pytest.fixture(scope="session")
def qemu_executable() -> str:
    return _require_executable("qemu-system-x86_64")


@pytest.fixture(scope="session")
def ssh_keygen_executable() -> str:
    return _require_executable("ssh-keygen")


@pytest.fixture(scope="session")
def ssh_executable() -> str:
    return _require_executable("ssh")


@pytest.fixture(scope="session")
def boot_ssh_key_pair(
    tmp_path_factory: pytest.TempPathFactory,
    ssh_keygen_executable: str,
) -> SSHKeyPair:
    key_dir = tmp_path_factory.mktemp("boot-image-ssh-key")
    private_key = key_dir / "id_ed25519"
    public_key = key_dir / "id_ed25519.pub"
    subprocess.run(
        [
            ssh_keygen_executable,
            "-t",
            "ed25519",
            "-N",
            "",
            "-C",
            "boot-image-vm-test",
            "-f",
            str(private_key),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return SSHKeyPair(private_key=private_key, public_key=public_key)


@pytest.fixture(scope="session")
def ssh_forward_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _resolve_iso_path(store_path: Path) -> Path:
    if store_path.is_file() and store_path.suffix == ".iso":
        return store_path
    iso_candidates = sorted(store_path.rglob("*.iso"))
    if not iso_candidates:
        raise AssertionError(
            f"no ISO images found under {store_path}; nix output was {store_path}"
        )
    if len(iso_candidates) > 1:
        raise AssertionError(
            "multiple ISO images discovered; unable to determine boot image uniquely: "
            + ", ".join(str(candidate) for candidate in iso_candidates)
        )
    return iso_candidates[0]


@pytest.fixture(scope="session")
def boot_image_build(
    nix_executable: str,
    boot_ssh_key_pair: SSHKeyPair,
    ssh_keygen_executable: str,
) -> BootImageBuild:
    env = os.environ.copy()
    env["PRE_NIXOS_ROOT_KEY"] = str(boot_ssh_key_pair.public_key)
    build_started = time.perf_counter()
    result = subprocess.run(
        [
            nix_executable,
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
    build_duration = time.perf_counter() - build_started
    paths = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    if not paths:
        raise AssertionError("nix build did not return a store path")
    store_path = Path(paths[-1])
    iso_path = _resolve_iso_path(store_path)

    info_proc = subprocess.run(
        [
            nix_executable,
            "path-info",
            "--json",
            str(store_path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    deriver: Optional[str] = None
    nar_hash: Optional[str] = None
    info_text = info_proc.stdout.strip()
    if info_text:
        info_json = json.loads(info_text)
        if isinstance(info_json, list):
            info_entries: List[Dict[str, str]] = info_json
        elif isinstance(info_json, dict):
            info_entries = [value for value in info_json.values() if isinstance(value, dict)]
        else:
            info_entries = []

        if info_entries:
            entry = info_entries[0]
            deriver = entry.get("deriver")
            nar_hash = entry.get("narHash")

    fingerprint_proc = subprocess.run(
        [
            ssh_keygen_executable,
            "-lf",
            str(boot_ssh_key_pair.public_key),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    fingerprint_lines = [
        line.strip() for line in fingerprint_proc.stdout.splitlines() if line.strip()
    ]
    fingerprint = fingerprint_lines[0] if fingerprint_lines else ""

    return BootImageBuild(
        iso_path=iso_path,
        store_path=store_path,
        deriver=deriver,
        nar_hash=nar_hash,
        root_key_fingerprint=fingerprint,
        build_duration_seconds=build_duration,
    )


@pytest.fixture(scope="session")
def boot_image_iso(boot_image_build: BootImageBuild) -> Path:
    return boot_image_build.iso_path


@pytest.fixture(scope="session")
def vm_disk_image(tmp_path_factory: pytest.TempPathFactory) -> Path:
    disk_dir = tmp_path_factory.mktemp("boot-image-disk")
    disk_path = disk_dir / "disk.img"
    with disk_path.open("wb") as handle:
        handle.truncate(4 * 1024 * 1024 * 1024)
    return disk_path


@pytest.fixture(scope="session")
def boot_image_vm(
    _pexpect: "pexpect",
    qemu_executable: str,
    boot_image_build: BootImageBuild,
    vm_disk_image: Path,
    tmp_path_factory: pytest.TempPathFactory,
    ssh_executable: str,
    ssh_forward_port: int,
    request: pytest.FixtureRequest,
) -> "BootImageVM":
    from tests.vm.controller import BootImageVM

    log_dir = tmp_path_factory.mktemp("boot-image-logs")
    log_path = log_dir / "serial.log"
    harness_log_path = log_dir / "harness.log"
    metadata_path = log_dir / "metadata.json"
    ledger_path = _resolve_ledger_path()
    harness_log_path.write_text("", encoding="utf-8")
    log_handle = log_path.open("w", encoding="utf-8")
    invocation_params = getattr(request.config, "invocation_params", None)
    invocation_args = (
        list(invocation_params.args)
        if invocation_params and invocation_params.args is not None
        else []
    )

    run_timings = RunTimings(
        build_seconds=boot_image_build.build_duration_seconds,
        started_at=datetime.datetime.now(datetime.timezone.utc),
    )

    cmd = [
        qemu_executable,
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
        str(boot_image_build.iso_path),
        "-drive",
        f"file={vm_disk_image},if=virtio,format=raw",
        "-device",
        "virtio-rng-pci",
        "-netdev",
        f"user,id=net0,hostfwd=tcp:127.0.0.1:{ssh_forward_port}-:22",
        "-device",
        "virtio-net-pci,netdev=net0",
    ]
    qemu_version = probe_qemu_version(qemu_executable)
    write_boot_image_metadata(
        metadata_path,
        artifact=boot_image_build,
        harness_log=harness_log_path,
        serial_log=log_path,
        qemu_command=cmd,
        qemu_version=qemu_version,
        disk_image=vm_disk_image,
        ssh_host="127.0.0.1",
        ssh_port=ssh_forward_port,
        ssh_executable=ssh_executable,
        run_timings=run_timings,
    )
    record_run_timings(metadata_path, run_timings=run_timings)

    child = _pexpect.spawn(
        cmd[0],
        cmd[1:],
        encoding="utf-8",
        codec_errors="ignore",
        timeout=VM_SPAWN_TIMEOUT,
    )
    child.logfile = log_handle
    debug_enabled = bool(request.config.getoption("boot_image_debug"))
    initial_failures = request.session.testsfailed
    vm: Optional[BootImageVM] = None
    debug_session_started = False
    total_started_at = time.perf_counter()
    boot_started_at = total_started_at
    run_outcome = "unknown"

    def _log_debug(message: str) -> None:
        timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat()
        with harness_log_path.open("a", encoding="utf-8") as handle:
            handle.write(f"[{timestamp}] {message}\n")

    try:
        vm = BootImageVM(
            child=child,
            log_path=log_path,
            harness_log_path=harness_log_path,
            metadata_path=metadata_path,
            ssh_port=ssh_forward_port,
            ssh_host="127.0.0.1",
            ssh_executable=ssh_executable,
            artifact=boot_image_build,
            qemu_version=qemu_version,
            qemu_command=tuple(cmd),
            disk_image=vm_disk_image,
            run_timings=run_timings,
            boot_started_at=boot_started_at,
        )
        record_run_timings(metadata_path, run_timings=run_timings)
        try:
            yield vm
            run_outcome = (
                "failed"
                if request.session.testsfailed > initial_failures
                else "passed"
            )
        finally:
            should_debug = debug_enabled and (
                request.session.testsfailed > initial_failures
            )
            if should_debug and not debug_session_started:
                vm.interact()
                debug_session_started = True
    except Exception:
        if debug_enabled and not debug_session_started:
            if vm is not None:
                vm.interact()
            else:
                _log_debug(
                    "Entering interactive debug session (setup failure)"
                )
                try:
                    child.interact(escape_character=chr(29))
                finally:
                    _log_debug("Exited interactive debug session")
            debug_session_started = True
        run_outcome = "error"
        raise
    finally:
        run_timings.total_seconds = time.perf_counter() - total_started_at
        run_timings.completed_at = datetime.datetime.now(datetime.timezone.utc)
        record_run_timings(metadata_path, run_timings=run_timings)
        if ledger_path is not None:
            try:
                append_run_ledger_entry(
                    ledger_path,
                    metadata_path=metadata_path,
                    run_timings=run_timings,
                    harness_log=harness_log_path,
                    serial_log=log_path,
                    qemu_command=cmd,
                    qemu_version=qemu_version,
                    ssh_host="127.0.0.1",
                    ssh_port=ssh_forward_port,
                    invocation_args=invocation_args,
                    spawn_timeout=VM_SPAWN_TIMEOUT,
                    login_timeout=VM_LOGIN_TIMEOUT,
                    outcome=run_outcome,
                )
            except Exception:
                # Recording the ledger should never fail the test run.
                _log_debug(
                    "Failed to append VM run entry to the ledger; continuing",
                )
        if vm is not None:
            vm.shutdown()
        else:
            try:
                child.close(force=True)
            except Exception:
                pass
        log_handle.close()


__all__ = [
    "BootImageBuild",
    "RunTimings",
    "DEFAULT_LOGIN_TIMEOUT",
    "DEFAULT_LEDGER_PATH",
    "DEFAULT_SPAWN_TIMEOUT",
    "REPO_ROOT",
    "SSHKeyPair",
    "VM_LOGIN_TIMEOUT",
    "VM_SPAWN_TIMEOUT",
    "_pexpect",
    "_read_timeout_env",
    "_resolve_ledger_path",
    "_require_executable",
    "boot_image_build",
    "boot_image_iso",
    "boot_ssh_key_pair",
    "boot_image_vm",
    "nix_executable",
    "probe_qemu_version",
    "qemu_executable",
    "ssh_executable",
    "ssh_forward_port",
    "ssh_keygen_executable",
    "vm_disk_image",
]
