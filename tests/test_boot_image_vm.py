"""Integration tests that exercise the boot image inside a virtual machine."""

from __future__ import annotations

import os
import re
import shutil
import socket
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

import pytest

try:
    import pexpect
except ImportError:  # pragma: no cover - handled by pytest skip
    pexpect = None  # type: ignore


REPO_ROOT = Path(__file__).resolve().parents[1]
SHELL_PROMPT = "PRE-NIXOS> "

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
def boot_image_iso(
    nix_executable: str,
    boot_ssh_key_pair: SSHKeyPair,
) -> Path:
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
    return _resolve_iso_path(store_path)


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


@dataclass
class BootImageVM:
    """Minimal controller for interacting with the boot image via serial and SSH."""

    child: "pexpect.spawn"
    log_path: Path
    ssh_port: int
    ssh_host: str
    ssh_executable: str

    def __post_init__(self) -> None:
        self._login()

    def _expect_normalised(self, patterns: List[str], *, timeout: int) -> int:
        compiled = self.child.compile_pattern_list([*patterns, ANSI_ESCAPE_PATTERN])
        deadline = time.monotonic() + timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise pexpect.TIMEOUT("timeout exceeded while waiting for pattern")
            idx = self.child.expect_list(compiled, timeout=remaining)
            if idx < len(patterns):
                return idx

    def _login(self) -> None:
        login_patterns = [
            r"login: ",
            r"\[nixos@[^]]+\]\$ ?",
            r"root@.*# ?",
            r"# ?",
        ]
        idx = self._expect_normalised(login_patterns, timeout=600)

        if idx == 0:
            automatic_login = False
            try:
                auto_idx = self._expect_normalised([r"\(automatic login\)"], timeout=1)
                automatic_login = auto_idx == 0
            except pexpect.TIMEOUT:
                automatic_login = False

            if not automatic_login:
                self.child.sendline("root")
                prompt_patterns = [r"Password:", r"root@.*# ?", r"# ?"]
                idx = self._expect_normalised(prompt_patterns, timeout=180)
                if idx == 0:
                    self.child.sendline("")
                    self._expect_normalised([r"root@.*# ?", r"# ?"], timeout=180)

        root_check = 'if [ "$(id -u)" -eq 0 ]; then echo __ROOT__; else echo __USER__; fi'
        self.child.sendline(root_check)
        marker_idx = self._expect_normalised([r"__ROOT__", r"__USER__"], timeout=60)
        self._expect_normalised([r"root@.*# ?", r"# ?", r"nixos@.*\$ ?"], timeout=60)

        if marker_idx == 1:
            self.child.sendline("sudo -i")
            sudo_patterns = [r"\[sudo\] password for nixos:", r"root@.*# ?", r"# ?"]
            idx = self._expect_normalised(sudo_patterns, timeout=180)
            if idx == 0:
                self.child.sendline("")
                self._expect_normalised([r"root@.*# ?", r"# ?"], timeout=180)
            else:
                self._expect_normalised([r"root@.*# ?", r"# ?"], timeout=180)

            self.child.sendline(root_check)
            marker_idx = self._expect_normalised([r"__ROOT__", r"__USER__"], timeout=60)
            self._expect_normalised([r"root@.*# ?", r"# ?"], timeout=60)
            if marker_idx != 0:
                raise AssertionError("failed to acquire root shell")

        self.child.sendline(f"export PS1='{SHELL_PROMPT}'")
        self._expect_normalised([SHELL_PROMPT], timeout=60)

    def _strip_ansi(self, text: str) -> str:
        """Remove ANSI escape sequences from command output."""

        return ANSI_ESCAPE_PATTERN.sub("", text)

    def run(self, command: str, *, timeout: int = 180) -> str:
        self.child.sendline(command)
        self.child.expect(SHELL_PROMPT, timeout=timeout)
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
                has_missing = any(line.endswith("MISSING") for line in lines)
                if not has_missing:
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
                return status
            time.sleep(5)
        raise AssertionError("timed out waiting for pre-nixos storage status")

    def wait_for_ipv4(self, iface: str = "lan", *, timeout: int = 240) -> List[str]:
        deadline = time.time() + timeout
        while time.time() < deadline:
            output = self.run(f"ip -o -4 addr show dev {iface} 2>/dev/null || true")
            lines = [line for line in output.splitlines() if line.strip()]
            if any("inet " in line for line in lines):
                return lines
            time.sleep(5)
        raise AssertionError(f"timed out waiting for IPv4 address on {iface}")

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
    boot_image_iso: Path,
    vm_disk_image: Path,
    tmp_path_factory: pytest.TempPathFactory,
    ssh_executable: str,
    ssh_forward_port: int,
) -> BootImageVM:
    log_dir = tmp_path_factory.mktemp("boot-image-logs")
    log_path = log_dir / "serial.log"
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
        str(boot_image_iso),
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
        timeout=600,
    )
    child.logfile = log_handle
    vm = BootImageVM(
        child=child,
        log_path=log_path,
        ssh_port=ssh_forward_port,
        ssh_host="127.0.0.1",
        ssh_executable=ssh_executable,
    )
    try:
        yield vm
    finally:
        vm.shutdown()
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

    vg_output = boot_image_vm.run(
        "vgs --noheadings --separator '|' -o vg_name", timeout=120
    )
    vg_names = {line.strip() for line in vg_output.splitlines() if line.strip()}
    assert "main" in vg_names

    lv_output = boot_image_vm.run(
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

    status = boot_image_vm.run("systemctl is-active pre-nixos", timeout=60)
    assert status == "inactive"

    ssh_identity = boot_image_vm.run_ssh(
        private_key=boot_ssh_key_pair.private_key,
        command="id -un",
    )
    assert ssh_identity == "root"
