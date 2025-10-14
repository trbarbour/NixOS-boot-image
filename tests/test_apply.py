"""Tests for apply module."""

import json
from pathlib import Path
from types import SimpleNamespace

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
        "disko --yes-wipe-all-disks --mode disko "
        f"--root-mountpoint /mnt {config_path}"
    )
    assert commands == [expected_cmd]
    devices = _read_devices(config_path)
    assert "disk" in devices and "mdadm" in devices and "lvm_vg" in devices


def test_apply_plan_handles_hdd_only_plan(tmp_path: Path) -> None:
    disks = [
        Disk(name="sda", size=2000, rotational=True),
        Disk(name="sdb", size=2000, rotational=True),
    ]
    plan = plan_storage("fast", disks)
    config_path = tmp_path / "hdd-only-disko.nix"
    plan["disko_config_path"] = str(config_path)
    commands = apply_plan(plan, dry_run=True)
    expected_cmd = (
        "disko --yes-wipe-all-disks --mode disko "
        f"--root-mountpoint /mnt {config_path}"
    )
    assert commands == [expected_cmd]
    devices = _read_devices(config_path)
    disks_cfg = devices["disk"]
    assert set(disks_cfg) == {"sda", "sdb"}
    for disk_name in ("sda", "sdb"):
        partitions = disks_cfg[disk_name]["content"]["partitions"]
        assert set(partitions) == {f"{disk_name}1", f"{disk_name}2"}
        assert partitions[f"{disk_name}2"]["content"]["name"] == "md0"
    boot_partition = disks_cfg["sda"]["content"]["partitions"]["sda1"]["content"]
    assert boot_partition["mountpoint"] == "/boot"
    assert boot_partition["format"] == "vfat"
    mirror_boot = disks_cfg["sdb"]["content"]["partitions"]["sdb1"]["content"]
    assert mirror_boot["format"] == "vfat"
    assert "md0" in devices["mdadm"], "root RAID array missing from HDD-only plan"
    md0 = devices["mdadm"]["md0"]
    assert md0["content"] == {"type": "lvm_pv", "vg": "main"}
    assert md0["devices"] == ["sda2", "sdb2"]
    assert set(devices["lvm_vg"]["main"]["lvs"]) == {"slash", "swap"}
    slash_lv = devices["lvm_vg"]["main"]["lvs"]["slash"]
    assert slash_lv["content"]["mountpoint"] == "/"


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
        "disko --yes-wipe-all-disks --mode disko "
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


def test_apply_plan_logs_command_execution(tmp_path: Path, monkeypatch, capsys) -> None:
    plan = {"disko": {"disk": {}}}
    config_path = tmp_path / "logged-disko.nix"
    plan["disko_config_path"] = str(config_path)

    monkeypatch.setenv("PRE_NIXOS_EXEC", "1")
    monkeypatch.setattr("pre_nixos.apply.shutil.which", lambda exe: f"/run/{exe}")

    calls: list[str] = []

    def fake_run(cmd, shell=False, check=False):  # type: ignore[override]
        calls.append(cmd)
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr("pre_nixos.apply.subprocess.run", fake_run)

    apply_plan(plan, dry_run=False)

    captured = capsys.readouterr()
    events = [json.loads(line) for line in captured.err.splitlines() if line.strip()]
    assert any(entry["event"] == "pre_nixos.apply.command.finished" for entry in events)
    assert any(entry["event"] == "pre_nixos.apply.apply_plan.finished" for entry in events)
    assert calls and isinstance(calls[0], str)

