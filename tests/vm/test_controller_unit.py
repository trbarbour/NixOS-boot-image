"""Unit coverage for the ``BootImageVM`` controller diagnostics and helpers."""

from __future__ import annotations

import importlib.util
import json
import re
import subprocess
import time
from pathlib import Path
from typing import List

import pytest

pexpect_spec = importlib.util.find_spec("pexpect")
if pexpect_spec is None:  # pragma: no cover - environment specific
    pexpect = None  # type: ignore[assignment]
else:  # pragma: no cover - exercised in integration environments
    import pexpect  # type: ignore

from tests.vm.controller import BootImageVM, SHELL_PROMPT
from tests.vm.fixtures import BootImageBuild, probe_qemu_version
from tests.vm.metadata import write_boot_image_metadata

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



def test_extract_uid_from_block_handles_noise() -> None:
    """UID extraction should survive stray console output around markers."""

    marker = "__UID_MARK__123__"
    noisy_block = """
    [nixos@nixos:~]$ export PS1='PRE-NIXOS> '; printf '__PROMPT_READY__1700000000000__'\n
    __PROMPT_READY__1700000000000__
    PRE-NIXOS> printf '__UID_MARK__123__%s__UID_MARK__123__' "$(id -u)"
    PRE-NIXOS> __UID_MARK__123__
    0
    __UID_MARK__123__
    PRE-NIXOS>
    """

    uid = BootImageVM._extract_uid_from_block(noisy_block, marker)

    assert uid == "0"

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
        "tests.vm.controller.subprocess.run",
        fake_run,
    )
    monkeypatch.setattr("tests.vm.controller.time.monotonic", fake_monotonic)
    monkeypatch.setattr("tests.vm.controller.time.sleep", lambda _: None)

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

    monkeypatch.setattr("tests.vm.controller.time.time", fake_time)
    monkeypatch.setattr("tests.vm.controller.time.sleep", lambda _: None)

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

    monkeypatch.setattr("tests.vm.controller.time.time", fake_time)
    monkeypatch.setattr("tests.vm.controller.time.sleep", lambda _: None)

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

    monkeypatch.setattr("tests.vm.controller.time.time", fake_time)
    monkeypatch.setattr("tests.vm.controller.time.sleep", lambda _: None)

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


def test_read_uid_uses_markers_to_filter_noise(monkeypatch: pytest.MonkeyPatch) -> None:
    """Marker-wrapped UID output should be returned even with extra lines."""

    import tests.vm.controller as controller

    vm = object.__new__(BootImageVM)
    vm._log_step = lambda *args, **kwargs: None  # type: ignore[assignment]
    vm._transcript = []  # type: ignore[assignment]
    monkeypatch.setattr(controller.time, "time", lambda: 1.0)

    marker = "__UID_MARK__1000__"
    vm._configure_prompt = lambda *args, **kwargs: None  # type: ignore[assignment]
    vm._synchronise_prompt = (  # type: ignore[assignment]
        lambda *args, **kwargs: None
    )
    vm._raise_with_transcript = lambda message: (_ for _ in ()).throw(AssertionError(message))  # type: ignore[assignment]

    class StubChild:
        def __init__(self) -> None:
            self.before = ""
            self.match = None
            self._output = f"{marker}\n0\n{marker}\n"

        def sendline(self, command: str) -> None:  # pragma: no cover - simple stub
            marker_match = re.search(r"__UID_MARK__\d+__", command)
            active_marker = marker_match.group(0) if marker_match else marker
            self._output = f"{active_marker}\n0\n{active_marker}\n"

        def expect(self, pattern, timeout: int | None = None) -> int:
            if pattern == SHELL_PROMPT:
                self.before = self._output
                return 0
            if isinstance(pattern, re.Pattern):
                self.match = pattern.search(self._output)
                self.before = self._output
                if self.match:
                    return 0
                raise pexpect.TIMEOUT("uid marker not found")
            raise AssertionError(f"Unexpected pattern: {pattern!r}")

    vm.child = StubChild()  # type: ignore[assignment]

    assert vm._read_uid() == "0"


