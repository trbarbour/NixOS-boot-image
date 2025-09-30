"""Tests for apply module."""

import json
from pathlib import Path

from pre_nixos.inventory import Disk
from pre_nixos.planner import plan_storage
from pre_nixos.apply import apply_plan


def _read_devices(config_path: Path) -> dict:
    text = config_path.read_text()
    start = text.index("''\n") + 3
    end = text.rindex("\n  ''")
    return json.loads(text[start:end])


def test_apply_plan_returns_commands(tmp_path: Path) -> None:
    disks = [
        Disk(name="sda", size=1000, rotational=False),
        Disk(name="sdb", size=2000, rotational=True),
        Disk(name="sdc", size=2000, rotational=True),
    ]
    plan = plan_storage("fast", disks)
    config_path = tmp_path / "disko.nix"
    plan["disko_config_path"] = str(config_path)
    commands = apply_plan(plan, dry_run=True)
    expected_cmd = (
        "disko --yes-wipe-all-disks --mode destroy,format,mount "
        f"--root-mountpoint /mnt {config_path}"
    )
    assert commands == [expected_cmd]
    devices = _read_devices(config_path)
    assert "disk" in devices and "mdadm" in devices and "lvm_vg" in devices


def test_apply_plan_handles_swap(tmp_path: Path) -> None:
    config_path = tmp_path / "swap-disko.nix"
    plan = {
        "disko": {
            "disk": {},
            "mdadm": {},
            "lvm_vg": {
                "swap": {
                    "type": "lvm_vg",
                    "lvs": {
                        "swap": {
                            "size": "8G",
                            "content": {"type": "swap"},
                        }
                    },
                }
            },
        },
        "disko_config_path": str(config_path),
    }
    commands = apply_plan(plan, dry_run=True)
    expected_cmd = (
        "disko --yes-wipe-all-disks --mode destroy,format,mount "
        f"--root-mountpoint /mnt {config_path}"
    )
    assert commands == [expected_cmd]
    devices = _read_devices(config_path)
    assert devices["lvm_vg"]["swap"]["lvs"]["swap"]["content"]["type"] == "swap"


def test_pv_created_for_each_array(tmp_path: Path) -> None:
    disks = [
        Disk(name="sda", size=1000, rotational=False),
        Disk(name="sdb", size=1000, rotational=False),
        Disk(name="sdc", size=2000, rotational=True),
        Disk(name="sdd", size=2000, rotational=True),
        Disk(name="sde", size=2000, rotational=True),
        Disk(name="sdf", size=4000, rotational=True),
        Disk(name="sdg", size=4000, rotational=True),
        Disk(name="sdh", size=6000, rotational=True),
        Disk(name="sdi", size=6000, rotational=True),
        Disk(name="sdj", size=6000, rotational=True),
        Disk(name="sdk", size=6000, rotational=True),
    ]
    plan = plan_storage("fast", disks)
    config_path = tmp_path / "arrays-disko.nix"
    plan["disko_config_path"] = str(config_path)
    apply_plan(plan)
    devices = _read_devices(config_path)
    mdadm_devices = devices["mdadm"].keys()
    expected = {arr["name"] for arr in plan["arrays"]}
    assert expected <= set(mdadm_devices)

