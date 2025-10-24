"""Tests for apply module."""

from __future__ import annotations

import os
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Callable

import pytest

import pre_nixos.apply as apply_module
from pre_nixos.inventory import Disk
from pre_nixos.planner import plan_storage
from pre_nixos.apply import apply_plan


def _read_devices(config_path: Path) -> dict:
    text = config_path.read_text()
    start = text.index("''\n") + 3
    end = text.rindex("\n  ''")
    return json.loads(text[start:end])


@pytest.fixture
def fake_disko(
    monkeypatch: pytest.MonkeyPatch, tmp_path_factory: pytest.TempPathFactory
) -> Callable[[str], None]:
    """Provide a configurable ``disko`` shim for exercising mode detection."""

    bin_dir = tmp_path_factory.mktemp("fake-disko")
    script_path = bin_dir / "disko"

    def configure(help_text: str) -> None:
        script_body = "\n".join(
            [
                "#!/bin/sh",
                'if [ "$1" = "--help" ]; then',
                "    cat <<'EOF'",
                help_text.rstrip(),
                "EOF",
                "    exit 0",
                "fi",
                "exit 0",
            ]
        )
        script_path.write_text(script_body, encoding="utf-8")
        script_path.chmod(0o755)
        apply_module.reset_disko_mode_cache()

    monkeypatch.setenv("PATH", f"{bin_dir}:{os.environ.get('PATH', '')}")

    configure(
        """Usage: disko [options] disk-config.nix
--mode disko
"""
    )

    yield configure

    apply_module.reset_disko_mode_cache()


def test_apply_plan_returns_commands(tmp_path: Path, fake_disko) -> None:
    disks = [
        Disk(name="sda", size=1000, rotational=False),
        Disk(name="sdb", size=2000, rotational=True),
        Disk(name="sdc", size=2000, rotational=True),
    ]
    plan = plan_storage("fast", disks)
    config_path = tmp_path / "disko.nix"
    plan["disko_config_path"] = str(config_path)
    commands = apply_plan(plan, dry_run=True)
    expected_cmd = f"disko --mode disko --root-mountpoint /mnt {config_path}"
    assert commands == [expected_cmd]
    devices = _read_devices(config_path)
    assert "disk" in devices and "mdadm" in devices and "lvm_vg" in devices
    slash_lv = devices["lvm_vg"]["main"]["lvs"]["slash"]
    assert slash_lv["content"]["extraArgs"] == ["-L", "slash"]


def test_apply_plan_handles_hdd_only_plan(tmp_path: Path, fake_disko) -> None:
    disks = [
        Disk(name="sda", size=2000, rotational=True),
        Disk(name="sdb", size=2000, rotational=True),
    ]
    plan = plan_storage("fast", disks)
    config_path = tmp_path / "hdd-only-disko.nix"
    plan["disko_config_path"] = str(config_path)
    commands = apply_plan(plan, dry_run=True)
    expected_cmd = f"disko --mode disko --root-mountpoint /mnt {config_path}"
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
    assert slash_lv["content"]["extraArgs"] == ["-L", "slash"]
    swap_lv = devices["lvm_vg"]["main"]["lvs"]["swap"]
    assert swap_lv["content"]["extraArgs"] == ["--label", "swap"]


def test_apply_plan_preserves_filesystem_labels(tmp_path: Path, fake_disko) -> None:
    plan = plan_storage(
        "standard",
        [Disk(name="sda", size=128, rotational=False)],
        ram_gb=4,
    )
    config_path = tmp_path / "labeled-filesystems.nix"
    plan["disko_config_path"] = str(config_path)

    apply_plan(plan, dry_run=True)

    devices = _read_devices(config_path)
    boot_content = devices["disk"]["sda"]["content"]["partitions"]["sda1"]["content"]
    assert boot_content.get("extraArgs") == ["-n", "EFI"]


def test_apply_plan_handles_swap(tmp_path: Path, fake_disko) -> None:
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
    expected_cmd = f"disko --mode disko --root-mountpoint /mnt {config_path}"
    assert commands == [expected_cmd]
    devices = _read_devices(config_path)
    assert devices["lvm_vg"]["swap"]["lvs"]["swap"]["content"]["type"] == "swap"


