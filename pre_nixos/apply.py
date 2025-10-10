"""Apply storage plans."""

from __future__ import annotations

import json
import os
import shlex
import shutil
import subprocess
import textwrap
from pathlib import Path
from typing import Any, Dict, List

from .logging_utils import log_event

DISKO_CONFIG_PATH = Path("/var/log/pre-nixos/disko-config.nix")


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

    cmd = (
        "disko --yes-wipe-all-disks --mode destroy,format,mount "
        f"--root-mountpoint /mnt {config_path}"
    )
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
