"""Tests for the automated installation helper."""

from datetime import datetime, timezone
from pathlib import Path

import pytest

from pre_nixos import install
from pre_nixos.network import LanConfiguration


@pytest.fixture
def broadcast_messages(monkeypatch) -> list[str]:
    messages: list[str] = []

    def fake_broadcast(message: str, **_: object):
        messages.append(message)
        path = Path("/dev/console")
        return True, [path], {path: True}

    monkeypatch.setattr(install, "broadcast_to_consoles", fake_broadcast)
    return messages


def _sample_storage_plan() -> dict:
    return {
        "disko": {
            "disk": {
                "sda": {
                    "type": "disk",
                    "device": "/dev/sda",
                    "content": {
                        "type": "gpt",
                        "partitions": {
                            "sda1": {
                                "size": "1G",
                                "type": "EF00",
                                "content": {
                                    "type": "filesystem",
                                    "format": "vfat",
                                    "mountpointPermissions": 0,
                                    "mountpoint": "/boot",
                                    "mountOptions": ["umask=0077"],
                                    "extraArgs": ["-n", "EFI"],
                                },
                            },
                            "sda2": {
                                "size": "100%",
                                "content": {
                                    "type": "lvm_pv",
                                    "vg": "main",
                                },
                            },
                        },
                    },
                }
            },
            "lvm_vg": {
                "main": {
                    "type": "lvm_vg",
                    "lvs": {
                        "slash": {
                            "size": "50G",
                            "content": {
                                "type": "filesystem",
                                "format": "ext4",
                                "mountpointPermissions": 0,
                                "mountpoint": "/",
                                "mountOptions": ["relatime"],
                                "extraArgs": ["-L", "slash"],
                            },
                        },
                        "home": {
                            "size": "25G",
                            "content": {
                                "type": "filesystem",
                                "format": "ext4",
                                "mountpointPermissions": 0,
                                "mountpoint": "/home",
                                "mountOptions": ["relatime"],
                                "extraArgs": ["-L", "home"],
                            },
                        },
                        "swap": {
                            "size": "16G",
                            "content": {
                                "type": "swap",
                                "extraArgs": ["--label", "swap"],
                            },
                        },
                    },
                }
            },
        }
    }


def _make_lan(tmp_path: Path) -> LanConfiguration:
    key_path = tmp_path / "key.pub"
    key_path.write_text("ssh-ed25519 AAAAB3NzaC1yc2EAAAADAQABAAACAQC7 test@local")
    rename_rule = tmp_path / "10-lan.link"
    rename_rule.write_text(
        "[Match]\n"
        "OriginalName=eth0\n"
        "MACAddress=00:11:22:33:44:55\n\n"
        "[Link]\n"
        "Name=lan\n"
    )
    network_unit = tmp_path / "20-lan.network"
    network_unit.write_text("[Match]\nName=lan\n[Network]\nDHCP=yes\n")
    return LanConfiguration(
        authorized_key=key_path,
        interface="lan",
        rename_rule=rename_rule,
        network_unit=network_unit,
        mac_address="00:11:22:33:44:55",
    )


def test_auto_install_skips_when_disabled(tmp_path, monkeypatch, broadcast_messages):
    lan = _make_lan(tmp_path)
    monkeypatch.setenv("PRE_NIXOS_EXEC", "1")
    result = install.auto_install(
        lan,
        _sample_storage_plan(),
        enabled=False,
        root_path=tmp_path / "mnt",
        status_dir=tmp_path / "status",
    )
    assert result.status == "skipped"
    assert result.reason == "disabled"
    status_file = (tmp_path / "status" / "auto-install-status")
    assert status_file.read_text() == "STATE=skipped\nREASON=disabled\n"
    assert broadcast_messages == []


