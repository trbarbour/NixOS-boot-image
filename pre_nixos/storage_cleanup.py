"""Utilities for wiping existing storage before applying a plan."""

from __future__ import annotations

import shlex
import subprocess
from typing import Callable, Iterable, List, Sequence

from .logging_utils import log_event

__all__ = [
    "WIPE_SIGNATURES",
    "DISCARD_BLOCKS",
    "OVERWRITE_RANDOM",
    "SKIP_CLEANUP",
    "perform_storage_cleanup",
]


CommandRunner = Callable[[Sequence[str]], subprocess.CompletedProcess | None]

WIPE_SIGNATURES = "wipe-signatures"
DISCARD_BLOCKS = "discard"
OVERWRITE_RANDOM = "overwrite-random"
SKIP_CLEANUP = "skip"


def _default_runner(cmd: Sequence[str]) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, check=False)


def _command_to_str(cmd: Sequence[str]) -> str:
    return " ".join(shlex.quote(part) for part in cmd)


def _commands_for_device(action: str, device: str) -> Iterable[Sequence[str]]:
    if action == WIPE_SIGNATURES:
        return (
            ("sgdisk", "--zap-all", device),
            ("wipefs", "-a", device),
        )
    if action == DISCARD_BLOCKS:
        return (
            ("sgdisk", "--zap-all", device),
            ("blkdiscard", "--force", device),
            ("wipefs", "-a", device),
        )
    if action == OVERWRITE_RANDOM:
        return (
            ("sgdisk", "--zap-all", device),
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
                if result.returncode != 0:
                    raise subprocess.CalledProcessError(result.returncode, cmd_str)
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