def test_pv_created_for_each_array(tmp_path: Path, fake_disko) -> None:
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


def test_apply_plan_logs_command_execution(
    tmp_path: Path, fake_disko, monkeypatch, capsys
) -> None:
    plan = {"disko": {"disk": {}}}
    config_path = tmp_path / "logged-disko.nix"
    plan["disko_config_path"] = str(config_path)

    monkeypatch.setenv("PRE_NIXOS_EXEC", "1")

    calls: list[str] = []

    def fake_run(
        cmd,
        shell=False,
        check=False,
        capture_output=False,
        text=False,
        env=None,
    ):  # type: ignore[override]
        if isinstance(cmd, list) and "--help" in cmd:
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        calls.append(cmd)
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr("pre_nixos.apply.subprocess.run", fake_run)

    monkeypatch.setenv("PRE_NIXOS_NIXPKGS", "/nix/store/test-nixpkgs")
    apply_plan(plan, dry_run=False)

    captured = capsys.readouterr()
    events = [json.loads(line) for line in captured.err.splitlines() if line.strip()]
    assert any(entry["event"] == "pre_nixos.apply.command.finished" for entry in events)
    assert any(entry["event"] == "pre_nixos.apply.apply_plan.finished" for entry in events)
    assert calls and isinstance(calls[0], str)


def test_apply_plan_injects_nix_path_from_pre_nixos_env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    plan = {"disko": {"disk": {}}}
    config_path = tmp_path / "env-disko.nix"
    plan["disko_config_path"] = str(config_path)

    monkeypatch.setenv("PRE_NIXOS_EXEC", "1")
    monkeypatch.delenv("NIX_PATH", raising=False)
    monkeypatch.setenv("PRE_NIXOS_NIXPKGS", "/nix/store/fallback-nixpkgs")
    monkeypatch.setattr("pre_nixos.apply._select_disko_mode", lambda: ("disko", False))
    monkeypatch.setattr("pre_nixos.apply.shutil.which", lambda exe: "/nix/store/disko")

    captured_env: dict[str, str] = {}

    def fake_run(
        cmd,
        shell=False,
        check=False,
        capture_output=False,
        text=False,
        env=None,
    ):  # type: ignore[override]
        captured_env.update(env or {})
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr("pre_nixos.apply.subprocess.run", fake_run)

    apply_plan(plan, dry_run=False)

    assert captured_env.get("NIX_PATH") == "nixpkgs=/nix/store/fallback-nixpkgs"


def test_apply_plan_prefers_combined_mode_when_supported(tmp_path: Path, fake_disko) -> None:
    config_path = tmp_path / "combined-disko.nix"
    plan = plan_storage(
        "standard",
        [Disk(name="sda", size=128, rotational=False)],
        ram_gb=4,
    )
    plan["disko_config_path"] = str(config_path)

    fake_disko(
        """Usage: disko [options] disk-config.nix
--mode destroy,format,mount
--yes-wipe-all-disks
"""
    )

    commands = apply_plan(plan, dry_run=True)
    expected_cmd = (
        "disko --mode destroy,format,mount --yes-wipe-all-disks "
        f"--root-mountpoint /mnt {config_path}"
    )
    assert commands == [expected_cmd]

    devices = _read_devices(config_path)
    boot_content = devices["disk"]["sda"]["content"]["partitions"]["sda1"]["content"]
    assert boot_content.get("extraArgs") == ["-n", "EFI"]


def test_select_disko_mode_prefers_legacy_when_combined_missing(fake_disko) -> None:
    mode, supports_yes = apply_module._select_disko_mode()
    assert mode == "disko"
    assert not supports_yes


def test_select_disko_mode_detects_combined_support(fake_disko) -> None:
    fake_disko(
        """Usage: disko [options] disk-config.nix
--mode destroy,format,mount
--yes-wipe-all-disks
"""
    )
    mode, supports_yes = apply_module._select_disko_mode()
    assert mode == "destroy,format,mount"
    assert supports_yes