def test_auto_install_success_writes_configuration(tmp_path, monkeypatch, broadcast_messages):
    root = tmp_path / "mnt"
    (root / "etc").mkdir(parents=True)
    lan = _make_lan(tmp_path)

    commands: list[list[str]] = []

    start_time = datetime(2025, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
    completion_time = datetime(2025, 1, 2, 3, 14, 5, tzinfo=timezone.utc)

    class FakeDateTime:
        calls = 0

        @classmethod
        def now(cls, tz=None):
            cls.calls += 1
            return start_time if cls.calls == 1 else completion_time

    def fake_run(cmd, check=False):
        commands.append(cmd)

        class Result:
            returncode = 0

        if cmd[0] == "nixos-generate-config":
            config_dir = root / "etc/nixos"
            config_dir.mkdir(parents=True, exist_ok=True)
            (config_dir / "configuration.nix").write_text("{\n}\n", encoding="utf-8")
            (config_dir / "hardware-configuration.nix").write_text(
                "{\n"
                "  fileSystems.\"/\" = { device = \"/dev/disk/by-uuid/OLD\"; };\n"
                "  swapDevices = [ { device = \"/dev/disk/by-uuid/OLD-SWAP\"; } ];\n"
                "  networking.useDHCP = lib.mkDefault true;\n"
                "}\n",
                encoding="utf-8",
            )
        return Result()

    monkeypatch.setattr(install.subprocess, "run", fake_run)
    monkeypatch.setenv("PRE_NIXOS_EXEC", "1")
    monkeypatch.setattr(install, "datetime", FakeDateTime)

    reboot_called: list[bool] = []

    def fake_reboot() -> bool:
        reboot_called.append(True)
        return True

    monkeypatch.setattr(install, "_request_reboot", fake_reboot)

    result = install.auto_install(
        lan,
        _sample_storage_plan(),
        root_path=root,
        status_dir=tmp_path / "status",
    )
    assert result.status == "success"
    assert commands == [
        ["nixos-generate-config", "--root", str(root)],
        ["nixos-install", "--root", str(root), "--no-root-passwd"],
    ]
    assert reboot_called == [True]

    config_path = root / "etc/nixos/configuration.nix"
    content = config_path.read_text()
    assert "networking.firewall" in content
    assert "networking.useDHCP = false;" in content
    assert "networking.useNetworkd = true;" in content
    assert "networking.interfaces.lan = {" in content
    assert "useDHCP = true;" in content
    assert 'matchConfig.MACAddress = "00:11:22:33:44:55";' in content
    assert 'systemd.network.links."lan"' in content
    assert 'systemd.services."pre-nixos-auto-install-ip"' in content
    assert 'description = "Announce LAN IPv4 on boot";' in content
    assert 'boot.kernelParams = [ "console=tty0" "console=ttyS0,115200n8" ];' in content
    assert "boot.loader.grub.extraConfig = ''" in content
    assert "serial --speed=115200 --unit=0 --word=8 --parity=no --stop=1" in content
    assert "experimental-features = [ \"nix-command\" \"flakes\" ]" in content
    authorized_line = '"ssh-ed25519 AAAAB3NzaC1yc2EAAAADAQABAAACAQC7 test@local"'
    assert authorized_line in content
    assert 'fileSystems = {' in content
    assert '"/" = {' in content
    assert 'label = "slash";' in content
    assert 'neededForBoot = true;' in content
    assert '"/boot" = {' in content
    assert 'label = "EFI";' in content
    assert '"/home" = {' in content
    assert 'label = "home";' in content
    assert 'systemd.tmpfiles.rules = [' in content
    assert '  "d /boot 000 root root -";' in content
    assert '  "d /home 000 root root -";' in content
    assert 'swapDevices = [' in content
    assert 'label = "swap";' in content
    assert 'boot.swraid.enable = true;' in content
    assert 'boot.initrd.services.lvm.enable = true;' in content

    hardware_text = (root / "etc/nixos/hardware-configuration.nix").read_text()
    assert 'fileSystems."/' not in hardware_text
    assert "swapDevices" not in hardware_text
    assert "networking.useDHCP" not in hardware_text

    network_dir = root / "etc/systemd/network"
    assert (network_dir / "10-lan.link").read_text() == lan.rename_rule.read_text()
    assert (network_dir / "20-lan.network").read_text() == lan.network_unit.read_text()

    start_stamp = start_time.strftime("%Y-%m-%d %H:%M:%SZ")
    completion_stamp = completion_time.strftime("%Y-%m-%d %H:%M:%SZ")
    assert broadcast_messages == [
        f"Starting automatic NixOS installation at {start_stamp} UTC.",
        f"Automatic NixOS installation completed at {completion_stamp} UTC.",
    ]

    issue_text = (root / "etc/issue").read_text()
    assert "Automatic NixOS installation completed by pre-nixos." in issue_text
    assert f"Installation timestamp (UTC): {completion_stamp}" in issue_text

    status_file = (tmp_path / "status" / "auto-install-status")
    status_text = status_file.read_text()
    assert "STATE=success" in status_text
    assert f"COMPLETED_AT={completion_stamp}" in status_text
    assert "REBOOT=requested" in status_text
    assert "CONSOLE_WRITTEN=true" in status_text
    assert f"ISSUE_PATH={root}/etc/issue" in status_text


def test_auto_install_missing_plan_fails(tmp_path, monkeypatch, broadcast_messages):
    root = tmp_path / "mnt"
    (root / "etc").mkdir(parents=True)
    lan = _make_lan(tmp_path)

    monkeypatch.setenv("PRE_NIXOS_EXEC", "1")

    result = install.auto_install(
        lan,
        None,
        root_path=root,
        status_dir=tmp_path / "status",
    )

    assert result.status == "failed"
    assert result.reason == "missing-storage-plan"
    status_text = (tmp_path / "status" / "auto-install-status").read_text()
    assert "STATE=failed" in status_text
    assert "REASON=missing-storage-plan" in status_text
    assert broadcast_messages == []


def test_auto_install_failure_returns_failed(tmp_path, monkeypatch, broadcast_messages):
    root = tmp_path / "mnt"
    (root / "etc").mkdir(parents=True)
    lan = _make_lan(tmp_path)

    start_time = datetime(2025, 2, 3, 4, 5, 6, tzinfo=timezone.utc)

    class FakeDateTime:
        @classmethod
        def now(cls, tz=None):
            return start_time

    def fake_run(cmd, check=False):
        class Result:
            returncode = 0 if cmd[0] == "nixos-generate-config" else 1

        if cmd[0] == "nixos-generate-config":
            config_dir = root / "etc/nixos"
            config_dir.mkdir(parents=True, exist_ok=True)
            (config_dir / "configuration.nix").write_text("{\n}\n", encoding="utf-8")
        return Result()

    monkeypatch.setattr(install.subprocess, "run", fake_run)
    monkeypatch.setenv("PRE_NIXOS_EXEC", "1")
    monkeypatch.setattr(install, "datetime", FakeDateTime)

    result = install.auto_install(
        lan,
        _sample_storage_plan(),
        root_path=root,
        status_dir=tmp_path / "status",
    )
    assert result.status == "failed"
    assert result.reason == "nixos-install"
    status_text = (tmp_path / "status" / "auto-install-status").read_text()
    assert "STATE=failed" in status_text
    assert "REASON=nixos-install" in status_text
    start_stamp = start_time.strftime("%Y-%m-%d %H:%M:%SZ")
    assert broadcast_messages == [
        f"Starting automatic NixOS installation at {start_stamp} UTC.",
    ]


def test_auto_install_dry_run_skips(monkeypatch, tmp_path, broadcast_messages):
    lan = _make_lan(tmp_path)
    monkeypatch.setenv("PRE_NIXOS_EXEC", "1")

    called = []

    def fail_run(*args, **kwargs):
        called.append(True)
        raise AssertionError("subprocess.run should not be called in dry-run mode")

    monkeypatch.setattr(install.subprocess, "run", fail_run)
    result = install.auto_install(
        lan,
        _sample_storage_plan(),
        dry_run=True,
        root_path=tmp_path / "mnt",
        status_dir=tmp_path / "status",
    )
    assert result.status == "skipped"
    assert result.reason == "dry-run"
    assert called == []
    status_text = (tmp_path / "status" / "auto-install-status").read_text()
    assert status_text.startswith("STATE=skipped\nREASON=dry-run")
    assert broadcast_messages == []
