"""Boot image VM controller and interaction helpers."""

from __future__ import annotations

import datetime
import re
import shlex
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, List, Optional, Tuple

import pexpect

from tests.vm.fixtures import BootImageBuild, RunTimings, VM_LOGIN_TIMEOUT
from tests.vm.metadata import DMESG_CAPTURE_COMMAND, record_boot_image_diagnostic

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
    """
    ,
    re.VERBOSE,
)

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
    run_timings: Optional[RunTimings] = None
    qemu_version: Optional[str] = None
    qemu_command: Optional[Tuple[str, ...]] = None
    disk_image: Optional[Path] = None
    boot_started_at: Optional[float] = None
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
        if (
            self.run_timings is not None
            and self.boot_started_at is not None
            and self.run_timings.boot_to_login_seconds is None
        ):
            self.run_timings.boot_to_login_seconds = (
                time.perf_counter() - self.boot_started_at
            )

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

    def _synchronise_prompt(self, *, context: str, timeout: int = 120) -> None:
        """Flush stray console output so the next command begins at the prompt."""

        self.child.sendline("")
        try:
            self.child.expect(SHELL_PROMPT, timeout=timeout)
        except pexpect.TIMEOUT as exc:  # pragma: no cover - integration timing
            self._raise_with_transcript(
                f"Timed out while resynchronising prompt during {context}: {exc}"
            )
        except pexpect.EOF as exc:  # pragma: no cover - integration timing
            self._raise_with_transcript(
                f"Unexpected EOF while resynchronising prompt during {context}: {exc}"
            )
        except pexpect.ExceptionPexpect as exc:  # pragma: no cover - defensive
            self._raise_with_transcript(
                "pexpect error while resynchronising prompt during "
                f"{context}: {exc}"
            )

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

    def collect_base_diagnostics(self) -> List[Tuple[str, Path]]:
        """Capture baseline diagnostics to persist alongside failed runs."""

        collected: List[Tuple[str, Path]] = []

        try:
            collected.append(self._capture_dmesg("post-test teardown"))
        except Exception as exc:  # pragma: no cover - best effort cleanup
            self._log_step(
                "Failed to capture dmesg during teardown", body=repr(exc)
            )

        try:
            journal = self.collect_journal("pre-nixos.service")
            journal_path = self._write_diagnostic_artifact(
                "pre-nixos-journal", journal, metadata_label="pre-nixos journal"
            )
            collected.append(("journalctl -u pre-nixos.service -b", journal_path))
        except Exception as exc:  # pragma: no cover - best effort cleanup
            self._log_step(
                "Failed to collect pre-nixos journal during teardown", body=repr(exc)
            )

        try:
            log_listing = self.run_as_root(
                "ls -1 /tmp/pre-nixos*.log 2>/dev/null || true", timeout=120
            )
            for raw_path in log_listing.splitlines():
                vm_path = raw_path.strip()
                if not vm_path:
                    continue
                content = self.run_as_root(
                    f"cat {vm_path} 2>/dev/null || true", timeout=180
                )
                label = f"pre-nixos log {Path(vm_path).name}"
                artifact_path = self._write_diagnostic_artifact(
                    Path(vm_path).name,
                    content,
                    metadata_label=label,
                )
                collected.append((label, artifact_path))
        except Exception as exc:  # pragma: no cover - best effort cleanup
            self._log_step(
                "Failed to collect pre-nixos logs during teardown", body=repr(exc)
            )

        return collected

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
        body: Optional[str] = None,
    ) -> None:
        self._record_child_output()
        serial_tail = self._read_serial_tail()
        transcript = "\n".join(self._transcript)

        if body is not None:
            self._log_step(message, body=body)
        else:
            self._log_step(message)

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

        if body:
            context_path = self._write_diagnostic_artifact(
                "failure-context",
                body,
                metadata_label="Failure context",
            )
            collected_diagnostics.append(("failure context", context_path))

        details = [message]
        details.append("Boot image artifact metadata:")
        details.extend(self._format_artifact_metadata())
        if body:
            details.append("Failure context:")
            details.append(body)
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

    def _configure_prompt(self, *, context: str = "shell") -> None:
        """Configure the shell prompt with a sentinel to absorb stray output."""

        marker = f"__PROMPT_READY__{int(time.time() * 1000)}__"
        command = f"export PS1='{SHELL_PROMPT}'; printf '{marker}\\n'"
        self.child.sendline(command)
        try:
            self._expect_normalised([marker], timeout=120)
            self._expect_normalised([SHELL_PROMPT], timeout=120)
        except pexpect.TIMEOUT as exc:  # pragma: no cover - integration timing
            self._raise_with_transcript(
                f"Timed out while configuring shell prompt during {context}: {exc}"
            )
        self._log_step(
            "Shell prompt configured for interaction", body=f"context={context}"
        )

    def _set_shell_prompt(self) -> None:
        self._configure_prompt()

    @staticmethod
    def _extract_uid_from_block(block: str, marker: str) -> Optional[str]:
        """Parse a UID surrounded by markers even when extra lines are present."""

        cleaned = block.replace("\r", "")
        positions: List[int] = []
        start = cleaned.find(marker)
        while start != -1:
            positions.append(start)
            start = cleaned.find(marker, start + len(marker))

        for idx in range(len(positions) - 1):
            between = cleaned[
                positions[idx] + len(marker) : positions[idx + 1]
            ]
            digit_match = re.search(r"\d+", between)
            if digit_match:
                return digit_match.group(0)
        return None

    def _read_uid(self) -> str:
        """Return the numeric UID reported by ``id -u`` using marker guards."""

        marker = f"__UID_MARK__{int(time.time() * 1000)}__"
        uid_command = f"printf '{marker}%s{marker}\\n' \"$(id -u)\""

        for attempt in range(2):
            self._synchronise_prompt(
                context=f"uid validation attempt {attempt + 1}", timeout=120
            )
            try:
                block = self.run(uid_command, timeout=180)
                uid_value = self._extract_uid_from_block(block, marker)
                if uid_value is None:
                    fallback_sources = []
                    fallback_block = getattr(self.child, "before", "")
                    if fallback_block:
                        fallback_sources.append(
                            ("child buffer", fallback_block)
                        )
                    log_path = getattr(self, "log_path", None)
                    if log_path is not None:
                        try:
                            serial_tail = "\n".join(self._read_serial_tail(200))
                        except Exception:
                            serial_tail = ""
                        if serial_tail:
                            fallback_sources.append(
                                ("serial log tail", serial_tail)
                            )
                    for source, candidate in fallback_sources:
                        uid_value = self._extract_uid_from_block(
                            candidate, marker
                        )
                        if uid_value is not None:
                            self._log_step(
                                "Recovered UID marker after parse failure",
                                body=(
                                    f"attempt={attempt + 1}, source={source}, "
                                    f"uid={uid_value}"
                                ),
                            )
                            return uid_value
                if uid_value is not None:
                    return uid_value
                raise ValueError(
                    f"UID marker not found in output block: {block!r}"
                )
            except (pexpect.TIMEOUT, pexpect.EOF, pexpect.ExceptionPexpect) as exc:
                self._log_step(
                    "Failed to parse id -u output; resynchronising prompt before retry",
                    body=(
                        f"attempt={attempt + 1}, error={exc}, buffer="
                        f"{getattr(self.child, 'before', '')}"
                    ),
                )
            except AssertionError as exc:
                self._log_step(
                    "Failed to parse id -u output; resynchronising prompt before retry",
                    body=(
                        f"attempt={attempt + 1}, error={exc}, buffer="
                        f"{getattr(self.child, 'before', '')}"
                    ),
                )
            except ValueError as exc:
                self._log_step(
                    "Failed to parse id -u output; resynchronising prompt before retry",
                    body=(
                        f"attempt={attempt + 1}, error={exc}, block={exc.args[0]}"
                    ),
                )
            self._configure_prompt(context="uid validation resync")

        self._raise_with_transcript(
            "Failed to parse id -u output while validating shell privileges",
        )
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
        self._configure_prompt(context="sudo -i")
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
        self._configure_prompt(context="su -")
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

        self._configure_prompt(context="initial login")

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

    def run_as_root_checked(self, command: str, *, timeout: int = 180) -> str:
        """Execute a root command and assert a zero exit status."""

        wrapped = (
            "{ "
            f"{command}; "
            "printf '\n__EXIT__=%s\n' $?; "
            "}"
        )
        output = self.run_as_root(wrapped, timeout=timeout)
        lines = [line for line in output.splitlines() if line.strip()]
        exit_lines = [line for line in lines if line.startswith("__EXIT__=")]
        if not exit_lines:
            self._raise_with_transcript(
                "Missing exit marker while running checked command", body=output
            )
        exit_status = exit_lines[-1].split("=", 1)[-1].strip()
        if exit_status != "0":
            self._raise_with_transcript(
                f"Command exited with status {exit_status}", body=output
            )
        return "\n".join(line for line in lines if not line.startswith("__EXIT__="))

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
                if (
                    self.run_timings is not None
                    and self.boot_started_at is not None
                    and self.run_timings.boot_to_ssh_seconds is None
                ):
                    self.run_timings.boot_to_ssh_seconds = (
                        time.perf_counter() - self.boot_started_at
                    )
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



__all__ = ["ANSI_ESCAPE_PATTERN", "BootImageVM", "SHELL_PROMPT"]
