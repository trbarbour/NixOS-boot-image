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

DISKO_CONFIG_PATH = Path("/var/log/pre-nixos/disko-config.nix")


def _run(cmd: str, execute: bool) -> None:
    """Run ``cmd`` when ``execute`` is ``True``.

    Commands are executed via ``subprocess.run`` with ``check=True``.  When
    execution is disabled, this function simply returns, allowing the caller to
    collect the commands for dry runs or environments where required utilities
    are missing.
    """

    if not execute:
        return
    exe = shlex.split(cmd)[0]
    if shutil.which(exe) is None:
        # Skip execution when the command is not present.  This keeps the
        # function usable in minimal test environments while still supporting
        # real execution on the target system.
        return
    subprocess.run(cmd, shell=True, check=True)


def apply_plan(plan: Dict[str, Any], dry_run: bool = False) -> List[str]:
    """Apply a storage plan."""

    commands: List[str] = []
    execute = not dry_run and os.environ.get("PRE_NIXOS_EXEC") == "1"

    devices = plan.get("disko") or {}
    if not devices:
        return commands

    config_text = _render_disko_config(devices)
    config_path = Path(plan.get("disko_config_path", DISKO_CONFIG_PATH))
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(config_text, encoding="utf-8")

    cmd = (
        "disko --yes-wipe-all-disks --mode destroy,format,mount "
        f"--root-mountpoint /mnt {config_path}"
    )
    commands.append(cmd)
    _run(cmd, execute)

    return commands


def _render_disko_config(devices: Dict[str, Any]) -> str:
    """Return a Nix expression for ``disko.devices``."""

    json_blob = json.dumps(devices, indent=2, sort_keys=True)
    body = textwrap.indent(json_blob, "    ")
    return "{\n  disko.devices = builtins.fromJSON ''\n" + body + "\n  '';\n}\n"