def test_read_uid_raises_when_marker_missing() -> None:
    """UID parsing should fail loudly if the marker is absent."""

    vm = object.__new__(BootImageVM)
    attempts = []

    def stub_log_step(self, message: str, body: str | None = None) -> None:
        attempts.append(message)

    def stub_configure_prompt(self, *, context: str = "shell") -> None:
        attempts.append(context)

    def stub_raise_with_transcript(self, message: str) -> None:
        raise AssertionError(message)

    class StubChild:
        def __init__(self) -> None:
            self.before = ""
            self.match = None
            self.outputs = ["noise without marker", "still missing"]

        def sendline(self, command: str) -> None:  # pragma: no cover - simple stub
            self._current = self.outputs.pop(0)

        def expect(self, pattern, timeout: int | None = None) -> int:
            if pattern == SHELL_PROMPT:
                self.before = ""
                return 0
            if isinstance(pattern, re.Pattern):
                self.match = pattern.search(self._current)
                self.before = self._current
                if self.match:
                    return 0
                raise pexpect.TIMEOUT("uid marker not found")
            raise AssertionError(f"Unexpected pattern: {pattern!r}")

    vm._log_step = stub_log_step.__get__(vm, BootImageVM)
    vm._configure_prompt = stub_configure_prompt.__get__(vm, BootImageVM)
    vm._synchronise_prompt = (  # type: ignore[assignment]
        lambda *args, **kwargs: None
    )
    vm._raise_with_transcript = stub_raise_with_transcript.__get__(vm, BootImageVM)
    vm.child = StubChild()  # type: ignore[assignment]

    with pytest.raises(AssertionError):
        vm._read_uid()

    assert attempts.count("uid validation resync") == 2


def test_read_uid_resynchronises_after_parse_failure() -> None:
    """UID parsing retries after prompt resynchronisation when markers are missing."""

    vm = object.__new__(BootImageVM)
    contexts: List[str] = []

    def stub_log_step(self, message: str, body: str | None = None) -> None:
        contexts.append(message)

    vm._transcript = []  # type: ignore[assignment]
    vm._log_step = stub_log_step.__get__(vm, BootImageVM)

    def stub_configure_prompt(self, *, context: str = "shell") -> None:
        contexts.append(context)

    class StubChild:
        def __init__(self) -> None:
            self.before = ""
            self.match = None
            self.outputs = ["noise without marker", "marker"]

        def sendline(self, command: str) -> None:  # pragma: no cover - simple stub
            marker_match = re.search(r"__UID_MARK__\d+__", command)
            marker_value = marker_match.group(0) if marker_match else "__UID_MARK__missing__"
            next_output = self.outputs.pop(0)
            if next_output == "marker":
                self._current = f"{marker_value}\n0\n{marker_value}\n"
            else:
                self._current = next_output

        def expect(self, pattern, timeout: int | None = None) -> int:
            if pattern == SHELL_PROMPT:
                self.before = self._current
                return 0
            if isinstance(pattern, re.Pattern):
                self.match = pattern.search(self._current)
                self.before = self._current
                if self.match:
                    return 0
                raise pexpect.TIMEOUT("uid marker not found")
            raise AssertionError(f"Unexpected pattern: {pattern!r}")

    vm._log_step = stub_log_step.__get__(vm, BootImageVM)
    vm._configure_prompt = stub_configure_prompt.__get__(vm, BootImageVM)
    vm._synchronise_prompt = (  # type: ignore[assignment]
        lambda *args, **kwargs: None
    )
    vm._raise_with_transcript = lambda message: (_ for _ in ()).throw(AssertionError(message))  # type: ignore[assignment]
    vm.child = StubChild()  # type: ignore[assignment]

    uid = vm._read_uid()

    assert uid == "0"
    assert "uid validation resync" in contexts


