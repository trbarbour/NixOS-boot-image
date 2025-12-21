"""Shared fixtures and configuration helpers for VM-based tests.

This module is the landing zone for code extracted from
``tests/test_boot_image_vm.py``. It hosts tool/host probes, boot-image build
helpers, SSH key generation, and storage for common constants.
"""

from __future__ import annotations
import importlib.util
import json
import os
import socket
import subprocess
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

import pytest

DEFAULT_SPAWN_TIMEOUT = 900
DEFAULT_LOGIN_TIMEOUT = 300
REPO_ROOT = Path(__file__).resolve().parents[2]


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


__all__ = [
    "BootImageBuild",
    "DEFAULT_LOGIN_TIMEOUT",
    "DEFAULT_SPAWN_TIMEOUT",
    "REPO_ROOT",
    "SSHKeyPair",
    "VM_LOGIN_TIMEOUT",
    "VM_SPAWN_TIMEOUT",
    "_pexpect",
    "_read_timeout_env",
    "_require_executable",
    "boot_image_build",
    "boot_image_iso",
    "boot_ssh_key_pair",
    "nix_executable",
    "probe_qemu_version",
    "qemu_executable",
    "ssh_executable",
    "ssh_forward_port",
    "ssh_keygen_executable",
    "vm_disk_image",
]
