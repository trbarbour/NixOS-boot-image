"""Utilities for wiping existing storage before applying a plan."""

from __future__ import annotations

from dataclasses import dataclass
import shlex
import subprocess
from typing import Callable, Iterable, List, Mapping, Sequence, Set, Tuple

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
    return subprocess.run(cmd, check=False)


def _command_to_str(cmd: Sequence[str]) -> str:
    return " ".join(shlex.quote(part) for part in cmd)


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


def _commands_for_device(action: str, device: str) -> Iterable[Sequence[str]]:
    if action == WIPE_SIGNATURES:
        return (
            ("sgdisk", "--zap-all", device),
            ("partprobe", device),
            ("wipefs", "-a", device),
        )
    if action == DISCARD_BLOCKS:
        return (
            ("sgdisk", "--zap-all", device),
            ("partprobe", device),
            ("blkdiscard", "--force", device),
            ("wipefs", "-a", device),
        )
    if action == OVERWRITE_RANDOM:
        return (
            ("sgdisk", "--zap-all", device),
            ("partprobe", device),
            ("shred", "-n", "1", "-vz", device),
            ("wipefs", "-a", device),
        )
    if action == SKIP_CLEANUP:
        return ()
    raise ValueError(f"unknown storage cleanup action: {action}")


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
    for device in devices:
        for cmd in _commands_for_device(action, device):
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
                continue
            result = runner(cmd)
            if isinstance(result, subprocess.CompletedProcess):
                if not _is_allowed_returncode(cmd, result.returncode):
                    raise subprocess.CalledProcessError(result.returncode, cmd_str)
                if result.returncode != 0:
                    log_event(
                        "pre_nixos.cleanup.command_nonzero",
                        action=action,
                        device=device,
                        command=cmd_str,
                        returncode=result.returncode,
                    )
            elif result is not None:
                raise TypeError("Command runner must return CompletedProcess or None")
    log_event(
        "pre_nixos.cleanup.finished",
        action=action,
        devices=list(devices),
        execute=execute,
        commands=scheduled,
    )
    return scheduled
