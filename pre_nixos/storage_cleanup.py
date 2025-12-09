"""Utilities for wiping existing storage before applying a plan."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
import shlex
import subprocess
from typing import Callable, Iterable, List, Mapping, Sequence, Set, Tuple

from . import storage_detection
from .logging_utils import log_event

__all__ = [
    "WIPE_SIGNATURES",
    "DISCARD_BLOCKS",
    "OVERWRITE_RANDOM",
    "SKIP_CLEANUP",
    "CleanupOption",
    "CLEANUP_OPTIONS",
    "perform_storage_cleanup",
]


CommandRunner = Callable[[Sequence[str]], subprocess.CompletedProcess | None]

WIPE_SIGNATURES = "wipe-signatures"
DISCARD_BLOCKS = "discard"
OVERWRITE_RANDOM = "overwrite-random"
SKIP_CLEANUP = "skip"


@dataclass(frozen=True)
class CleanupOption:
    """Choice presented to operators when wiping existing storage."""

    key: str
    action: str | None
    description: str


CLEANUP_OPTIONS: Tuple[CleanupOption, ...] = (
    CleanupOption(
        "1",
        WIPE_SIGNATURES,
        "Wipe partition tables and filesystem signatures (fast)",
    ),
    CleanupOption(
        "2",
        DISCARD_BLOCKS,
        "Discard all blocks (SSD/NVMe only)",
    ),
    CleanupOption(
        "3",
        OVERWRITE_RANDOM,
        "Overwrite the entire device with random data (slow)",
    ),
    CleanupOption("s", SKIP_CLEANUP, "Skip wiping and continue"),
    CleanupOption("q", None, "Abort without making changes"),
)


def _default_runner(cmd: Sequence[str]) -> subprocess.CompletedProcess:
    """Run *cmd* with output captured to avoid noisy stderr/tty chatter."""

    return subprocess.run(
        cmd,
        check=False,
        capture_output=True,
        text=True,
    )


def _command_to_str(cmd: Sequence[str]) -> str:
    return " ".join(shlex.quote(part) for part in cmd)


def _command_output_fields(result: subprocess.CompletedProcess) -> dict[str, str]:
    """Return a mapping of non-empty output streams for logging."""

    fields = {}
    stdout = (result.stdout or "").strip()
    stderr = (result.stderr or "").strip()
    if stdout:
        fields["stdout"] = stdout
    if stderr:
        fields["stderr"] = stderr
    return fields


def _collect_wipefs_diagnostics(device: str) -> dict[str, object]:
    mounts_result = subprocess.run(
        ["findmnt", "-rn", "-o", "TARGET,SOURCE", "-T", device],
        capture_output=True,
        text=True,
        check=False,
    )
    mount_lines = [line for line in mounts_result.stdout.splitlines() if line.strip()]
    boot_probe_data = storage_detection.collect_boot_probe_data()
    return {"mounts": mount_lines, **boot_probe_data}


def _capture_diagnostic_output(cmd: Sequence[str]) -> str:
    """Return combined stdout/stderr from *cmd* for diagnostics."""

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError as exc:  # pragma: no cover - defensive
        return f"{cmd[0]}: {exc}"

    output = (result.stdout or "") + (result.stderr or "")
    output = output.strip()
    if output:
        return output
    if result.returncode != 0:
        return f"{cmd[0]} exited with {result.returncode}"
    return ""


def _collect_storage_stack_state() -> dict[str, object]:
    """Return a snapshot of block-layer state for diagnostics."""

    return {
        "lsblk_json": _capture_diagnostic_output(["lsblk", "--output-all", "--json"]),
        "mdadm_detail_scan": _capture_diagnostic_output(["mdadm", "--detail", "--scan"]),
        "dmsetup_tree": _capture_diagnostic_output(["dmsetup", "ls", "--tree"]),
    }


_ALLOWED_NONZERO_EXIT_CODES: Mapping[Tuple[str, ...], Set[int]] = {
    ("sgdisk", "--zap-all"): {2},
    ("partprobe",): {1},
}


def _is_allowed_returncode(cmd: Sequence[str], returncode: int) -> bool:
    """Return ``True`` when *returncode* is acceptable for *cmd*."""

    if returncode == 0:
        return True
    for prefix_length in range(len(cmd), 0, -1):
        key = tuple(cmd[:prefix_length])
        allowed = _ALLOWED_NONZERO_EXIT_CODES.get(key)
        if allowed and returncode in allowed:
            return True
    return False


def _execute_command(
    cmd: Sequence[str],
    *,
    action: str,
    device: str,
    execute: bool,
    runner: CommandRunner,
    scheduled: List[str],
    tolerate_failure: bool = False,
) -> subprocess.CompletedProcess:
    cmd_str = _command_to_str(cmd)
    scheduled.append(cmd_str)
    log_event(
        "pre_nixos.cleanup.command",
        action=action,
        device=device,
        command=cmd_str,
        execute=execute,
    )
    if not execute:
        return subprocess.CompletedProcess(cmd, 0)

    result = runner(cmd)
    if result is None:
        return subprocess.CompletedProcess(cmd, 0)
    if isinstance(result, subprocess.CompletedProcess):
        if not _is_allowed_returncode(cmd, result.returncode):
            if cmd[0] == "wipefs":
                diagnostics = _collect_wipefs_diagnostics(device)
                log_event(
                    "pre_nixos.cleanup.wipefs_failed",
                    action=action,
                    device=device,
                    command=cmd_str,
                    returncode=result.returncode,
                    **_command_output_fields(result),
                    **diagnostics,
                )
            if tolerate_failure:
                log_event(
                    "pre_nixos.cleanup.command_failed",
                    action=action,
                    device=device,
                    command=cmd_str,
                    returncode=result.returncode,
                    **_command_output_fields(result),
                )
                return result
            raise subprocess.CalledProcessError(
                result.returncode,
                cmd_str,
                output=result.stdout,
                stderr=result.stderr,
            )
        if result.returncode != 0:
            log_event(
                "pre_nixos.cleanup.command_nonzero",
                action=action,
                device=device,
                command=cmd_str,
                returncode=result.returncode,
                **_command_output_fields(result),
            )
        return result
    raise TypeError("Command runner must return CompletedProcess or None")


def _list_block_devices() -> list[dict[str, object]]:
    result = subprocess.run(
        [
            "lsblk",
            "--json",
            "--paths",
            "-o",
            "NAME,TYPE,MOUNTPOINT,PKNAME,FSTYPE",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return []
    try:
        parsed = json.loads(result.stdout or "{}")
    except json.JSONDecodeError:
        return []
    devices = parsed.get("blockdevices")
    return devices if isinstance(devices, list) else []


def _flatten_lsblk(entry: dict[str, object], parents: list[str]) -> Iterable[dict[str, object]]:
    name = str(entry.get("name", ""))
    children = entry.get("children") or []
    record = {
        "name": name,
        "type": entry.get("type"),
        "mountpoint": entry.get("mountpoint"),
        "pkname": entry.get("pkname"),
        "fstype": entry.get("fstype"),
        "parents": list(parents),
    }
    yield record
    for child in children:
        if isinstance(child, dict):
            yield from _flatten_lsblk(child, parents + [name])


def _build_device_hierarchy() -> tuple[list[dict[str, object]], dict[str, list[dict[str, object]]]]:
    """Return flattened lsblk data and a parent->children mapping."""

    entries: list[dict[str, object]] = []
    for entry in _list_block_devices():
        entries.extend(_flatten_lsblk(entry, []))

    children: dict[str, list[dict[str, object]]] = {}
    for entry in entries:
        parents = entry.get("parents", []) or []
        if parents:
            parent = parents[-1]
            children.setdefault(parent, []).append(entry)

    return entries, children


def _descendant_entries(device: str) -> list[dict[str, object]]:
    """Return all descendant block devices of *device*.

    Descendants are discovered via the lsblk tree and include grandchildren and
    deeper levels. The returned list is ordered depth-first so that the deepest
    nodes appear first.
    """

    _, children = _build_device_hierarchy()

    ordered: list[dict[str, object]] = []

    def visit(current: str) -> None:
        for child in children.get(current, []):
            visit(str(child.get("name", "")))
            ordered.append(child)

    visit(device)
    return ordered


def _device_usage_entries(device: str) -> list[dict[str, object]]:
    entries, _ = _build_device_hierarchy()
    relevant = [entry for entry in entries if device == entry["name"]]
    relevant.extend(_descendant_entries(device))
    relevant.sort(key=lambda entry: len(entry.get("parents", [])), reverse=True)
    return relevant


def _teardown_device_usage(
    action: str,
    device: str,
    *,
    execute: bool,
    runner: CommandRunner,
    scheduled: List[str],
) -> bool:
    success = True
    entries = _device_usage_entries(device)
    for entry in entries:
        if entry.get("name") == device:
            continue
        mountpoint = entry.get("mountpoint")
        if mountpoint:
            result = _execute_command(
                ["umount", str(mountpoint)],
                action=action,
                device=device,
                execute=execute,
                runner=runner,
                scheduled=scheduled,
                tolerate_failure=True,
            )
            if result.returncode != 0:
                success = False
        if entry.get("fstype") == "swap" or entry.get("mountpoint") == "[SWAP]":
            result = _execute_command(
                ["swapoff", str(entry.get("name"))],
                action=action,
                device=device,
                execute=execute,
                runner=runner,
                scheduled=scheduled,
                tolerate_failure=True,
            )
            if result.returncode != 0:
                success = False
        entry_type = str(entry.get("type") or "")
        if entry_type.startswith("raid"):
            result = _execute_command(
                ["mdadm", "--stop", str(entry.get("name"))],
                action=action,
                device=device,
                execute=execute,
                runner=runner,
                scheduled=scheduled,
                tolerate_failure=True,
            )
            if result.returncode != 0:
                success = False
        if entry_type in {"crypt", "dm", "lvm"}:
            result = _execute_command(
                ["dmsetup", "remove", str(entry.get("name"))],
                action=action,
                device=device,
                execute=execute,
                runner=runner,
                scheduled=scheduled,
                tolerate_failure=True,
            )
            if result.returncode != 0:
                success = False
    if not success:
        log_event(
            "pre_nixos.cleanup.teardown_failed",
            action=action,
            device=device,
            execute=execute,
            **_collect_storage_stack_state(),
        )
    return success


def _wipe_descendant_metadata(
    action: str,
    device: str,
    *,
    execute: bool,
    runner: CommandRunner,
    scheduled: List[str],
) -> bool:
    """Remove filesystem and RAID signatures from *device*'s descendants."""

    success = True
    for entry in _descendant_entries(device):
        name = str(entry.get("name") or "")
        if not name:
            continue
        result = _execute_command(
            ["wipefs", "-a", name],
            action=action,
            device=device,
            execute=execute,
            runner=runner,
            scheduled=scheduled,
            tolerate_failure=True,
        )
        if result.returncode != 0:
            success = False

        fstype = str(entry.get("fstype") or "")
        entry_type = str(entry.get("type") or "")
        if fstype == "linux_raid_member" or entry_type.startswith("raid"):
            result = _execute_command(
                ["mdadm", "--zero-superblock", "--force", name],
                action=action,
                device=device,
                execute=execute,
                runner=runner,
                scheduled=scheduled,
                tolerate_failure=True,
            )
            if result.returncode != 0:
                success = False

    if not success:
        log_event(
            "pre_nixos.cleanup.descendant_wipe_failed",
            action=action,
            device=device,
            execute=execute,
        )
    return success


