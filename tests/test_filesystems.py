"""Tests for filesystem-related entries in the disko config."""

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
    assert "noatime" in slash["content"]["mountOptions"]

    data = devices["lvm_vg"]["large"]["lvs"]["data"]
    assert data["content"]["format"] == "ext4"
    assert data["content"]["mountpoint"] == "/data"
    assert "noatime" in data["content"]["mountOptions"]

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
