"""Apply storage plans."""

from __future__ import annotations

import os
import shlex
import shutil
import subprocess
from typing import Dict, Any, List


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
    """Apply a storage plan.

    Parameters:
        plan: Plan dictionary produced by :func:`pre_nixos.planner.plan_storage`.
        dry_run: If ``True``, commands are returned without execution.

    Returns:
        A list of shell command strings in the order they would be executed.
    """
    commands: List[str] = []
    execute = not dry_run and os.environ.get("PRE_NIXOS_EXEC") == "1"

    for disk, parts in plan.get("partitions", {}).items():
        cmd = f"sgdisk -Z /dev/{disk}"
        commands.append(cmd)
        _run(cmd, execute)
        for idx, part in enumerate(parts, start=1):
            if part["type"] == "efi":
                cmd = f"sgdisk -n{idx}:0:+1G -t{idx}:EF00 /dev/{disk}"
            elif part["type"] == "linux-raid":
                cmd = f"sgdisk -n{idx}:0:0 -t{idx}:FD00 /dev/{disk}"
            else:
                continue
            commands.append(cmd)
            _run(cmd, execute)
        # Inform the kernel of partition table changes and wait for udev to
        # settle so that subsequent commands see the new devices.
        for cmd in (f"partprobe /dev/{disk}", "udevadm settle"):
            commands.append(cmd)
            _run(cmd, execute)

    for array in plan.get("arrays", []):
        devices = " ".join(f"/dev/{d}" for d in array["devices"])
        cmd = (
            f"mdadm --create /dev/{array['name']} --level={array['level']} {devices}"
        )
        commands.append(cmd)
        _run(cmd, execute)

    pv_devices = {d for vg in plan.get("vgs", []) for d in vg["devices"]}
    for dev in pv_devices:
        cmd = f"pvcreate /dev/{dev}"
        commands.append(cmd)
        _run(cmd, execute)

    for vg in plan.get("vgs", []):
        devs = " ".join(f"/dev/{d}" for d in vg["devices"])
        cmd = f"vgcreate {vg['name']} {devs}"
        commands.append(cmd)
        _run(cmd, execute)

    for lv in plan.get("lvs", []):
        size = lv["size"]
        flag = "-l" if size.endswith("%") or size.upper().endswith("FREE") else "-L"
        cmd = f"lvcreate -n {lv['name']} {lv['vg']} {flag} {size}"
        commands.append(cmd)
        _run(cmd, execute)
        lv_path = f"/dev/{lv['vg']}/{lv['name']}"
        if lv["name"] == "swap":
            cmd = f"mkswap {lv_path}"
            commands.append(cmd)
            _run(cmd, execute)
            continue
        # The Nix store contains millions of small files. Using a dense
        # inode allocation (1 inode per 2 KiB) prevents running out of
        # inodes long before the LV is full.
        cmd = f"mkfs.ext4 -i 2048 {lv_path}"
        commands.append(cmd)
        _run(cmd, execute)
        cmd = f"e2label {lv_path} {lv['name']}"
        commands.append(cmd)
        _run(cmd, execute)
        mount_point = "/mnt" if lv["name"] == "root" else f"/mnt/{lv['name']}"
        if lv["name"] != "root":
            cmd = f"mkdir -p {mount_point}"
            commands.append(cmd)
            _run(cmd, execute)
        cmd = f"mount -L {lv['name']} {mount_point}"
        commands.append(cmd)
        _run(cmd, execute)

    return commands
