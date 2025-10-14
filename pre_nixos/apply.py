"""Apply storage plans."""

from __future__ import annotations

import json
import os
import shlex
import shutil
import subprocess
import textwrap
from pathlib import Path
from typing import Any, Dict, List, Tuple

from .logging_utils import log_event

DISKO_CONFIG_PATH = Path("/var/log/pre-nixos/disko-config.nix")
_DISKO_MODE_CACHE: Tuple[str, bool] | None = None


def _run(cmd: str, execute: bool) -> None:
    """Run ``cmd`` when ``execute`` is ``True``."""

    log_event("pre_nixos.apply.command.start", command=cmd, execute=execute)
    if not execute:
        log_event(
            "pre_nixos.apply.command.skip",
            command=cmd,
            reason="execution disabled",
        )
        return
    exe = shlex.split(cmd)[0]
    if shutil.which(exe) is None:
        log_event(
            "pre_nixos.apply.command.skip",
            command=cmd,
            reason="executable not found",
        )
        return
    result = subprocess.run(cmd, shell=True, check=False)
    status = "success" if result.returncode == 0 else "error"
    log_event(
        "pre_nixos.apply.command.finished",
        command=cmd,
        status=status,
        returncode=result.returncode,
    )
    if result.returncode != 0:
        raise subprocess.CalledProcessError(result.returncode, cmd)


def apply_plan(plan: Dict[str, Any], dry_run: bool = False) -> List[str]:
    """Apply a storage plan."""

    commands: List[str] = []
    execute = not dry_run and os.environ.get("PRE_NIXOS_EXEC") == "1"

    disko_mode, allow_yes_wipe = _select_disko_mode()

    log_event(
        "pre_nixos.apply.apply_plan.start",
        dry_run=dry_run,
        execute=execute,
    )

    devices = plan.get("disko") or {}
    if not devices:
        log_event("pre_nixos.apply.apply_plan.no_devices")
        return commands

    config_text = _render_disko_config(devices)
    config_path = Path(plan.get("disko_config_path", DISKO_CONFIG_PATH))
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(config_text, encoding="utf-8")
    log_event(
        "pre_nixos.apply.apply_plan.config_written",
        config_path=config_path,
    )

    cmd_parts = ["disko", "--mode", disko_mode]
    if allow_yes_wipe and disko_mode == "destroy,format,mount":
        cmd_parts.append("--yes-wipe-all-disks")
    cmd_parts.extend(["--root-mountpoint", "/mnt", str(config_path)])
    cmd = " ".join(cmd_parts)
    commands.append(cmd)
    log_event(
        "pre_nixos.apply.apply_plan.command_scheduled",
        command=cmd,
    )
    _run(cmd, execute)

    log_event(
        "pre_nixos.apply.apply_plan.finished",
        commands=commands,
    )
    return commands


def _render_disko_config(devices: Dict[str, Any]) -> str:
    """Return a Nix expression for ``disko.devices``."""

    json_blob = json.dumps(devices, indent=2, sort_keys=True)
    body = textwrap.indent(json_blob, "    ")
    return "{\n  disko.devices = builtins.fromJSON ''\n" + body + "\n  '';\n}\n"


def _select_disko_mode() -> Tuple[str, bool]:
    """Return the preferred disko mode and whether ``--yes-wipe-all-disks`` is supported."""

    global _DISKO_MODE_CACHE
    if _DISKO_MODE_CACHE is not None:
        return _DISKO_MODE_CACHE

    exe = shutil.which("disko")
    if exe is None:
        log_event(
            "pre_nixos.apply.disko_mode",
            mode="disko",
            supports_yes_wipe=False,
            reason="executable not found",
        )
        _DISKO_MODE_CACHE = ("disko", False)
        return _DISKO_MODE_CACHE

    try:
        result = subprocess.run(
            [exe, "--help"],
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError as exc:  # pragma: no cover - subprocess failure is rare
        log_event(
            "pre_nixos.apply.disko_mode",
            mode="disko",
            supports_yes_wipe=False,
            reason=str(exc),
        )
        _DISKO_MODE_CACHE = ("disko", False)
        return _DISKO_MODE_CACHE

    help_text = (result.stdout or "") + (result.stderr or "")
    supports_combined = "destroy,format,mount" in help_text
    supports_yes = "--yes-wipe-all-disks" in help_text and supports_combined
    mode = "destroy,format,mount" if supports_combined else "disko"

    log_event(
        "pre_nixos.apply.disko_mode",
        mode=mode,
        supports_yes_wipe=supports_yes,
        detected=True,
    )
    _DISKO_MODE_CACHE = (mode, supports_yes)
    return _DISKO_MODE_CACHE
