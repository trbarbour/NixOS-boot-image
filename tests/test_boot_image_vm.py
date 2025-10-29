"""Integration tests that exercise the boot image inside a virtual machine."""

from __future__ import annotations

import datetime
import json
import os
import re
import shlex
import shutil
import socket
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

import pytest

try:
    import pexpect
except ImportError:  # pragma: no cover - handled by pytest skip
    pexpect = None  # type: ignore


REPO_ROOT = Path(__file__).resolve().parents[1]
SHELL_PROMPT = "PRE-NIXOS> "


def _read_timeout_env(name: str, default: int) -> int:
    """Return a positive integer timeout configured via environment variable."""

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


VM_SPAWN_TIMEOUT = _read_timeout_env("BOOT_IMAGE_VM_SPAWN_TIMEOUT", 600)
VM_LOGIN_TIMEOUT = _read_timeout_env("BOOT_IMAGE_VM_LOGIN_TIMEOUT", 600)

ANSI_ESCAPE_PATTERN = re.compile(
    r"""
    \x1B(
        \[[0-?]*[ -/]*[@-~]      # CSI sequences, including bracketed paste toggles
        |\][^\x07]*(?:\x07|\x1b\\)  # OSC sequences for terminal title updates
        |P[^\x07\x1b]*(?:\x07|\x1b\\)  # DCS sequences
        |[@-Z\\-_]                 # 2-character sequences (e.g. ESCc)
        |_[^\x07]*(?:\x07|\x1b\\)    # APC sequences
        |\^[^\x07]*(?:\x07|\x1b\\)   # PM sequences
    )
    """,
    re.VERBOSE,
)


DMESG_CAPTURE_COMMAND = "dmesg --color=never 2>&1 || dmesg 2>&1 || true"


def _require_executable(executable: str) -> str:
    path = shutil.which(executable)
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
    if pexpect is None:  # pragma: no cover - environment specific
        pytest.skip("pexpect is required for VM integration tests")
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


@dataclass(frozen=True)
class SSHKeyPair:
    """Filesystem paths for a generated SSH key pair."""

    private_key: Path
    public_key: Path


