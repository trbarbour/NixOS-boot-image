import os
import shutil
import subprocess
from pathlib import Path
from typing import Iterable, Sequence

import pytest

from pre_nixos import storage_cleanup


def _require_commands(commands: Iterable[str]) -> None:
    missing = [cmd for cmd in commands if shutil.which(cmd) is None]
    if missing:
        pytest.skip(f"Required commands unavailable: {', '.join(missing)}")


def _run_command(cmd: Sequence[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        check=True,
        capture_output=True,
        text=True,
        **kwargs,
    )


def _wait_for_udev() -> None:
    subprocess.run(["udevadm", "settle"], check=False)


def _has_stack_metadata(md_identifier: str, vg_name: str) -> bool:
    lsblk_output = subprocess.run(
        ["lsblk", "-J"], capture_output=True, text=True, check=False
    ).stdout
    if md_identifier in lsblk_output or vg_name in lsblk_output:
        return True

    mdadm_output = subprocess.run(
        ["mdadm", "--detail", "--scan"], capture_output=True, text=True, check=False
    ).stdout
    if md_identifier in mdadm_output:
        return True

    for cmd in (
        ["pvs", "--noheadings", "-o", "pv_name,vg_name"],
        ["vgs", "--noheadings", "-o", "vg_name"],
        ["lvs", "--noheadings", "-o", "vg_name,lv_name"],
    ):
        output = subprocess.run(cmd, capture_output=True, text=True, check=False).stdout
        if md_identifier in output or vg_name in output:
            return True

    return False


def _assert_stack_absent(md_identifier: str, vg_name: str) -> None:
    assert not _has_stack_metadata(md_identifier, vg_name)


def _create_md_lvm_stack(loops: Sequence[str], md_path: str, vg_name: str, lv_name: str) -> None:
    for loop in loops:
        _run_command(["sgdisk", "--zap-all", loop])
        partition_table = "label: gpt\n,32M,fd00\n"
        _run_command(["sfdisk", loop], input=partition_table)
    for loop in loops:
        _run_command(["partprobe", loop])
    _wait_for_udev()

    partitions = [f"{loop}p1" for loop in loops]
    Path(md_path).parent.mkdir(parents=True, exist_ok=True)
    _run_command(
        [
            "mdadm",
            "--create",
            md_path,
            "--metadata=1.2",
            "--level=1",
            "--raid-devices=2",
            "--force",
            partitions[0],
            partitions[1],
        ]
    )
    _wait_for_udev()
    _run_command(["pvcreate", "-ff", "-y", md_path])
    _run_command(["vgcreate", vg_name, md_path])
    _run_command(["lvcreate", "-n", lv_name, "-L", "8M", vg_name])
    _wait_for_udev()


def _teardown_stack(loops: Sequence[str], md_path: str, vg_name: str, lv_name: str) -> None:
    subprocess.run(["lvremove", "-ff", "-y", f"{vg_name}/{lv_name}"], check=False)
    subprocess.run(["lvchange", "-an", f"{vg_name}/{lv_name}"], check=False)
    subprocess.run(["vgchange", "-an", vg_name], check=False)
    subprocess.run(["vgremove", "-ff", "-y", vg_name], check=False)
    subprocess.run(["pvremove", "-ff", "-y", md_path], check=False)
    subprocess.run(["mdadm", "--stop", "--force", md_path], check=False)
    subprocess.run(["mdadm", "--zero-superblock", "--force", md_path], check=False)
    for loop in loops:
        for suffix in ("", "p1"):
            subprocess.run(
                ["mdadm", "--zero-superblock", "--force", f"{loop}{suffix}"],
                check=False,
            )
        subprocess.run(["losetup", "-d", loop], check=False)
    _wait_for_udev()


def test_storage_cleanup_two_pass(tmp_path: Path) -> None:
    _require_commands(
        [
            "losetup",
            "mdadm",
            "pvcreate",
            "vgcreate",
            "lvcreate",
            "pvs",
            "vgs",
            "lvs",
            "lsblk",
            "sgdisk",
            "sfdisk",
            "partprobe",
            "udevadm",
            "dmsetup",
            "truncate",
        ]
    )

    if os.geteuid() != 0:
        pytest.skip("Root privileges are required for loop device setup")

    md_name = "cleanup_test_md"
    md_path = f"/dev/md/{md_name}"
    vg_name = "cleanup_test_vg"
    lv_name = "cleanup_test_lv"

    backing_files = [tmp_path / "loop1.img", tmp_path / "loop2.img"]
    for file in backing_files:
        _run_command(["truncate", "-s", "64M", str(file)])

    loops: list[str] = []
    for file in backing_files:
        loop_device = _run_command(["losetup", "--find", "--show", str(file)]).stdout.strip()
        loops.append(loop_device)

    try:
        _create_md_lvm_stack(loops, md_path, vg_name, lv_name)
        assert _has_stack_metadata(md_name, vg_name)

        storage_cleanup.perform_storage_cleanup(
            storage_cleanup.WIPE_SIGNATURES,
            loops,
            execute=True,
        )
        _assert_stack_absent(md_name, vg_name)

        _create_md_lvm_stack(loops, md_path, vg_name, lv_name)
        assert _has_stack_metadata(md_name, vg_name)

        storage_cleanup.perform_storage_cleanup(
            storage_cleanup.WIPE_SIGNATURES,
            loops,
            execute=True,
        )
        _assert_stack_absent(md_name, vg_name)
    finally:
        _teardown_stack(loops, md_path, vg_name, lv_name)
        for file in backing_files:
            try:
                file.unlink()
            except FileNotFoundError:
                pass
