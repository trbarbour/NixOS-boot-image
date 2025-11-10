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


def _make_lan(tmp_path: Path) -> LanConfiguration:
    key_path = tmp_path / "key.pub"
    key_path.write_text("ssh-ed25519 AAAAB3NzaC1yc2EAAAADAQABAAACAQC7 test@local")
    rename_rule = tmp_path / "10-lan.link"
    rename_rule.write_text("[Match]\nOriginalName=eth0\n[Link]\nName=lan\n")
    network_unit = tmp_path / "20-lan.network"
    network_unit.write_text("[Match]\nName=lan\n[Network]\nDHCP=yes\n")
    return LanConfiguration(
        authorized_key=key_path,
        interface="lan",
        rename_rule=rename_rule,
        network_unit=network_unit,
    )


def test_auto_install_skips_when_disabled(tmp_path, monkeypatch, broadcast_messages):
    lan = _make_lan(tmp_path)
    monkeypatch.setenv("PRE_NIXOS_EXEC", "1")
    result = install.auto_install(
        lan,
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
        return Result()

    monkeypatch.setattr(install.subprocess, "run", fake_run)
    monkeypatch.setenv("PRE_NIXOS_EXEC", "1")
    monkeypatch.setattr(install, "datetime", FakeDateTime)

    reboot_called: list[bool] = []

    def fake_reboot() -> bool:
        reboot_called.append(True)
        return True

    monkeypatch.setattr(install, "_request_reboot", fake_reboot)

    result = install.auto_install(lan, root_path=root, status_dir=tmp_path / "status")
    assert result.status == "success"
    assert commands == [
        ["nixos-generate-config", "--root", str(root)],
        ["nixos-install", "--root", str(root), "--no-root-passwd"],
    ]
    assert reboot_called == [True]

    config_path = root / "etc/nixos/configuration.nix"
    content = config_path.read_text()
    assert "networking.firewall" in content
    assert 'PermitRootLogin = "prohibit-password"' in content
    assert "experimental-features = [ \"nix-command\" \"flakes\" ]" in content
    authorized_line = '"ssh-ed25519 AAAAB3NzaC1yc2EAAAADAQABAAACAQC7 test@local"'
    assert authorized_line in content

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

    result = install.auto_install(lan, root_path=root, status_dir=tmp_path / "status")
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