def write_boot_image_metadata(
    metadata_path: Path,
    *,
    artifact: "BootImageBuild",
    harness_log: Path,
    serial_log: Path,
    qemu_command: List[str],
    qemu_version: Optional[str] = None,
    disk_image: Path,
    ssh_host: str,
    ssh_port: int,
    ssh_executable: str,
) -> None:
    """Persist structured metadata describing the active BootImageVM session."""

    log_dir = metadata_path.parent
    diagnostics_dir = log_dir / "diagnostics"
    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    metadata = {
        "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "artifact": {
            "iso_path": str(artifact.iso_path),
            "store_path": str(artifact.store_path),
            "deriver": artifact.deriver,
            "nar_hash": artifact.nar_hash,
            "root_key_fingerprint": artifact.root_key_fingerprint,
        },
        "logs": {
            "harness": str(harness_log),
            "serial": str(serial_log),
        },
        "qemu": {
            "command": qemu_command,
            "disk_image": str(disk_image),
        },
        "ssh": {
            "host": ssh_host,
            "port": ssh_port,
            "executable": ssh_executable,
        },
        "diagnostics": {
            "directory": str(diagnostics_dir),
            "artifacts": [],
        },
    }
    if qemu_version:
        metadata["qemu"]["version"] = qemu_version
    metadata_path.write_text(
        json.dumps(metadata, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def record_boot_image_diagnostic(
    metadata_path: Path,
    *,
    label: str,
    path: Path,
) -> None:
    """Append a diagnostic artifact entry to ``metadata.json`` when available."""

    try:
        raw_metadata = metadata_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return

    if not raw_metadata.strip():
        return

    try:
        metadata = json.loads(raw_metadata)
    except json.JSONDecodeError:
        return

    diagnostics = metadata.setdefault("diagnostics", {})
    artifacts = diagnostics.setdefault("artifacts", [])
    entry = {"label": label, "path": str(path)}
    if any(existing.get("path") == entry["path"] for existing in artifacts):
        return

    artifacts.append(entry)
    metadata_path.write_text(
        json.dumps(metadata, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


@dataclass(frozen=True)
class BootImageBuild:
    """Metadata describing the built boot image artifact."""

    iso_path: Path
    store_path: Path
    deriver: Optional[str]
    nar_hash: Optional[str]
    root_key_fingerprint: str


@dataclass
class BootImageVM:
    """Minimal controller for interacting with the boot image via serial and SSH."""

    child: "pexpect.spawn"
    log_path: Path
    harness_log_path: Path
    metadata_path: Path
    ssh_port: int
    ssh_host: str
    ssh_executable: str
    artifact: BootImageBuild
    qemu_version: Optional[str] = None
    qemu_command: Optional[Tuple[str, ...]] = None
    disk_image: Optional[Path] = None
    _transcript: List[str] = field(default_factory=list, init=False, repr=False)
    _has_root_privileges: bool = field(default=False, init=False, repr=False)
    _log_dir: Path = field(init=False, repr=False)
    _diagnostic_dir: Path = field(init=False, repr=False)
    _diagnostic_counter: int = field(default=0, init=False, repr=False)
    _escalation_diagnostics: List[Tuple[str, Path]] = field(
        default_factory=list, init=False, repr=False
    )

    def __post_init__(self) -> None:
        self._log_dir = self.harness_log_path.parent
        self._diagnostic_dir = self._log_dir / "diagnostics"
        self._diagnostic_dir.mkdir(exist_ok=True)
        if self.qemu_command is not None and not isinstance(self.qemu_command, tuple):
            self.qemu_command = tuple(self.qemu_command)
        self._log_step(
            "Boot image artifact metadata",
            body="\n".join(self._format_artifact_metadata()),
        )
        self._log_step(f"Harness metadata written to {self.metadata_path}")
        self._login()

    def _format_artifact_metadata(self) -> List[str]:
        metadata = [
            f"ISO: {self.artifact.iso_path}",
            f"Store path: {self.artifact.store_path}",
        ]
        if self.artifact.deriver:
            metadata.append(f"Deriver: {self.artifact.deriver}")
        if self.artifact.nar_hash:
            metadata.append(f"NAR hash: {self.artifact.nar_hash}")
        metadata.append(
            "Embedded root key fingerprint: "
            f"{self.artifact.root_key_fingerprint}"
        )
        if self.qemu_version:
            metadata.append(f"QEMU version: {self.qemu_version}")
        if self.disk_image is not None:
            metadata.append(f"Disk image: {self.disk_image}")
        if self.qemu_command:
            try:
                command_repr = shlex.join(self.qemu_command)
            except AttributeError:
                command_repr = " ".join(self.qemu_command)
            metadata.append(f"QEMU command: {command_repr}")
        return metadata

    def _log_step(self, message: str, body: Optional[str] = None) -> None:
        timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat()
        entry = f"[{timestamp}] {message}"
        self._transcript.append(entry)
        with self.harness_log_path.open("a", encoding="utf-8") as handle:
            handle.write(entry + "\n")
            if body is not None:
                lines = body.splitlines()
                if not lines:
                    handle.write(f"[{timestamp}]   <no output>\n")
                else:
                    for line in lines:
                        handle.write(f"[{timestamp}]   {line}\n")

    def _write_diagnostic_artifact(
        self,
        slug: str,
        content: str,
        *,
        extension: str = ".log",
        metadata_label: Optional[str] = None,
    ) -> Path:
        safe_slug = re.sub(r"[^A-Za-z0-9_-]", "-", slug).strip("-")
        if not safe_slug:
            safe_slug = "diagnostic"
        if not extension.startswith("."):
            extension = "." + extension
        self._diagnostic_counter += 1
        filename = f"{safe_slug}-{self._diagnostic_counter:02d}{extension}"
        path = self._diagnostic_dir / filename
        if content and not content.endswith("\n"):
            to_write = content + "\n"
        else:
            to_write = content
        path.write_text(to_write, encoding="utf-8")
        self._log_step(f"Diagnostic artifact written to {path}")
        if metadata_label:
            try:
                record_boot_image_diagnostic(
                    self.metadata_path, label=metadata_label, path=path
                )
            except Exception as exc:  # pragma: no cover - defensive logging
                self._log_step(
                    "Failed to record diagnostic artifact in metadata",
                    body=repr(exc),
                )
        return path

    def _capture_dmesg(self, context: str) -> Tuple[str, Path]:
        """Capture the kernel ring buffer for diagnostic purposes."""

        output = self.run(DMESG_CAPTURE_COMMAND, timeout=240)
        self._log_step(f"Captured dmesg after {context}", body=output)
        slug_context = re.sub(r"[^A-Za-z0-9_-]+", "-", context.lower()).strip("-")
        if slug_context:
            slug = f"dmesg-{slug_context}"
        else:
            slug = "dmesg"
        label = f"dmesg ({context})"
        path = self._write_diagnostic_artifact(
            slug,
            output,
            metadata_label=label,
        )
        return (label, path)

    def _snapshot_transcript(self) -> int:
        """Return the index of the next transcript entry for later slicing."""

        return len(self._transcript)

    def _clear_escalation_diagnostics(self) -> None:
        """Remove any recorded escalation diagnostics after a successful login."""

        if self._escalation_diagnostics:
            self._escalation_diagnostics.clear()

    def _capture_escalation_failure(
        self,
        *,
        slug: str,
        description: str,
        reason: str,
        transcript_start: int,
    ) -> None:
        """Persist a diagnostic transcript for a failed privilege escalation."""

        self._record_child_output()
        captured_entries = self._transcript[transcript_start:]
        transcript_body = "\n".join(captured_entries).strip()
        if not transcript_body:
            transcript_body = "<no transcript entries recorded>"
        captured_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
        content_lines = [
            f"Escalation method: {description}",
            f"Failure reason: {reason}",
            f"Captured at: {captured_at}",
            "",
            transcript_body,
        ]
        content = "\n".join(content_lines)
        path = self._write_diagnostic_artifact(
            f"{slug}-escalation-failure",
            content,
            extension=".txt",
            metadata_label=f"{description} escalation transcript",
        )
        label = f"{description} escalation transcript"
        if not any(existing_path == path for _, existing_path in self._escalation_diagnostics):
            self._escalation_diagnostics.append((label, path))

        serial_tail = self._read_serial_tail()
        if serial_tail:
            serial_body = "\n".join(serial_tail)
        else:
            serial_body = "<no serial log entries recorded>"
        serial_lines = [
            f"Escalation method: {description}",
            f"Failure reason: {reason}",
            f"Captured at: {captured_at}",
            "",
            serial_body,
        ]
        serial_content = "\n".join(serial_lines)
        serial_path = self._write_diagnostic_artifact(
            f"{slug}-serial-log-tail",
            serial_content,
            extension=".txt",
            metadata_label=f"{description} serial log tail",
        )
        serial_label = f"{description} serial log tail"
        if not any(existing_path == serial_path for _, existing_path in self._escalation_diagnostics):
            self._escalation_diagnostics.append((serial_label, serial_path))

    def _record_child_output(self) -> None:
        buffer = self.child.before.replace("\r", "") if self.child.before else ""
        if not buffer:
            return
        for raw_line in buffer.splitlines():
            line = self._strip_ansi(raw_line).strip()
            if not line:
                continue
            if line == SHELL_PROMPT.strip():
                continue
            self._log_step(f"Serial output: {line}")

    def _read_serial_tail(self, lines: int = 50) -> List[str]:
        if not self.log_path.exists():
            return []
        with self.log_path.open("r", encoding="utf-8", errors="ignore") as handle:
            tail = handle.readlines()[-lines:]
        return [line.rstrip("\n") for line in tail]

    def _record_vm_exit_status(self) -> Optional[Tuple[str, Path, List[str]]]:
        """Record diagnostic information about the QEMU process when it exits."""

        isalive = getattr(self.child, "isalive", None)
        if not callable(isalive):
            return None
        try:
            alive = bool(isalive())
        except Exception as exc:  # pragma: no cover - defensive logging
            self._log_step(
                "Failed to determine QEMU process status",
                body=repr(exc),
            )
            return None
        if alive:
            return None

        exitstatus = getattr(self.child, "exitstatus", None)
        signalstatus = getattr(self.child, "signalstatus", None)
        pid = getattr(self.child, "pid", None)
        closed = getattr(self.child, "closed", None)

        status_lines = [
            "QEMU process is no longer running.",
            f"PID: {pid if pid is not None else 'unknown'}",
            f"Exit status: {exitstatus if exitstatus is not None else 'unknown'}",
            f"Signal status: {signalstatus if signalstatus is not None else 'unknown'}",
        ]
        if closed is not None:
            status_lines.append(f"pexpect closed flag: {closed!r}")

        status_body = "\n".join(status_lines)
        self._log_step("Captured QEMU exit status after failure", body=status_body)
        path = self._write_diagnostic_artifact(
            "qemu-exit-status",
            status_body,
            metadata_label="QEMU exit status",
        )
        return ("QEMU exit status", path, status_lines)

    def _raise_with_transcript(
        self,
        message: str,
        *,
        diagnostics: Optional[List[Tuple[str, Path]]] = None,
    ) -> None:
        self._record_child_output()
        serial_tail = self._read_serial_tail()
        transcript = "\n".join(self._transcript)

        collected_diagnostics: List[Tuple[str, Path]] = []
        if diagnostics:
            collected_diagnostics.extend(diagnostics)

        if self._escalation_diagnostics:
            for label, path in self._escalation_diagnostics:
                if not any(existing_path == path for _, existing_path in collected_diagnostics):
                    collected_diagnostics.append((label, path))

        exit_status = self._record_vm_exit_status()
        if exit_status is not None:
            label, path, status_lines = exit_status
            collected_diagnostics.append((label, path))

        if serial_tail:
            serial_body = "\n".join(serial_tail)
            self._log_step(
                f"Serial log tail (last {len(serial_tail)} lines)",
                body=serial_body,
            )
            serial_path = self._write_diagnostic_artifact(
                "serial-log-tail",
                serial_body,
                metadata_label="Serial log tail",
            )
            collected_diagnostics.append(("serial log tail", serial_path))

        if transcript:
            transcript_path = self._write_diagnostic_artifact(
                "login-transcript",
                transcript,
                extension=".txt",
                metadata_label="Login transcript",
            )
            collected_diagnostics.append(("login transcript", transcript_path))

        details = [message]
        details.append("Boot image artifact metadata:")
        details.extend(self._format_artifact_metadata())
        if transcript:
            details.append("Login transcript:")
            details.append(transcript)
        if serial_tail:
            details.append(f"Serial log tail (last {len(serial_tail)} lines):")
            details.append("\n".join(serial_tail))
        if exit_status is not None:
            _, _, status_lines = exit_status
            details.append("QEMU exit status:")
            details.extend(status_lines)
        details.append(f"Harness log: {self.harness_log_path}")
        details.append(f"Serial log: {self.log_path}")
        details.append(f"Metadata: {self.metadata_path}")
        if collected_diagnostics:
            details.append("Diagnostic artifacts:")
            for label, path in collected_diagnostics:
                details.append(f"- {label}: {path}")
        raise AssertionError("\n".join(details))

    def _expect_normalised(self, patterns: List[str], *, timeout: int) -> int:
        compiled = self.child.compile_pattern_list([*patterns, ANSI_ESCAPE_PATTERN])
        deadline = time.monotonic() + timeout
        self._log_step(
            "Awaiting patterns: " + ", ".join(patterns) + f" (timeout={timeout}s)"
        )
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                self._log_step("Timeout exceeded while waiting for patterns")
                raise pexpect.TIMEOUT("timeout exceeded while waiting for pattern")
            try:
                idx = self.child.expect_list(compiled, timeout=remaining)
            except pexpect.TIMEOUT:
                self._record_child_output()
                self._log_step("pexpect reported TIMEOUT while awaiting patterns")
                raise
            except pexpect.EOF as exc:
                self._record_child_output()
                self._log_step("pexpect reported EOF while awaiting patterns")
                self._raise_with_transcript(
                    "Unexpected EOF while awaiting patterns "
                    + ", ".join(patterns)
                    + f": {exc}"
                )
            except pexpect.ExceptionPexpect as exc:
                self._record_child_output()
                self._log_step(
                    "pexpect raised unexpected error while awaiting patterns",
                    body=repr(exc),
                )
                self._raise_with_transcript(
                    "pexpect error while awaiting patterns "
                    + ", ".join(patterns)
                    + f": {exc}"
                )
            self._record_child_output()
            if idx < len(patterns):
                self._log_step(f"Matched pattern: {patterns[idx]!r}")
                return idx

    def _set_shell_prompt(self) -> None:
        """Configure the interactive shell prompt."""

        self.child.sendline(f"export PS1='{SHELL_PROMPT}'")
        self._expect_normalised([SHELL_PROMPT], timeout=60)
        self._log_step("Shell prompt configured for interaction")

    def _read_uid(self) -> str:
        """Return the numeric UID reported by ``id -u``."""

        self.child.sendline("id -u")
        try:
            self.child.expect(r"(\d+)\r*(?:\n|$)", timeout=60)
        except pexpect.TIMEOUT as exc:  # pragma: no cover - integration timing
            self._raise_with_transcript(
                f"Timed out waiting for id -u output: {exc}"
            )
        except pexpect.EOF as exc:  # pragma: no cover - integration timing
            self._log_step("pexpect reported EOF while waiting for id -u output")
            self._raise_with_transcript(
                f"Unexpected EOF while waiting for id -u output: {exc}"
            )
        except pexpect.ExceptionPexpect as exc:  # pragma: no cover - defensive
            self._log_step(
                "pexpect raised unexpected error while waiting for id -u output",
                body=repr(exc),
            )
            self._raise_with_transcript(
                f"pexpect error while waiting for id -u output: {exc}"
            )
        uid = self.child.match.group(1)
        self._expect_normalised([SHELL_PROMPT], timeout=60)
        return uid

    def _escalate_with_sudo(self) -> bool:
        """Attempt to escalate privileges with ``sudo -i``."""

        transcript_start = self._snapshot_transcript()
        self._log_step("Attempting to escalate with sudo -i")
        self.child.sendline("sudo -i")
        sudo_patterns = [r"\[sudo\] password for nixos:", r"root@.*# ?", r"# ?"]
        try:
            idx = self._expect_normalised(sudo_patterns, timeout=120)
        except pexpect.TIMEOUT:
            reason = "sudo -i did not produce a root prompt"
            self._log_step(reason)
            self._capture_escalation_failure(
                slug="sudo",
                description="sudo -i",
                reason=reason,
                transcript_start=transcript_start,
            )
            return False
        if idx == 0:
            self._log_step("Submitting empty sudo password")
            self.child.sendline("")
            try:
                self._expect_normalised([r"root@.*# ?", r"# ?"], timeout=120)
            except pexpect.TIMEOUT:
                reason = "sudo -i password prompt did not yield a root shell"
                self._log_step(reason)
                self._capture_escalation_failure(
                    slug="sudo",
                    description="sudo -i",
                    reason=reason,
                    transcript_start=transcript_start,
                )
                return False
        self._set_shell_prompt()
        uid_output = self._read_uid()
        self._has_root_privileges = uid_output == "0"
        self._log_step(f"id -u after sudo -i returned: {uid_output!r}")
        if self._has_root_privileges:
            self._log_step("Successfully escalated privileges with sudo -i")
            self._clear_escalation_diagnostics()
            return True
        self._log_step("sudo -i completed without root privileges")
        self._capture_escalation_failure(
            slug="sudo",
            description="sudo -i",
            reason="sudo -i completed without root privileges",
            transcript_start=transcript_start,
        )
        return False

    def _escalate_with_su(self) -> bool:
        """Attempt to escalate privileges with ``su -``."""

        transcript_start = self._snapshot_transcript()
        self._log_step("Attempting to escalate with su -")
        self.child.sendline("su -")
        su_patterns = [r"Password:", r"root@.*# ?", r"# ?"]
        try:
            idx = self._expect_normalised(su_patterns, timeout=120)
        except pexpect.TIMEOUT:
            reason = "su - did not produce a root prompt"
            self._log_step(reason)
            self._capture_escalation_failure(
                slug="su",
                description="su -",
                reason=reason,
                transcript_start=transcript_start,
            )
            return False
        if idx == 0:
            self._log_step("Submitting empty root password for su -")
            self.child.sendline("")
            try:
                self._expect_normalised([r"root@.*# ?", r"# ?"], timeout=120)
            except pexpect.TIMEOUT:
                reason = "su - password prompt did not yield a root shell"
                self._log_step(reason)
                self._capture_escalation_failure(
                    slug="su",
                    description="su -",
                    reason=reason,
                    transcript_start=transcript_start,
                )
                return False
        self._set_shell_prompt()
        uid_output = self._read_uid()
        self._has_root_privileges = uid_output == "0"
        self._log_step(f"id -u after su - returned: {uid_output!r}")
        if self._has_root_privileges:
            self._log_step("Successfully escalated privileges with su -")
            self._clear_escalation_diagnostics()
            return True
        self._log_step("su - completed without root privileges")
        self._capture_escalation_failure(
            slug="su",
            description="su -",
            reason="su - completed without root privileges",
            transcript_start=transcript_start,
        )
        return False

    def _login(self) -> None:
        self._log_step("Starting login sequence")
        login_patterns = [
            r"login: ",
            r"\[nixos@[^]]+\]\$ ?",
            r"root@.*# ?",
            r"# ?",
        ]
        try:
            idx = self._expect_normalised(login_patterns, timeout=VM_LOGIN_TIMEOUT)
        except pexpect.TIMEOUT as exc:  # pragma: no cover - integration timing
            self._raise_with_transcript(
                f"Timed out waiting for initial login prompt: {exc}"
            )

        if idx == 0:
            automatic_login = False
            try:
                auto_idx = self._expect_normalised([r"\(automatic login\)"], timeout=1)
                automatic_login = auto_idx == 0
            except pexpect.TIMEOUT:
                automatic_login = False

            if not automatic_login:
                self._log_step("Sending username 'root'")
                self.child.sendline("root")
                prompt_patterns = [r"Password:", r"root@.*# ?", r"# ?"]
                try:
                    idx = self._expect_normalised(prompt_patterns, timeout=180)
                except pexpect.TIMEOUT as exc:  # pragma: no cover - integration timing
                    self._raise_with_transcript(
                        f"Timed out waiting for password prompt: {exc}"
                    )
                if idx == 0:
                    self._log_step("Submitting empty root password")
                    self.child.sendline("")
                    self._expect_normalised([r"root@.*# ?", r"# ?"], timeout=180)
                else:
                    self._log_step("Root prompt detected without password entry")
            else:
                self._log_step("Automatic login banner observed")

        self._set_shell_prompt()

        uid_output = self._read_uid()
        self._has_root_privileges = uid_output == "0"
        if self._has_root_privileges:
            self._log_step("Initial shell already has root privileges")
            self._clear_escalation_diagnostics()
            return

        self._log_step("Initial shell lacks root privileges")
        if self._escalate_with_sudo():
            return
        if self._escalate_with_su():
            return
        self._raise_with_transcript(
            "Failed to acquire root shell via sudo -i or su -"
        )

    def interact(self) -> None:
        """Drop into an interactive session with the running VM."""

        self._log_step(
            "Entering interactive debug session (Ctrl-] to terminate)"
        )
        try:
            self.child.interact(escape_character=chr(29))
        finally:
            self._log_step("Exited interactive debug session")

    def _strip_ansi(self, text: str) -> str:
        """Remove ANSI escape sequences from command output."""

        return ANSI_ESCAPE_PATTERN.sub("", text)

    def run(self, command: str, *, timeout: int = 180) -> str:
        self._log_step(f"Running command: {command}")
        self.child.sendline(command)
        try:
            self.child.expect(SHELL_PROMPT, timeout=timeout)
        except pexpect.TIMEOUT as exc:  # pragma: no cover - integration timing
            self._raise_with_transcript(
                f"Timed out while running command '{command}': {exc}"
            )
        except pexpect.EOF as exc:  # pragma: no cover - integration timing
            self._log_step("pexpect reported EOF while waiting for command output")
            self._raise_with_transcript(
                f"Unexpected EOF while running command '{command}': {exc}"
            )
        except pexpect.ExceptionPexpect as exc:  # pragma: no cover - defensive
            self._log_step(
                "pexpect raised unexpected error while running command",
                body=repr(exc),
            )
            self._raise_with_transcript(
                f"pexpect error while running command '{command}': {exc}"
            )
        output = self.child.before.replace("\r", "")
        lines = output.splitlines()
        cleaned: List[str] = []
        for raw_line in lines:
            stripped = self._strip_ansi(raw_line)
            if stripped.startswith(SHELL_PROMPT):
                stripped = stripped[len(SHELL_PROMPT) :]
            stripped = stripped.strip()
            if not stripped:
                continue
            cleaned.append(stripped)
        if cleaned and cleaned[0] == command:
            cleaned = cleaned[1:]
        return "\n".join(cleaned).strip()

    def _ensure_root_privileges(self) -> None:
        """Re-establish a root shell when privileged operations are required."""

        if self._has_root_privileges:
            uid_output = self._read_uid()
            if uid_output == "0":
                self._clear_escalation_diagnostics()
                return
            self._log_step(
                "Root shell check reported non-root uid "
                f"{uid_output!r}; attempting to regain root access"
            )
            self._has_root_privileges = False

        self._log_step(
            "Privileged command requested without active root shell; "
            "attempting to regain root access"
        )
        if self._escalate_with_sudo():
            return
        if self._escalate_with_su():
            return
        self._raise_with_transcript(
            "Failed to acquire root shell for privileged command"
        )

    def run_as_root(self, command: str, *, timeout: int = 180) -> str:
        """Execute a command with root privileges when needed."""

        self._ensure_root_privileges()
        return self.run(command, timeout=timeout)

    def collect_journal(self, unit: str, *, since_boot: bool = True) -> str:
        """Return the journal for a systemd unit."""

        args = ["journalctl", "--no-pager", "-u", unit]
        if since_boot:
            args.append("-b")
        command = " ".join(args) + " || true"
        return self.run(command, timeout=240)

    def assert_commands_available(self, *commands: str) -> None:
        """Ensure required commands are present in the boot environment."""

        # Issue a no-op to ensure the prompt is stable before issuing probes.
        self.run(":")

        missing: List[str] = []
        retry_attempts = 3
        retry_delay = 2.0
        for command in commands:
            for attempt in range(retry_attempts):
                result = self.run(
                    f"command -v {command} >/dev/null 2>&1 && echo OK || echo MISSING"
                )
                lines = [line.strip() for line in result.splitlines() if line.strip()]
                results = [line for line in lines if line in {"OK", "MISSING"}]
                has_missing = any(line == "MISSING" for line in results)
                if results and not has_missing:
                    break
                if attempt + 1 < retry_attempts:
                    time.sleep(retry_delay)
            else:
                missing.append(command)
        if missing:
            raise AssertionError(
                "required commands missing from boot image: " + ", ".join(sorted(missing))
            )

    def read_storage_status(self) -> Dict[str, str]:
        status_raw = self.run("cat /run/pre-nixos/storage-status 2>/dev/null || true")
        status: Dict[str, str] = {}
        for line in status_raw.splitlines():
            if "=" not in line:
                continue
            key, value = line.split("=", 1)
            status[key.strip()] = value.strip()
        return status

    def wait_for_storage_status(self, *, timeout: int = 420) -> Dict[str, str]:
        deadline = time.time() + timeout
        while time.time() < deadline:
            status = self.read_storage_status()
            if "STATE" in status and "DETAIL" in status:
                # Issue a no-op to ensure any buffered command output is flushed
                self.run(":")
                return status
            time.sleep(5)
        self._log_step("Timed out waiting for pre-nixos storage status")
        journal = self.collect_journal("pre-nixos.service")
        self._log_step(
            "Captured journalctl -u pre-nixos.service -b after storage status timeout",
            body=journal,
        )
        unit_status = self.run(
            "systemctl status pre-nixos --no-pager 2>&1 || true", timeout=240
        )
        self._log_step(
            "Captured systemctl status pre-nixos after storage status timeout",
            body=unit_status,
        )
        diagnostics: List[Tuple[str, Path]] = []
        journal_path = self._write_diagnostic_artifact(
            "pre-nixos-journal-storage-timeout",
            journal,
            metadata_label="journalctl -u pre-nixos.service -b (storage timeout)",
        )
        diagnostics.append(("journalctl -u pre-nixos.service -b", journal_path))
        status_path = self._write_diagnostic_artifact(
            "pre-nixos-status-storage-timeout",
            unit_status,
            metadata_label="systemctl status pre-nixos (storage timeout)",
        )
        diagnostics.append(("systemctl status pre-nixos", status_path))
        lsblk_output = self.run("lsblk -f 2>&1 || true", timeout=240)
        self._log_step(
            "Captured lsblk -f after storage status timeout",
            body=lsblk_output,
        )
        lsblk_path = self._write_diagnostic_artifact(
            "lsblk-storage-timeout",
            lsblk_output,
            metadata_label="lsblk -f (storage timeout)",
        )
        diagnostics.append(("lsblk -f", lsblk_path))
        jobs_output = self.run(
            "systemctl list-jobs --no-legend 2>&1 || true",
            timeout=240,
        )
        self._log_step(
            "Captured systemctl list-jobs after storage status timeout",
            body=jobs_output,
        )
        jobs_path = self._write_diagnostic_artifact(
            "systemctl-list-jobs-storage-timeout",
            jobs_output,
            metadata_label="systemctl list-jobs (storage timeout)",
        )
        diagnostics.append(("systemctl list-jobs", jobs_path))
        failed_units_output = self.run(
            "systemctl list-units --failed --no-legend 2>&1 || true",
            timeout=240,
        )
        self._log_step(
            "Captured systemctl list-units --failed after storage status timeout",
            body=failed_units_output,
        )
        failed_units_path = self._write_diagnostic_artifact(
            "systemctl-list-units-failed-storage-timeout",
            failed_units_output,
            metadata_label="systemctl list-units --failed (storage timeout)",
        )
        diagnostics.append(("systemctl list-units --failed", failed_units_path))
        storage_status_raw = self.run(
            "cat /run/pre-nixos/storage-status 2>/dev/null || true", timeout=240
        )
        self._log_step(
            "Captured /run/pre-nixos/storage-status after storage status timeout",
            body=storage_status_raw,
        )
        storage_status_path = self._write_diagnostic_artifact(
            "storage-status-storage-timeout",
            storage_status_raw,
            metadata_label="/run/pre-nixos/storage-status (storage timeout)",
        )
        diagnostics.append(("/run/pre-nixos/storage-status", storage_status_path))
        diagnostics.append(self._capture_dmesg("storage timeout"))
        storage_status_display = (
            storage_status_raw.strip() or "<no storage status captured>"
        )
        self._raise_with_transcript(
            "timed out waiting for pre-nixos storage status\n"
            f"journalctl -u pre-nixos.service -b:\n{journal}\n"
            f"systemctl status pre-nixos:\n{unit_status}\n"
            f"/run/pre-nixos/storage-status contents:\n{storage_status_display}",
            diagnostics=diagnostics,
        )

    def wait_for_ipv4(self, iface: str = "lan", *, timeout: int = 240) -> List[str]:
        deadline = time.time() + timeout
        while time.time() < deadline:
            output = self.run(f"ip -o -4 addr show dev {iface} 2>/dev/null || true")
            lines = [line for line in output.splitlines() if line.strip()]
            if any("inet " in line for line in lines):
                # Run a no-op so any buffered ip output is consumed before returning
                self.run(":")
                return lines
            time.sleep(5)
        self._log_step(f"Timed out waiting for IPv4 on interface {iface}")
        journal = self.collect_journal("pre-nixos.service")
        self._log_step(
            "Captured journalctl -u pre-nixos.service -b after IPv4 timeout",
            body=journal,
        )
        unit_status = self.run(
            "systemctl status pre-nixos --no-pager 2>&1 || true", timeout=240
        )
        self._log_step(
            "Captured systemctl status pre-nixos after IPv4 timeout",
            body=unit_status,
        )
        diagnostics: List[Tuple[str, Path]] = []
        journal_path = self._write_diagnostic_artifact(
            f"pre-nixos-journal-ipv4-timeout-{iface}",
            journal,
            metadata_label=(
                "journalctl -u pre-nixos.service -b "
                f"(IPv4 timeout on {iface})"
            ),
        )
        diagnostics.append(("journalctl -u pre-nixos.service -b", journal_path))
        status_path = self._write_diagnostic_artifact(
            f"pre-nixos-status-ipv4-timeout-{iface}",
            unit_status,
            metadata_label="systemctl status pre-nixos (IPv4 timeout)",
        )
        diagnostics.append(("systemctl status pre-nixos", status_path))
        network_status = self.run(
            f"networkctl status {iface} 2>&1 || true", timeout=240
        )
        self._log_step(
            f"Captured networkctl status {iface} after IPv4 timeout",
            body=network_status,
        )
        network_path = self._write_diagnostic_artifact(
            f"networkctl-status-ipv4-timeout-{iface}",
            network_status,
            metadata_label=f"networkctl status {iface} (IPv4 timeout)",
        )
        diagnostics.append((f"networkctl status {iface}", network_path))
        ip_addr_output = self.run(
            f"ip addr show dev {iface} 2>&1 || true", timeout=240
        )
        self._log_step(
            f"Captured ip addr show dev {iface} after IPv4 timeout",
            body=ip_addr_output,
        )
        ip_addr_path = self._write_diagnostic_artifact(
            f"ip-addr-ipv4-timeout-{iface}",
            ip_addr_output,
            metadata_label=f"ip addr show dev {iface} (IPv4 timeout)",
        )
        diagnostics.append((f"ip addr show dev {iface}", ip_addr_path))
        ip_route_output = self.run(
            f"ip route show dev {iface} 2>&1 || true", timeout=240
        )
        self._log_step(
            f"Captured ip route show dev {iface} after IPv4 timeout",
            body=ip_route_output,
        )
        ip_route_path = self._write_diagnostic_artifact(
            f"ip-route-ipv4-timeout-{iface}",
            ip_route_output,
            metadata_label=f"ip route show dev {iface} (IPv4 timeout)",
        )
        diagnostics.append((f"ip route show dev {iface}", ip_route_path))
        ip_link_output = self.run(
            f"ip -s link show dev {iface} 2>&1 || true", timeout=240
        )
        self._log_step(
            f"Captured ip -s link show dev {iface} after IPv4 timeout",
            body=ip_link_output,
        )
        ip_link_path = self._write_diagnostic_artifact(
            f"ip-link-stats-ipv4-timeout-{iface}",
            ip_link_output,
            metadata_label=f"ip -s link show dev {iface} (IPv4 timeout)",
        )
        diagnostics.append((f"ip -s link show dev {iface}", ip_link_path))
        networkd_status = self.run(
            "systemctl status systemd-networkd --no-pager 2>&1 || true",
            timeout=240,
        )
        self._log_step(
            "Captured systemctl status systemd-networkd after IPv4 timeout",
            body=networkd_status,
        )
        networkd_status_path = self._write_diagnostic_artifact(
            f"systemd-networkd-status-ipv4-timeout-{iface}",
            networkd_status,
            metadata_label="systemctl status systemd-networkd (IPv4 timeout)",
        )
        diagnostics.append(("systemctl status systemd-networkd", networkd_status_path))
        networkd_journal = self.collect_journal("systemd-networkd.service")
        self._log_step(
            "Captured journalctl -u systemd-networkd.service -b after IPv4 timeout",
            body=networkd_journal,
        )
        networkd_journal_path = self._write_diagnostic_artifact(
            f"systemd-networkd-journal-ipv4-timeout-{iface}",
            networkd_journal,
            metadata_label="journalctl -u systemd-networkd.service -b (IPv4 timeout)",
        )
        diagnostics.append(
            ("journalctl -u systemd-networkd.service -b", networkd_journal_path)
        )
        jobs_output = self.run(
            "systemctl list-jobs --no-legend 2>&1 || true",
            timeout=240,
        )
        self._log_step(
            f"Captured systemctl list-jobs after IPv4 timeout on {iface}",
            body=jobs_output,
        )
        jobs_path = self._write_diagnostic_artifact(
            f"systemctl-list-jobs-ipv4-timeout-{iface}",
            jobs_output,
            metadata_label=f"systemctl list-jobs (IPv4 timeout on {iface})",
        )
        diagnostics.append(("systemctl list-jobs", jobs_path))
        failed_units_output = self.run(
            "systemctl list-units --failed --no-legend 2>&1 || true",
            timeout=240,
        )
        self._log_step(
            f"Captured systemctl list-units --failed after IPv4 timeout on {iface}",
            body=failed_units_output,
        )
        failed_units_path = self._write_diagnostic_artifact(
            f"systemctl-list-units-failed-ipv4-timeout-{iface}",
            failed_units_output,
            metadata_label=(
                f"systemctl list-units --failed (IPv4 timeout on {iface})"
            ),
        )
        diagnostics.append(("systemctl list-units --failed", failed_units_path))
        diagnostics.append(self._capture_dmesg(f"IPv4 timeout on {iface}"))
        self._raise_with_transcript(
            f"timed out waiting for IPv4 address on {iface}\n"
            f"journalctl -u pre-nixos.service -b:\n{journal}\n"
            f"systemctl status pre-nixos:\n{unit_status}",
            diagnostics=diagnostics,
        )

    def wait_for_unit_inactive(self, unit: str, *, timeout: int = 240) -> str:
        """Wait until a systemd unit reports ``inactive`` via ``systemctl``."""

        # Flush any buffered output (e.g. from previous ip captures) before polling.
        self.run(":")
        deadline = time.time() + timeout
        status_command = f"systemctl is-active {unit} 2>/dev/null || true"
        while time.time() < deadline:
            output = self.run(status_command, timeout=60)
            lines = [line.strip() for line in output.splitlines() if line.strip()]
            if lines:
                status = lines[-1]
                if status == "inactive":
                    self._log_step(f"{unit} reported inactive state")
                    self.run(":")
                    return status
            time.sleep(5)

        unit_status = self.run(
            f"systemctl status {unit} --no-pager 2>&1 || true", timeout=240
        )
        journal_unit = unit if unit.endswith(".service") else f"{unit}.service"
        journal = self.collect_journal(journal_unit)
        diagnostics: List[Tuple[str, Path]] = []
        status_path = self._write_diagnostic_artifact(
            f"{journal_unit}-status-timeout",
            unit_status,
            metadata_label=f"systemctl status {unit} (inactive timeout)",
        )
        diagnostics.append((f"systemctl status {unit}", status_path))
        journal_path = self._write_diagnostic_artifact(
            f"{journal_unit}-journal-timeout",
            journal,
            metadata_label=f"journalctl -u {journal_unit} -b (inactive timeout)",
        )
        diagnostics.append((f"journalctl -u {journal_unit} -b", journal_path))
        job_list = self.run(
            "systemctl list-jobs --no-legend 2>&1 || true", timeout=240
        )
        self._log_step(
            "Captured systemctl list-jobs after unit inactivity timeout",
            body=job_list,
        )
        jobs_path = self._write_diagnostic_artifact(
            f"{journal_unit}-jobs-timeout",
            job_list,
            metadata_label="systemctl list-jobs (inactive timeout)",
        )
        diagnostics.append(("systemctl list-jobs", jobs_path))
        failed_units_output = self.run(
            "systemctl list-units --failed --no-legend 2>&1 || true",
            timeout=240,
        )
        self._log_step(
            "Captured systemctl list-units --failed after unit inactivity timeout",
            body=failed_units_output,
        )
        failed_units_path = self._write_diagnostic_artifact(
            f"{journal_unit}-failed-units-timeout",
            failed_units_output,
            metadata_label="systemctl list-units --failed (inactive timeout)",
        )
        diagnostics.append(("systemctl list-units --failed", failed_units_path))
        diagnostics.append(
            self._capture_dmesg(f"inactive timeout for {unit}")
        )
        self._raise_with_transcript(
            "\n".join(
                [
                    f"Unit {unit} did not reach inactive state within {timeout}s",
                    f"systemctl status {unit}:\n{unit_status}",
                    f"journalctl -u {journal_unit} -b:\n{journal}",
                ]
            ),
            diagnostics=diagnostics,
        )

    def shutdown(self) -> None:
        if not self.child.isalive():
            return
        try:
            self.child.sendline("poweroff")
            self.child.expect(["reboot: Power down", pexpect.EOF], timeout=180)
        except pexpect.ExceptionPexpect:
            self.child.close(force=True)
        else:
            self.child.expect(pexpect.EOF, timeout=60)

    def run_ssh(
        self,
        *,
        private_key: Path,
        command: str,
        port: Optional[int] = None,
        user: str = "root",
        timeout: int = 240,
        interval: float = 5.0,
    ) -> str:
        """Execute a command over SSH, retrying until success or timeout."""

        target_port = self.ssh_port if port is None else port
        deadline = time.monotonic() + timeout
        last_stdout = ""
        last_stderr = ""
        last_returncode: Optional[int] = None
        attempts = 0

        self._log_step(
            "Executing SSH command",
            body="\n".join(
                [
                    f"User: {user}",
                    f"Host: {self.ssh_host}",
                    f"Port: {target_port}",
                    f"Command: {command}",
                ]
            ),
        )

        ssh_cmd = [
            self.ssh_executable,
            "-i",
            str(private_key),
            "-o",
            "BatchMode=yes",
            "-o",
            "StrictHostKeyChecking=no",
            "-o",
            "UserKnownHostsFile=/dev/null",
            "-o",
            "ConnectTimeout=10",
            "-p",
            str(target_port),
            f"{user}@{self.ssh_host}",
            command,
        ]

        while time.monotonic() < deadline:
            attempts += 1
            result = subprocess.run(
                ssh_cmd,
                check=False,
                capture_output=True,
                text=True,
            )
            if result.returncode == 0:
                output = result.stdout.strip()
                self._log_step(
                    f"SSH command succeeded on attempt {attempts}",
                    body=output or None,
                )
                return output
            last_stdout = result.stdout
            last_stderr = result.stderr
            last_returncode = result.returncode
            self._log_step(
                f"SSH command attempt {attempts} failed with return code {result.returncode}",
                body="\n".join(
                    [
                        "--- stdout ---",
                        last_stdout.strip() or "<no stdout>",
                        "--- stderr ---",
                        last_stderr.strip() or "<no stderr>",
                    ]
                ),
            )
            time.sleep(interval)

        diagnostics: List[Tuple[str, Path]] = []
        command_summary = " ".join(ssh_cmd)
        stdout_content = "\n".join(
            [
                f"SSH command: {command_summary}",
                f"User: {user}",
                f"Host: {self.ssh_host}",
                f"Port: {target_port}",
                f"Attempts: {attempts}",
                f"Last return code: {last_returncode if last_returncode is not None else 'N/A'}",
                "",
                last_stdout.rstrip("\n") or "<no stdout captured>",
            ]
        )
        stdout_path = self._write_diagnostic_artifact(
            "ssh-command-stdout",
            stdout_content,
            metadata_label="SSH command stdout",
        )
        diagnostics.append(("SSH command stdout", stdout_path))

        stderr_content = "\n".join(
            [
                f"SSH command: {command_summary}",
                f"User: {user}",
                f"Host: {self.ssh_host}",
                f"Port: {target_port}",
                f"Attempts: {attempts}",
                f"Last return code: {last_returncode if last_returncode is not None else 'N/A'}",
                "",
                last_stderr.rstrip("\n") or "<no stderr captured>",
            ]
        )
        stderr_path = self._write_diagnostic_artifact(
            "ssh-command-stderr",
            stderr_content,
            metadata_label="SSH command stderr",
        )
        diagnostics.append(("SSH command stderr", stderr_path))

        def _capture_vm_output(
            *,
            label: str,
            slug: str,
            collector: Callable[[], str],
        ) -> None:
            try:
                output = collector()
            except AssertionError as exc:
                output = f"Failed to capture {label}: {exc}"
            log_body = output or "<no output captured>"
            self._log_step(f"Captured {label} after SSH failure", body=log_body)
            path = self._write_diagnostic_artifact(
                slug,
                output,
                metadata_label=label,
            )
            diagnostics.append((label, path))

        _capture_vm_output(
            label="systemctl status sshd",
            slug="systemctl-status-sshd",
            collector=lambda: self.run(
                "systemctl status sshd --no-pager 2>&1 || true", timeout=240
            ),
        )

        _capture_vm_output(
            label="journalctl -u sshd.service -b",
            slug="journalctl-sshd-service",
            collector=lambda: self.collect_journal("sshd.service"),
        )

        failure_lines = [
            (
                "SSH command '{cmd}' failed after {attempts} attempts for {user}@{host}:{port}".format(
                    cmd=command,
                    attempts=attempts,
                    user=user,
                    host=self.ssh_host,
                    port=target_port,
                )
            )
        ]
        if last_returncode is not None:
            failure_lines.append(f"Last return code: {last_returncode}")
        failure_lines.append(
            "Last stdout:\n" + (last_stdout.strip() or "<no stdout>")
        )
        failure_lines.append(
            "Last stderr:\n" + (last_stderr.strip() or "<no stderr>")
        )
        self._raise_with_transcript("\n".join(failure_lines), diagnostics=diagnostics)


def test_escalation_failure_artifact_and_raise(tmp_path: Path) -> None:
    """Root escalation failures should create diagnostic transcripts automatically."""

    iso_path = tmp_path / "sample.iso"
    store_path = tmp_path / "store"
    disk_image = tmp_path / "disk.img"
    harness_log = tmp_path / "harness.log"
    serial_log = tmp_path / "serial.log"
    metadata_path = tmp_path / "metadata.json"
    iso_path.write_text("", encoding="utf-8")
    store_path.mkdir()
    disk_image.write_text("", encoding="utf-8")
    harness_log.write_text("", encoding="utf-8")
    serial_log.write_text(
        "serial boot line 1\nserial boot line 2\n",
        encoding="utf-8",
    )

    artifact = BootImageBuild(
        iso_path=iso_path,
        store_path=store_path,
        deriver="sample.drv",
        nar_hash="sha256-sample",
        root_key_fingerprint="SHA256:sample",
    )

    write_boot_image_metadata(
        metadata_path,
        artifact=artifact,
        harness_log=harness_log,
        serial_log=serial_log,
        qemu_command=["qemu", "--version"],
        disk_image=disk_image,
        ssh_host="127.0.0.1",
        ssh_port=2222,
        ssh_executable="/usr/bin/ssh",
    )

    class DummyChild:
        def __init__(self) -> None:
            self.before = ""

    vm = object.__new__(BootImageVM)
    vm.child = DummyChild()
    vm.log_path = serial_log
    vm.harness_log_path = harness_log
    vm.metadata_path = metadata_path
    vm.ssh_port = 2222
    vm.ssh_host = "127.0.0.1"
    vm.ssh_executable = "/usr/bin/ssh"
    vm.artifact = artifact
    vm.qemu_command = ("qemu", "--version")
    vm.disk_image = disk_image
    vm._transcript = []
    vm._has_root_privileges = False
    vm._log_dir = metadata_path.parent
    vm._diagnostic_dir = metadata_path.parent / "diagnostics"
    vm._diagnostic_dir.mkdir(exist_ok=True)
    vm._diagnostic_counter = 0
    vm._escalation_diagnostics = []

    transcript_start = vm._snapshot_transcript()
    vm._log_step("Attempting to escalate with sudo -i")
    vm.child.before = "sudo -i\r\nPassword:\r\n"
    vm._capture_escalation_failure(
        slug="sudo",
        description="sudo -i",
        reason="sudo -i did not produce a root prompt",
        transcript_start=transcript_start,
    )

    assert vm._escalation_diagnostics, "expected escalation diagnostics to be recorded"
    diagnostics_map = {label: path for label, path in vm._escalation_diagnostics}

    transcript_path = diagnostics_map.get("sudo -i escalation transcript")
    assert transcript_path is not None, "expected escalation transcript artifact"
    assert transcript_path.exists()
    content = transcript_path.read_text(encoding="utf-8")
    assert "Escalation method: sudo -i" in content
    assert "Failure reason: sudo -i did not produce a root prompt" in content

    serial_path = diagnostics_map.get("sudo -i serial log tail")
    assert serial_path is not None, "expected serial log artifact"
    assert serial_path.exists()
    serial_content = serial_path.read_text(encoding="utf-8")
    assert "Escalation method: sudo -i" in serial_content
    assert "serial boot line 2" in serial_content

    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    diagnostics = metadata["diagnostics"]["artifacts"]
    labels_in_metadata = {entry["label"] for entry in diagnostics}
    assert "sudo -i escalation transcript" in labels_in_metadata
    assert "sudo -i serial log tail" in labels_in_metadata

    paths_in_metadata = {entry["path"] for entry in diagnostics}
    assert str(transcript_path) in paths_in_metadata
    assert str(serial_path) in paths_in_metadata

    with pytest.raises(AssertionError) as excinfo:
        vm._raise_with_transcript("escalation failed")
    message = str(excinfo.value)
    assert "sudo -i escalation transcript" in message
    assert "sudo -i serial log tail" in message
    assert str(transcript_path) in message
    assert str(serial_path) in message


def test_raise_with_transcript_includes_qemu_version(tmp_path: Path) -> None:
    """Failures should surface the QEMU version in harness assertions."""

    iso_path = tmp_path / "sample.iso"
    store_path = tmp_path / "store"
    disk_image = tmp_path / "disk.img"
    harness_log = tmp_path / "harness.log"
    serial_log = tmp_path / "serial.log"
    metadata_path = tmp_path / "metadata.json"

    iso_path.write_text("", encoding="utf-8")
    store_path.mkdir()
    disk_image.write_text("", encoding="utf-8")
    harness_log.write_text("", encoding="utf-8")
    serial_log.write_text("", encoding="utf-8")

    artifact = BootImageBuild(
        iso_path=iso_path,
        store_path=store_path,
        deriver="sample.drv",
        nar_hash="sha256-sample",
        root_key_fingerprint="SHA256:sample",
    )

    qemu_version = "QEMU emulator version 8.0.0"
    write_boot_image_metadata(
        metadata_path,
        artifact=artifact,
        harness_log=harness_log,
        serial_log=serial_log,
        qemu_command=["qemu", "--version"],
        qemu_version=qemu_version,
        disk_image=disk_image,
        ssh_host="127.0.0.1",
        ssh_port=2222,
        ssh_executable="/usr/bin/ssh",
    )

    class DummyChild:
        def __init__(self) -> None:
            self.before = ""
            self.exitstatus = 0
            self.signalstatus = None
            self.pid = 1234
            self.closed = False

        def isalive(self) -> bool:
            return False

    vm = object.__new__(BootImageVM)
    vm.child = DummyChild()
    vm.log_path = serial_log
    vm.harness_log_path = harness_log
    vm.metadata_path = metadata_path
    vm.ssh_port = 2222
    vm.ssh_host = "127.0.0.1"
    vm.ssh_executable = "/usr/bin/ssh"
    vm.artifact = artifact
    vm.qemu_version = qemu_version
    vm.qemu_command = ("qemu", "--version")
    vm.disk_image = disk_image
    vm._transcript = []
    vm._has_root_privileges = False
    vm._log_dir = metadata_path.parent
    vm._diagnostic_dir = metadata_path.parent / "diagnostics"
    vm._diagnostic_dir.mkdir(exist_ok=True)
    vm._diagnostic_counter = 0
    vm._escalation_diagnostics = []

    with pytest.raises(AssertionError) as excinfo:
        vm._raise_with_transcript("example failure")

    message = str(excinfo.value)
    assert f"QEMU version: {qemu_version}" in message
    assert f"Disk image: {disk_image}" in message
    assert "QEMU command: qemu --version" in message


def test_run_command_eof_records_diagnostics(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Unexpected EOF errors should surface diagnostics via _raise_with_transcript."""

    stub_pexpect = pexpect
    if pexpect is None:
        class DummyTimeout(Exception):
            pass

        class DummyEOF(Exception):
            pass

        class DummyException(Exception):
            pass

        class StubPexpect:
            TIMEOUT = DummyTimeout
            EOF = DummyEOF
            ExceptionPexpect = DummyException

        monkeypatch.setitem(globals(), "pexpect", StubPexpect)
        stub_pexpect = StubPexpect

    iso_path = tmp_path / "sample.iso"
    store_path = tmp_path / "store"
    disk_image = tmp_path / "disk.img"
    harness_log = tmp_path / "harness.log"
    serial_log = tmp_path / "serial.log"
    metadata_path = tmp_path / "metadata.json"

    iso_path.write_text("", encoding="utf-8")
    store_path.mkdir()
    disk_image.write_text("", encoding="utf-8")
    harness_log.write_text("", encoding="utf-8")

    artifact = BootImageBuild(
        iso_path=iso_path,
        store_path=store_path,
        deriver="sample.drv",
        nar_hash="sha256-sample",
        root_key_fingerprint="SHA256:sample",
    )

    write_boot_image_metadata(
        metadata_path,
        artifact=artifact,
        harness_log=harness_log,
        serial_log=serial_log,
        qemu_command=["qemu", "--version"],
        disk_image=disk_image,
        ssh_host="127.0.0.1",
        ssh_port=2222,
        ssh_executable="/usr/bin/ssh",
    )

    class EOFChild:
        def __init__(self) -> None:
            self.before = ""
            self.exitstatus = 1
            self.signalstatus = None
            self.pid = 1234
            self.closed = True
            self._alive = True

        def sendline(self, command: str) -> None:
            self.before = f"{command}\r\npartial output"

        def expect(self, pattern: object, timeout: int) -> None:
            self.before += "\r\nunexpected termination"
            self._alive = False
            raise stub_pexpect.EOF("command stream closed")

        def isalive(self) -> bool:
            return self._alive

    vm = object.__new__(BootImageVM)
    vm.child = EOFChild()
    vm.log_path = serial_log
    vm.harness_log_path = harness_log
    vm.metadata_path = metadata_path
    vm.ssh_port = 2222
    vm.ssh_host = "127.0.0.1"
    vm.ssh_executable = "/usr/bin/ssh"
    vm.artifact = artifact
    vm.qemu_command = ("qemu", "--version")
    vm.disk_image = disk_image
    vm._transcript = []
    vm._has_root_privileges = False
    vm._log_dir = metadata_path.parent
    vm._diagnostic_dir = metadata_path.parent / "diagnostics"
    vm._diagnostic_dir.mkdir(exist_ok=True)
    vm._diagnostic_counter = 0
    vm._escalation_diagnostics = []

    with pytest.raises(AssertionError) as excinfo:
        vm.run("echo hello")

    message = str(excinfo.value)
    assert "Unexpected EOF while running command 'echo hello'" in message
    assert "Diagnostic artifacts:" in message

    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    diagnostics = metadata["diagnostics"]["artifacts"]
    login_entries = [
        entry
        for entry in diagnostics
        if entry["label"] == "Login transcript"
    ]
    assert login_entries, "expected login transcript diagnostic to be recorded"
    for entry in login_entries:
        path = Path(entry["path"])
        assert path.exists(), "diagnostic artifact path should exist"

    qemu_entries = [
        entry for entry in diagnostics if entry["label"] == "QEMU exit status"
    ]
    assert qemu_entries, "expected QEMU exit status diagnostic to be recorded"
    qemu_path = Path(qemu_entries[-1]["path"])
    assert qemu_path.exists(), "QEMU exit status artifact should exist"
    qemu_content = qemu_path.read_text(encoding="utf-8")
    assert "Exit status: 1" in qemu_content


def test_run_ssh_failure_records_diagnostics(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """SSH failures should leave behind diagnostic artifacts and surface them."""

    iso_path = tmp_path / "sample.iso"
    store_path = tmp_path / "store"
    disk_image = tmp_path / "disk.img"
    harness_log = tmp_path / "harness.log"
    serial_log = tmp_path / "serial.log"
    metadata_path = tmp_path / "metadata.json"

    iso_path.write_text("", encoding="utf-8")
    store_path.mkdir()
    disk_image.write_text("", encoding="utf-8")
    harness_log.write_text("", encoding="utf-8")
    serial_log.write_text("", encoding="utf-8")

    artifact = BootImageBuild(
        iso_path=iso_path,
        store_path=store_path,
        deriver="sample.drv",
        nar_hash="sha256-sample",
        root_key_fingerprint="SHA256:sample",
    )

    write_boot_image_metadata(
        metadata_path,
        artifact=artifact,
        harness_log=harness_log,
        serial_log=serial_log,
        qemu_command=["qemu", "--version"],
        disk_image=disk_image,
        ssh_host="127.0.0.1",
        ssh_port=2222,
        ssh_executable="/usr/bin/ssh",
    )

    class DummyChild:
        def __init__(self) -> None:
            self.before = ""

    vm = object.__new__(BootImageVM)
    vm.child = DummyChild()
    vm.log_path = serial_log
    vm.harness_log_path = harness_log
    vm.metadata_path = metadata_path
    vm.ssh_port = 2222
    vm.ssh_host = "127.0.0.1"
    vm.ssh_executable = "/usr/bin/ssh"
    vm.artifact = artifact
    vm.qemu_command = ("qemu", "--version")
    vm.disk_image = disk_image
    vm._transcript = []
    vm._has_root_privileges = False
    vm._log_dir = metadata_path.parent
    vm._diagnostic_dir = metadata_path.parent / "diagnostics"
    vm._diagnostic_dir.mkdir(exist_ok=True)
    vm._diagnostic_counter = 0
    vm._escalation_diagnostics = []

    attempts: List[int] = []
    commands: List[str] = []
    journal_calls: List[Tuple[str, bool]] = []

    def fake_run(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        result = subprocess.CompletedProcess(
            args=args,
            returncode=255,
            stdout="simulated stdout\n",
            stderr="simulated stderr\n",
        )
        attempts.append(1)
        return result

    monotonic_values = iter([0.0, 0.1, 1.5])

    def fake_monotonic() -> float:
        try:
            return next(monotonic_values)
        except StopIteration:
            return 2.0

    monkeypatch.setattr(
        "tests.test_boot_image_vm.subprocess.run",
        fake_run,
    )
    monkeypatch.setattr("tests.test_boot_image_vm.time.monotonic", fake_monotonic)
    monkeypatch.setattr("tests.test_boot_image_vm.time.sleep", lambda _: None)

    def fake_vm_run(command: str, *, timeout: int = 180) -> str:  # type: ignore[override]
        commands.append(command)
        return f"output for {command}"

    def fake_collect_journal(
        unit: str, *, since_boot: bool = True
    ) -> str:  # type: ignore[override]
        journal_calls.append((unit, since_boot))
        return f"journal for {unit}"

    vm.run = fake_vm_run  # type: ignore[assignment]
    vm.collect_journal = fake_collect_journal  # type: ignore[assignment]

    with pytest.raises(AssertionError) as excinfo:
        vm.run_ssh(
            private_key=tmp_path / "id_ed25519",
            command="id -un",
            timeout=1,
            interval=0,
        )

    assert attempts, "expected SSH command to be invoked"
    message = str(excinfo.value)
    assert "SSH command stdout" in message
    assert "SSH command stderr" in message
    assert "systemctl status sshd" in message
    assert "journalctl -u sshd.service -b" in message

    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    artifacts = metadata["diagnostics"]["artifacts"]
    stdout_entries = [
        entry for entry in artifacts if entry["label"] == "SSH command stdout"
    ]
    stderr_entries = [
        entry for entry in artifacts if entry["label"] == "SSH command stderr"
    ]
    assert stdout_entries, "expected SSH stdout diagnostic to be recorded"
    assert stderr_entries, "expected SSH stderr diagnostic to be recorded"

    sshd_status_entries = [
        entry for entry in artifacts if entry["label"] == "systemctl status sshd"
    ]
    sshd_journal_entries = [
        entry
        for entry in artifacts
        if entry["label"] == "journalctl -u sshd.service -b"
    ]
    assert sshd_status_entries, "expected sshd status diagnostic to be recorded"
    assert sshd_journal_entries, "expected sshd journal diagnostic to be recorded"

    stdout_path = Path(stdout_entries[-1]["path"])
    stderr_path = Path(stderr_entries[-1]["path"])
    assert stdout_path.exists()
    assert stderr_path.exists()
    stdout_content = stdout_path.read_text(encoding="utf-8")
    stderr_content = stderr_path.read_text(encoding="utf-8")
    assert "simulated stdout" in stdout_content
    assert "simulated stderr" in stderr_content

    status_path = Path(sshd_status_entries[-1]["path"])
    journal_path = Path(sshd_journal_entries[-1]["path"])
    assert status_path.exists()
    assert journal_path.exists()
    status_content = status_path.read_text(encoding="utf-8")
    journal_content = journal_path.read_text(encoding="utf-8")
    assert "output for systemctl status sshd --no-pager 2>&1 || true" in status_content
    assert "journal for sshd.service" in journal_content

    assert any(
        command == "systemctl status sshd --no-pager 2>&1 || true" for command in commands
    ), "expected systemctl status sshd to be collected"
    assert journal_calls == [("sshd.service", True)]

def test_storage_timeout_records_systemd_jobs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Storage status timeouts should capture systemctl list-jobs diagnostics."""

    iso_path = tmp_path / "sample.iso"
    store_path = tmp_path / "store"
    disk_image = tmp_path / "disk.img"
    harness_log = tmp_path / "harness.log"
    serial_log = tmp_path / "serial.log"
    metadata_path = tmp_path / "metadata.json"

    iso_path.write_text("", encoding="utf-8")
    store_path.mkdir()
    disk_image.write_text("", encoding="utf-8")
    harness_log.write_text("", encoding="utf-8")
    serial_log.write_text("serial line\n", encoding="utf-8")

    artifact = BootImageBuild(
        iso_path=iso_path,
        store_path=store_path,
        deriver="sample.drv",
        nar_hash="sha256-sample",
        root_key_fingerprint="SHA256:sample",
    )

    write_boot_image_metadata(
        metadata_path,
        artifact=artifact,
        harness_log=harness_log,
        serial_log=serial_log,
        qemu_command=["qemu", "--version"],
        disk_image=disk_image,
        ssh_host="127.0.0.1",
        ssh_port=2222,
        ssh_executable="/usr/bin/ssh",
    )

    class DummyChild:
        def __init__(self) -> None:
            self.before = ""

    vm = object.__new__(BootImageVM)
    vm.child = DummyChild()
    vm.log_path = serial_log
    vm.harness_log_path = harness_log
    vm.metadata_path = metadata_path
    vm.ssh_port = 2222
    vm.ssh_host = "127.0.0.1"
    vm.ssh_executable = "/usr/bin/ssh"
    vm.artifact = artifact
    vm.qemu_command = ("qemu", "--version")
    vm.disk_image = disk_image
    vm._transcript = []
    vm._has_root_privileges = False
    vm._log_dir = metadata_path.parent
    vm._diagnostic_dir = metadata_path.parent / "diagnostics"
    vm._diagnostic_dir.mkdir(exist_ok=True)
    vm._diagnostic_counter = 0
    vm._escalation_diagnostics = []

    commands: List[str] = []

    def fake_run(command: str, *, timeout: int = 180) -> str:  # type: ignore[override]
        commands.append(command)
        if "systemctl status pre-nixos" in command:
            return "pre-nixos status"
        if "lsblk" in command:
            return "lsblk output"
        if "systemctl list-jobs" in command:
            return "job output"
        if "systemctl list-units --failed" in command:
            return "failed units output"
        if command.startswith("dmesg"):
            return "dmesg output"
        if "/run/pre-nixos/storage-status" in command:
            return "STATE=pending\nDETAIL=waiting"
        return ""

    def fake_collect_journal(unit: str, *, since_boot: bool = True) -> str:  # type: ignore[override]
        return "journal output"

    vm.run = fake_run  # type: ignore[assignment]
    vm.collect_journal = fake_collect_journal  # type: ignore[assignment]
    vm.read_storage_status = lambda: {}

    time_values = iter([0.0, 0.0, 1000.0])

    def fake_time() -> float:
        try:
            return next(time_values)
        except StopIteration:
            return 1000.0

    monkeypatch.setattr("tests.test_boot_image_vm.time.time", fake_time)
    monkeypatch.setattr("tests.test_boot_image_vm.time.sleep", lambda _: None)

    with pytest.raises(AssertionError) as excinfo:
        vm.wait_for_storage_status(timeout=1)

    message = str(excinfo.value)
    assert "systemctl list-jobs" in message
    assert any("systemctl list-jobs" in cmd for cmd in commands)
    assert "systemctl list-units --failed" in message
    assert any("systemctl list-units --failed" in cmd for cmd in commands)
    assert "/run/pre-nixos/storage-status contents" in message
    assert any("/run/pre-nixos/storage-status" in cmd for cmd in commands)
    assert "dmesg (storage timeout)" in message
    assert any(cmd.startswith("dmesg") for cmd in commands)

    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    diagnostics = metadata["diagnostics"]["artifacts"]
    labels = {entry["label"] for entry in diagnostics}
    assert "systemctl list-jobs (storage timeout)" in labels
    assert "systemctl list-units --failed (storage timeout)" in labels
    assert "/run/pre-nixos/storage-status (storage timeout)" in labels
    assert "dmesg (storage timeout)" in labels
    job_entries = [
        entry
        for entry in diagnostics
        if entry["label"] == "systemctl list-jobs (storage timeout)"
    ]
    assert job_entries, "expected systemctl list-jobs artifact to be catalogued"
    for entry in job_entries:
        assert Path(entry["path"]).exists()

    failed_units_entries = [
        entry
        for entry in diagnostics
        if entry["label"] == "systemctl list-units --failed (storage timeout)"
    ]
    assert (
        failed_units_entries
    ), "expected systemctl list-units --failed artifact to be catalogued"
    for entry in failed_units_entries:
        assert Path(entry["path"]).exists()

    dmesg_entries = [
        entry
        for entry in diagnostics
        if entry["label"] == "dmesg (storage timeout)"
    ]
    assert dmesg_entries, "expected dmesg artifact to be catalogued"
    for entry in dmesg_entries:
        assert Path(entry["path"]).exists()

    storage_entries = [
        entry
        for entry in diagnostics
        if entry["label"] == "/run/pre-nixos/storage-status (storage timeout)"
    ]
    assert storage_entries, "expected storage-status artifact to be catalogued"
    for entry in storage_entries:
        assert Path(entry["path"]).exists()


def test_ipv4_timeout_records_systemd_jobs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """IPv4 timeouts should capture systemctl list-jobs diagnostics."""

    iso_path = tmp_path / "sample.iso"
    store_path = tmp_path / "store"
    disk_image = tmp_path / "disk.img"
    harness_log = tmp_path / "harness.log"
    serial_log = tmp_path / "serial.log"
    metadata_path = tmp_path / "metadata.json"

    iso_path.write_text("", encoding="utf-8")
    store_path.mkdir()
    disk_image.write_text("", encoding="utf-8")
    harness_log.write_text("", encoding="utf-8")
    serial_log.write_text("serial line\n", encoding="utf-8")

    artifact = BootImageBuild(
        iso_path=iso_path,
        store_path=store_path,
        deriver="sample.drv",
        nar_hash="sha256-sample",
        root_key_fingerprint="SHA256:sample",
    )

    write_boot_image_metadata(
        metadata_path,
        artifact=artifact,
        harness_log=harness_log,
        serial_log=serial_log,
        qemu_command=["qemu", "--version"],
        disk_image=disk_image,
        ssh_host="127.0.0.1",
        ssh_port=2222,
        ssh_executable="/usr/bin/ssh",
    )

    class DummyChild:
        def __init__(self) -> None:
            self.before = ""

    vm = object.__new__(BootImageVM)
    vm.child = DummyChild()
    vm.log_path = serial_log
    vm.harness_log_path = harness_log
    vm.metadata_path = metadata_path
    vm.ssh_port = 2222
    vm.ssh_host = "127.0.0.1"
    vm.ssh_executable = "/usr/bin/ssh"
    vm.artifact = artifact
    vm.qemu_command = ("qemu", "--version")
    vm.disk_image = disk_image
    vm._transcript = []
    vm._has_root_privileges = False
    vm._log_dir = metadata_path.parent
    vm._diagnostic_dir = metadata_path.parent / "diagnostics"
    vm._diagnostic_dir.mkdir(exist_ok=True)
    vm._diagnostic_counter = 0
    vm._escalation_diagnostics = []

    commands: List[str] = []
    journal_calls: List[Tuple[str, bool]] = []

    def fake_run(command: str, *, timeout: int = 180) -> str:  # type: ignore[override]
        commands.append(command)
        if command.startswith("ip -o -4 addr"):
            return ""
        if command.startswith("ip addr show dev"):
            return "ip addr output"
        if command.startswith("ip route show dev"):
            return "ip route output"
        if command.startswith("ip -s link show dev"):
            return "ip link stats output"
        if "systemctl status pre-nixos" in command:
            return "pre-nixos status"
        if "networkctl status" in command:
            return "networkctl output"
        if "systemctl status systemd-networkd" in command:
            return "networkd status"
        if "systemctl list-jobs" in command:
            return "job output"
        if "systemctl list-units --failed" in command:
            return "failed units output"
        if command.startswith("dmesg"):
            return "dmesg output"
        return ""

    def fake_collect_journal(
        unit: str, *, since_boot: bool = True
    ) -> str:  # type: ignore[override]
        journal_calls.append((unit, since_boot))
        if unit == "systemd-networkd.service":
            return "networkd journal"
        return "journal output"

    vm.run = fake_run  # type: ignore[assignment]
    vm.collect_journal = fake_collect_journal  # type: ignore[assignment]

    time_values = iter([0.0, 0.0, 1000.0])

    def fake_time() -> float:
        try:
            return next(time_values)
        except StopIteration:
            return 1000.0

    monkeypatch.setattr("tests.test_boot_image_vm.time.time", fake_time)
    monkeypatch.setattr("tests.test_boot_image_vm.time.sleep", lambda _: None)

    with pytest.raises(AssertionError) as excinfo:
        vm.wait_for_ipv4(timeout=1)

    message = str(excinfo.value)
    assert "systemctl list-jobs" in message
    assert any("systemctl list-jobs" in cmd for cmd in commands)
    assert "systemctl list-units --failed" in message
    assert any("systemctl list-units --failed" in cmd for cmd in commands)
    assert "systemctl status systemd-networkd" in message
    assert any(
        "systemctl status systemd-networkd" in cmd for cmd in commands
    )
    assert "ip addr show dev lan" in message
    assert any("ip addr show dev lan" in cmd for cmd in commands)
    assert "ip route show dev lan" in message
    assert any("ip route show dev lan" in cmd for cmd in commands)
    assert "ip -s link show dev lan" in message
    assert any("ip -s link show dev lan" in cmd for cmd in commands)
    assert "dmesg (IPv4 timeout on lan)" in message
    assert any(cmd.startswith("dmesg") for cmd in commands)

    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    diagnostics = metadata["diagnostics"]["artifacts"]
    labels = {entry["label"] for entry in diagnostics}
    assert "systemctl list-jobs (IPv4 timeout on lan)" in labels
    assert "systemctl list-units --failed (IPv4 timeout on lan)" in labels
    assert "systemctl status systemd-networkd (IPv4 timeout)" in labels
    assert (
        "journalctl -u systemd-networkd.service -b (IPv4 timeout)" in labels
    )
    assert "ip addr show dev lan (IPv4 timeout)" in labels
    assert "ip route show dev lan (IPv4 timeout)" in labels
    assert "ip -s link show dev lan (IPv4 timeout)" in labels
    assert "dmesg (IPv4 timeout on lan)" in labels
    job_entries = [
        entry
        for entry in diagnostics
        if entry["label"] == "systemctl list-jobs (IPv4 timeout on lan)"
    ]
    assert job_entries, "expected systemctl list-jobs artifact to be catalogued"
    for entry in job_entries:
        assert Path(entry["path"]).exists()

    failed_units_entries = [
        entry
        for entry in diagnostics
        if entry["label"]
        == "systemctl list-units --failed (IPv4 timeout on lan)"
    ]
    assert (
        failed_units_entries
    ), "expected systemctl list-units --failed artifact to be catalogued"
    for entry in failed_units_entries:
        assert Path(entry["path"]).exists()

    networkd_status_entries = [
        entry
        for entry in diagnostics
        if entry["label"] == "systemctl status systemd-networkd (IPv4 timeout)"
    ]
    assert (
        networkd_status_entries
    ), "expected systemctl status systemd-networkd artifact to be catalogued"
    for entry in networkd_status_entries:
        assert Path(entry["path"]).exists()

    networkd_journal_entries = [
        entry
        for entry in diagnostics
        if entry["label"]
        == "journalctl -u systemd-networkd.service -b (IPv4 timeout)"
    ]
    assert (
        networkd_journal_entries
    ), "expected systemd-networkd journal artifact to be catalogued"
    for entry in networkd_journal_entries:
        assert Path(entry["path"]).exists()

    link_stats_entries = [
        entry
        for entry in diagnostics
        if entry["label"] == "ip -s link show dev lan (IPv4 timeout)"
    ]
    assert link_stats_entries, "expected ip -s link show artifact to be catalogued"
    for entry in link_stats_entries:
        assert Path(entry["path"]).exists()

    ip_addr_entries = [
        entry
        for entry in diagnostics
        if entry["label"] == "ip addr show dev lan (IPv4 timeout)"
    ]
    assert ip_addr_entries, "expected ip addr artifact to be catalogued"
    for entry in ip_addr_entries:
        assert Path(entry["path"]).exists()

    ip_route_entries = [
        entry
        for entry in diagnostics
        if entry["label"] == "ip route show dev lan (IPv4 timeout)"
    ]
    assert ip_route_entries, "expected ip route artifact to be catalogued"
    for entry in ip_route_entries:
        assert Path(entry["path"]).exists()

    dmesg_entries = [
        entry
        for entry in diagnostics
        if entry["label"] == "dmesg (IPv4 timeout on lan)"
    ]
    assert dmesg_entries, "expected dmesg artifact to be catalogued"
    for entry in dmesg_entries:
        assert Path(entry["path"]).exists()

    assert journal_calls == [
        ("pre-nixos.service", True),
        ("systemd-networkd.service", True),
    ]


def test_unit_inactive_timeout_records_failed_units(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Unit inactivity timeouts should snapshot failed units alongside jobs."""

    iso_path = tmp_path / "sample.iso"
    store_path = tmp_path / "store"
    disk_image = tmp_path / "disk.img"
    harness_log = tmp_path / "harness.log"
    serial_log = tmp_path / "serial.log"
    metadata_path = tmp_path / "metadata.json"

    iso_path.write_text("", encoding="utf-8")
    store_path.mkdir()
    disk_image.write_text("", encoding="utf-8")
    harness_log.write_text("", encoding="utf-8")
    serial_log.write_text("serial line\n", encoding="utf-8")

    artifact = BootImageBuild(
        iso_path=iso_path,
        store_path=store_path,
        deriver="sample.drv",
        nar_hash="sha256-sample",
        root_key_fingerprint="SHA256:sample",
    )

    write_boot_image_metadata(
        metadata_path,
        artifact=artifact,
        harness_log=harness_log,
        serial_log=serial_log,
        qemu_command=["qemu", "--version"],
        disk_image=disk_image,
        ssh_host="127.0.0.1",
        ssh_port=2222,
        ssh_executable="/usr/bin/ssh",
    )

    class DummyChild:
        def __init__(self) -> None:
            self.before = ""

    vm = object.__new__(BootImageVM)
    vm.child = DummyChild()
    vm.log_path = serial_log
    vm.harness_log_path = harness_log
    vm.metadata_path = metadata_path
    vm.ssh_port = 2222
    vm.ssh_host = "127.0.0.1"
    vm.ssh_executable = "/usr/bin/ssh"
    vm.artifact = artifact
    vm.qemu_command = ("qemu", "--version")
    vm.disk_image = disk_image
    vm._transcript = []
    vm._has_root_privileges = False
    vm._log_dir = metadata_path.parent
    vm._diagnostic_dir = metadata_path.parent / "diagnostics"
    vm._diagnostic_dir.mkdir(exist_ok=True)
    vm._diagnostic_counter = 0
    vm._escalation_diagnostics = []

    commands: List[str] = []
    journal_calls: List[Tuple[str, bool]] = []

    def fake_run(command: str, *, timeout: int = 180) -> str:  # type: ignore[override]
        commands.append(command)
        if command == ":":
            return ""
        if command.startswith("systemctl is-active"):
            return "activating\n"
        if command.startswith("systemctl status pre-nixos"):
            return "pre-nixos status"
        if command.startswith("systemctl list-jobs"):
            return "job output"
        if command.startswith("systemctl list-units --failed"):
            return "failed units output"
        if command.startswith("dmesg"):
            return "dmesg output"
        return ""

    def fake_collect_journal(
        unit: str, *, since_boot: bool = True
    ) -> str:  # type: ignore[override]
        journal_calls.append((unit, since_boot))
        return "journal output"

    vm.run = fake_run  # type: ignore[assignment]
    vm.collect_journal = fake_collect_journal  # type: ignore[assignment]

    time_values = iter([0.0, 0.0, 1000.0])

    def fake_time() -> float:
        try:
            return next(time_values)
        except StopIteration:
            return 1000.0

    monkeypatch.setattr("tests.test_boot_image_vm.time.time", fake_time)
    monkeypatch.setattr("tests.test_boot_image_vm.time.sleep", lambda _: None)

    with pytest.raises(AssertionError) as excinfo:
        vm.wait_for_unit_inactive("pre-nixos", timeout=1)

    message = str(excinfo.value)
    assert "systemctl list-jobs" in message
    assert any("systemctl list-jobs" in cmd for cmd in commands)
    assert "systemctl list-units --failed" in message
    assert any("systemctl list-units --failed" in cmd for cmd in commands)
    assert "systemctl status pre-nixos" in message
    assert any("systemctl status pre-nixos" in cmd for cmd in commands)
    assert "dmesg (inactive timeout for pre-nixos)" in message
    assert any(cmd.startswith("dmesg") for cmd in commands)

    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    diagnostics = metadata["diagnostics"]["artifacts"]
    labels = {entry["label"] for entry in diagnostics}
    assert "systemctl status pre-nixos (inactive timeout)" in labels
    assert "journalctl -u pre-nixos.service -b (inactive timeout)" in labels
    assert "systemctl list-jobs (inactive timeout)" in labels
    assert "systemctl list-units --failed (inactive timeout)" in labels
    assert "dmesg (inactive timeout for pre-nixos)" in labels

    failed_units_entries = [
        entry
        for entry in diagnostics
        if entry["label"] == "systemctl list-units --failed (inactive timeout)"
    ]
    assert (
        failed_units_entries
    ), "expected systemctl list-units --failed artifact to be catalogued"
    for entry in failed_units_entries:
        assert Path(entry["path"]).exists()

    journal_entries = [
        entry
        for entry in diagnostics
        if entry["label"] == "journalctl -u pre-nixos.service -b (inactive timeout)"
    ]
    assert journal_entries, "expected pre-nixos journal artifact to be catalogued"
    for entry in journal_entries:
        assert Path(entry["path"]).exists()

    job_entries = [
        entry
        for entry in diagnostics
        if entry["label"] == "systemctl list-jobs (inactive timeout)"
    ]
    assert job_entries, "expected systemctl list-jobs artifact to be catalogued"
    for entry in job_entries:
        assert Path(entry["path"]).exists()

    assert journal_calls == [("pre-nixos.service", True)]

    dmesg_entries = [
        entry
        for entry in diagnostics
        if entry["label"] == "dmesg (inactive timeout for pre-nixos)"
    ]
    assert dmesg_entries, "expected dmesg artifact to be catalogued"
    for entry in dmesg_entries:
        assert Path(entry["path"]).exists()


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
) -> BootImageVM:
    log_dir = tmp_path_factory.mktemp("boot-image-logs")
    log_path = log_dir / "serial.log"
    harness_log_path = log_dir / "harness.log"
    metadata_path = log_dir / "metadata.json"
    harness_log_path.write_text("", encoding="utf-8")
    log_handle = log_path.open("w", encoding="utf-8")
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
    )

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
        )
        try:
            yield vm
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
        raise
    finally:
        if vm is not None:
            vm.shutdown()
        else:
            try:
                child.close(force=True)
            except Exception:
                pass
        log_handle.close()


def test_boot_image_provisions_clean_disk(boot_image_vm: BootImageVM) -> None:
    boot_image_vm.assert_commands_available("disko", "findmnt", "lsblk", "wipefs")
    status = boot_image_vm.wait_for_storage_status()
    if status.get("STATE") != "applied" or status.get("DETAIL") != "auto-applied":
        journal = boot_image_vm.collect_journal("pre-nixos.service")
        pytest.fail(
            "pre-nixos did not auto-apply provisioning:\n"
            f"status={status}\n"
            f"journalctl -u pre-nixos.service:\n{journal}"
        )

    vg_output = boot_image_vm.run_as_root(
        "vgs --noheadings --separator '|' -o vg_name", timeout=120
    )
    vg_names = {line.strip() for line in vg_output.splitlines() if line.strip()}
    assert "main" in vg_names

    lv_output = boot_image_vm.run_as_root(
        "lvs --noheadings --separator '|' -o lv_name,vg_name", timeout=120
    )
    lv_pairs = {tuple(part.strip() for part in line.split("|")) for line in lv_output.splitlines() if line.strip()}
    assert ("slash", "main") in lv_pairs


def test_boot_image_configures_network(
    boot_image_vm: BootImageVM,
    boot_ssh_key_pair: SSHKeyPair,
) -> None:
    addr_lines = boot_image_vm.wait_for_ipv4()
    assert any("inet " in line for line in addr_lines)

    status = boot_image_vm.wait_for_unit_inactive("pre-nixos", timeout=180)
    assert status == "inactive"

    ssh_identity = boot_image_vm.run_ssh(
        private_key=boot_ssh_key_pair.private_key,
        command="id -un",
    )
    assert ssh_identity == "root"