def _collect_partition_refresh_diagnostics(device: str) -> dict[str, object]:
    return {
        "usage": _device_usage_entries(device),
        **storage_detection.collect_boot_probe_data(),
    }


def _refresh_partition_table(
    action: str,
    device: str,
    *,
    execute: bool,
    runner: CommandRunner,
    scheduled: List[str],
    attempts: int = 3,
    delay_seconds: float = 0.5,
) -> bool:
    for attempt in range(attempts):
        blockdev_result = _execute_command(
            ["blockdev", "--rereadpt", device],
            action=action,
            device=device,
            execute=execute,
            runner=runner,
            scheduled=scheduled,
            tolerate_failure=True,
        )
        partprobe_result = _execute_command(
            ["partprobe", device],
            action=action,
            device=device,
            execute=execute,
            runner=runner,
            scheduled=scheduled,
            tolerate_failure=True,
        )
        settle_result = _execute_command(
            ["udevadm", "settle"],
            action=action,
            device=device,
            execute=execute,
            runner=runner,
            scheduled=scheduled,
            tolerate_failure=True,
        )
        if (
            blockdev_result.returncode == 0
            and partprobe_result.returncode == 0
            and settle_result.returncode == 0
        ):
            return True
        time.sleep(delay_seconds)
    log_event(
        "pre_nixos.cleanup.partition_refresh_failed",
        action=action,
        device=device,
        execute=execute,
        **_collect_partition_refresh_diagnostics(device),
        **_collect_storage_stack_state(),
    )
    return False