def test_apply_plan_logs_no_devices(monkeypatch: pytest.MonkeyPatch) -> None:
    events: list[tuple[str, dict[str, object]]] = []

    def record_event(event: str, **fields: object) -> None:
        events.append((event, fields))

    monkeypatch.setattr("pre_nixos.apply.log_event", record_event)
    monkeypatch.setattr("pre_nixos.apply._select_disko_mode", lambda: ("disko", False))

    commands = apply_plan({}, dry_run=True)

    assert commands == []
    event_names = [event for event, _ in events]
    assert event_names[0] == "pre_nixos.apply.apply_plan.start"
    assert "pre_nixos.apply.apply_plan.no_devices" in event_names


def test_apply_plan_logs_missing_disko(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    plan = {"disko": {"disk": {}}, "disko_config_path": str(tmp_path / "missing-disko.nix")}

    events: list[tuple[str, dict[str, object]]] = []

    def record_event(event: str, **fields: object) -> None:
        events.append((event, fields))

    monkeypatch.setattr("pre_nixos.apply.log_event", record_event)
    monkeypatch.setattr("pre_nixos.apply._select_disko_mode", lambda: ("disko", False))
    monkeypatch.setattr("pre_nixos.apply.shutil.which", lambda exe: None)
    monkeypatch.setenv("PRE_NIXOS_EXEC", "1")

    apply_plan(plan, dry_run=False)

    skip_events = [fields for event, fields in events if event == "pre_nixos.apply.command.skip"]
    assert any(fields.get("reason") == "executable not found" for fields in skip_events)
    assert any(event == "pre_nixos.apply.apply_plan.finished" for event, _ in events)


def test_apply_plan_logs_execution_disabled(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    plan = {"disko": {"disk": {}}, "disko_config_path": str(tmp_path / "disabled-disko.nix")}

    events: list[tuple[str, dict[str, object]]] = []

    def record_event(event: str, **fields: object) -> None:
        events.append((event, fields))

    monkeypatch.setattr("pre_nixos.apply.log_event", record_event)
    monkeypatch.setattr("pre_nixos.apply._select_disko_mode", lambda: ("disko", False))

    def fail_run(*_args, **_kwargs):
        raise AssertionError("execution should be disabled")

    monkeypatch.setattr("pre_nixos.apply.subprocess.run", fail_run)

    monkeypatch.setenv("PRE_NIXOS_EXEC", "0")

    apply_plan(plan, dry_run=False)

    skip_events = [
        fields
        for event, fields in events
        if event == "pre_nixos.apply.command.skip"
    ]
    assert any(fields.get("reason") == "execution disabled" for fields in skip_events)
    assert any(event == "pre_nixos.apply.apply_plan.finished" for event, _ in events)


def test_prepare_command_environment_logs_nix_path_injection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[tuple[str, dict[str, object]]] = []

    def record_event(event: str, **fields: object) -> None:
        events.append((event, fields))

    monkeypatch.setattr("pre_nixos.apply.log_event", record_event)
    monkeypatch.delenv("NIX_PATH", raising=False)
    monkeypatch.setenv("PRE_NIXOS_NIXPKGS", "/nix/store/test-nixpkgs")

    env = apply_module._prepare_command_environment()

    assert env["NIX_PATH"] == "nixpkgs=/nix/store/test-nixpkgs"
    assert events and events[-1][0] == "pre_nixos.apply.command.nix_path_injected"


def test_prepare_command_environment_logs_missing_nix_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[tuple[str, dict[str, object]]] = []

    def record_event(event: str, **fields: object) -> None:
        events.append((event, fields))

    monkeypatch.setattr("pre_nixos.apply.log_event", record_event)
    monkeypatch.delenv("NIX_PATH", raising=False)
    monkeypatch.delenv("PRE_NIXOS_NIXPKGS", raising=False)

    env = apply_module._prepare_command_environment()

    assert "NIX_PATH" not in env or not env["NIX_PATH"].strip()
    assert events and events[-1][0] == "pre_nixos.apply.command.nix_path_missing"

