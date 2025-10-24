"""Integration tests that exercise the boot image inside a virtual machine."""

from __future__ import annotations

import datetime
import json
import os
import re
import shutil
import socket
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

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


def _require_executable(executable: str) -> str:
    path = shutil.which(executable)
    if path is None:
        pytest.skip(f"required executable '{executable}' is not available in PATH")
    return path


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
    ssh_port: int
    ssh_host: str
    ssh_executable: str
    artifact: BootImageBuild
    _transcript: List[str] = field(default_factory=list, init=False, repr=False)
    _has_root_privileges: bool = field(default=False, init=False, repr=False)

    def __post_init__(self) -> None:
        self._log_step(
            "Boot image artifact metadata",
            body="\n".join(self._format_artifact_metadata()),
        )
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

    def _raise_with_transcript(self, message: str) -> None:
        self._record_child_output()
        serial_tail = self._read_serial_tail()
        if serial_tail:
            self._log_step(
                f"Serial log tail (last {len(serial_tail)} lines)",
                body="\n".join(serial_tail),
            )
        transcript = "\n".join(self._transcript)
        details = [message]
        details.append("Boot image artifact metadata:")
        details.extend(self._format_artifact_metadata())
        if transcript:
            details.append("Login transcript:")
            details.append(transcript)
        if serial_tail:
            details.append(f"Serial log tail (last {len(serial_tail)} lines):")
            details.append("\n".join(serial_tail))
        details.append(f"Harness log: {self.harness_log_path}")
        details.append(f"Serial log: {self.log_path}")
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
        uid = self.child.match.group(1)
        self._expect_normalised([SHELL_PROMPT], timeout=60)
        return uid

    def _escalate_with_sudo(self) -> bool:
        """Attempt to escalate privileges with ``sudo -i``."""

        self._log_step("Attempting to escalate with sudo -i")
        self.child.sendline("sudo -i")
        sudo_patterns = [r"\[sudo\] password for nixos:", r"root@.*# ?", r"# ?"]
        try:
            idx = self._expect_normalised(sudo_patterns, timeout=120)
        except pexpect.TIMEOUT:
            self._log_step("sudo -i did not produce a root prompt")
            return False
        if idx == 0:
            self._log_step("Submitting empty sudo password")
            self.child.sendline("")
            try:
                self._expect_normalised([r"root@.*# ?", r"# ?"], timeout=120)
            except pexpect.TIMEOUT:
                self._log_step("sudo -i password prompt did not yield a root shell")
                return False
        self._set_shell_prompt()
        uid_output = self._read_uid()
        self._has_root_privileges = uid_output == "0"
        self._log_step(f"id -u after sudo -i returned: {uid_output!r}")
        if self._has_root_privileges:
            self._log_step("Successfully escalated privileges with sudo -i")
            return True
        self._log_step("sudo -i completed without root privileges")
        return False

    def _escalate_with_su(self) -> bool:
        """Attempt to escalate privileges with ``su -``."""

        self._log_step("Attempting to escalate with su -")
        self.child.sendline("su -")
        su_patterns = [r"Password:", r"root@.*# ?", r"# ?"]
        try:
            idx = self._expect_normalised(su_patterns, timeout=120)
        except pexpect.TIMEOUT:
            self._log_step("su - did not produce a root prompt")
            return False
        if idx == 0:
            self._log_step("Submitting empty root password for su -")
            self.child.sendline("")
            try:
                self._expect_normalised([r"root@.*# ?", r"# ?"], timeout=120)
            except pexpect.TIMEOUT:
                self._log_step("su - password prompt did not yield a root shell")
                return False
        self._set_shell_prompt()
        uid_output = self._read_uid()
        self._has_root_privileges = uid_output == "0"
        self._log_step(f"id -u after su - returned: {uid_output!r}")
        if self._has_root_privileges:
            self._log_step("Successfully escalated privileges with su -")
            return True
        self._log_step("su - completed without root privileges")
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
        self._raise_with_transcript(
            "timed out waiting for pre-nixos storage status\n"
            f"journalctl -u pre-nixos.service -b:\n{journal}\n"
            f"systemctl status pre-nixos:\n{unit_status}"
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
        self._raise_with_transcript(
            f"timed out waiting for IPv4 address on {iface}\n"
            f"journalctl -u pre-nixos.service -b:\n{journal}\n"
            f"systemctl status pre-nixos:\n{unit_status}"
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
        self._raise_with_transcript(
            "\n".join(
                [
                    f"Unit {unit} did not reach inactive state within {timeout}s",
                    f"systemctl status {unit}:\n{unit_status}",
                    f"journalctl -u {journal_unit} -b:\n{journal}",
                ]
            )
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
            result = subprocess.run(
                ssh_cmd,
                check=False,
                capture_output=True,
                text=True,
            )
            if result.returncode == 0:
                return result.stdout.strip()
            last_stdout = result.stdout
            last_stderr = result.stderr
            time.sleep(interval)

        raise AssertionError(
            "SSH command failed after retries: "
            f"stdout={last_stdout!r} stderr={last_stderr!r}"
        )


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
            ssh_port=ssh_forward_port,
            ssh_host="127.0.0.1",
            ssh_executable=ssh_executable,
            artifact=boot_image_build,
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