def perform_storage_cleanup(
    action: str,
    devices: Sequence[str],
    *,
    execute: bool,
    runner: CommandRunner | None = None,
) -> List[str]:
    """Apply the requested storage cleanup action to *devices*.

    Returns the list of shell command strings that were scheduled. When
    ``execute`` is ``False`` the commands are only logged.
    """

    runner = runner or _default_runner
    scheduled: List[str] = []
    log_event(
        "pre_nixos.cleanup.start",
        action=action,
        devices=list(devices),
        execute=execute,
    )
    if action == SKIP_CLEANUP:
        log_event(
            "pre_nixos.cleanup.finished",
            action=action,
            devices=list(devices),
            execute=execute,
            commands=scheduled,
        )
        return scheduled

    if action not in {
        WIPE_SIGNATURES,
        DISCARD_BLOCKS,
        OVERWRITE_RANDOM,
    }:
        raise ValueError(f"unknown storage cleanup action: {action}")

    for device in devices:
        if not _teardown_device_usage(
            action,
            device,
            execute=execute,
            runner=runner,
            scheduled=scheduled,
        ):
            continue

        _wipe_descendant_metadata(
            action,
            device,
            execute=execute,
            runner=runner,
            scheduled=scheduled,
        )

        _execute_command(
            ("sgdisk", "--zap-all", device),
            action=action,
            device=device,
            execute=execute,
            runner=runner,
            scheduled=scheduled,
        )

        if not _refresh_partition_table(
            action,
            device,
            execute=execute,
            runner=runner,
            scheduled=scheduled,
        ):
            continue

        if action == DISCARD_BLOCKS:
            _execute_command(
                ("blkdiscard", "--force", device),
                action=action,
                device=device,
                execute=execute,
                runner=runner,
                scheduled=scheduled,
            )
        elif action == OVERWRITE_RANDOM:
            _execute_command(
                ("shred", "-n", "1", "-vz", device),
                action=action,
                device=device,
                execute=execute,
                runner=runner,
                scheduled=scheduled,
            )

        _execute_command(
            ("wipefs", "-a", device),
            action=action,
            device=device,
            execute=execute,
            runner=runner,
            scheduled=scheduled,
        )
    log_event(
        "pre_nixos.cleanup.finished",
        action=action,
        devices=list(devices),
        execute=execute,
        commands=scheduled,
    )
    return scheduled
