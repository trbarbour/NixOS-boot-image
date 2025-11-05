"""Tests for filesystem-related entries in the disko config."""

import json
from pathlib import Path

from pre_nixos.inventory import Disk
from pre_nixos.planner import plan_storage, _plan_to_disko_devices
from pre_nixos.apply import apply_plan


def _read_devices(config_path: Path) -> dict:
    text = config_path.read_text()
    start = text.index("''\n") + 3
    end = text.rindex("\n  ''")
    return json.loads(text[start:end])


def test_filesystem_entries_for_lvs(tmp_path: Path) -> None:
    disks = [
        Disk(name="sda", size=1000, rotational=False),
        Disk(name="sdb", size=2000, rotational=True),
        Disk(name="sdc", size=2000, rotational=True),
        Disk(name="sdd", size=1000, rotational=True),
    ]
    plan = plan_storage("fast", disks)
    config_path = tmp_path / "fs.nix"
    plan["disko_config_path"] = str(config_path)
    apply_plan(plan, dry_run=True)

    devices = _read_devices(config_path)
    slash = devices["lvm_vg"]["main"]["lvs"]["slash"]
    assert slash["content"]["format"] == "ext4"
    assert slash["content"]["mountpoint"] == "/"
    assert "relatime" in slash["content"]["mountOptions"]
    assert slash["content"]["extraArgs"] == ["-L", "slash"]

    data = devices["lvm_vg"]["large"]["lvs"]["data"]
    assert data["content"]["format"] == "ext4"
    assert data["content"]["mountpoint"] == "/data"
    assert "relatime" in data["content"]["mountOptions"]
    assert data["content"]["extraArgs"] == ["-L", "data"]

    var_tmp = devices["lvm_vg"]["swap"]["lvs"]["var_tmp"]
    assert var_tmp["content"]["mountpoint"] == "/var/tmp"
    assert "relatime" in var_tmp["content"]["mountOptions"]

    var_log = devices["lvm_vg"]["swap"]["lvs"]["var_log"]
    assert var_log["content"]["mountpoint"] == "/var/log"
    assert "relatime" in var_log["content"]["mountOptions"]

    swap_args = None
    for vg in devices["lvm_vg"].values():
        swap_spec = vg.get("lvs", {}).get("swap")
        if swap_spec:
            swap_args = swap_spec["content"].get("extraArgs")
            break
    assert swap_args == ["--label", "swap"]

    efi = devices["disk"]["sda"]["content"]["partitions"]["sda1"]["content"]
    assert efi["format"] == "vfat"
    assert efi["mountpoint"] == "/boot"


def test_non_root_lvs_have_mountpoints(tmp_path: Path) -> None:
    disks = [
        Disk(name="sda", size=1000, rotational=False),
        Disk(name="sdb", size=2000, rotational=True),
        Disk(name="sdc", size=2000, rotational=True),
        Disk(name="sdd", size=1000, rotational=True),
    ]
    plan = plan_storage("fast", disks)
    config_path = tmp_path / "mounts.nix"
    plan["disko_config_path"] = str(config_path)
    apply_plan(plan, dry_run=True)

    devices = _read_devices(config_path)
    lvs = devices["lvm_vg"].get("large", {}).get("lvs", {})
    for name, spec in lvs.items():
        assert spec["content"].get("mountpoint") == f"/{name}"


def test_lv_labels_replace_disallowed_characters() -> None:
    plan = {
        "arrays": [],
        "vgs": [{"name": "main", "devices": []}],
        "lvs": [
            {
                "name": "large-1",
                "vg": "main",
                "size": "10G",
            }
        ],
        "partitions": {},
    }

    devices = _plan_to_disko_devices(plan)

    args = devices["lvm_vg"]["main"]["lvs"]["large-1"]["content"].get("extraArgs")
    assert args == ["-L", "large_1"]
