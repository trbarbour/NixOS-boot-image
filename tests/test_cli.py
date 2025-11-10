"""Tests for CLI entry point."""

import pytest

from pre_nixos import pre_nixos
from pre_nixos.install import AutoInstallResult
from pre_nixos.inventory import Disk


def test_cli_plan_only(monkeypatch, capsys, tmp_path):
    monkeypatch.setattr(
        pre_nixos.inventory,
        "enumerate_disks",
        lambda: [Disk(name="sda", size=1000, rotational=False)],
    )
    called = []
    net_called = []

    sample_lan = pre_nixos.network.LanConfiguration(
        authorized_key=tmp_path / "key.pub",
        interface="lan",
        rename_rule=None,
        network_unit=None,
    )

    def fake_apply(plan, dry_run=False):
        called.append(dry_run)

    monkeypatch.setattr(pre_nixos.apply, "apply_plan", fake_apply)
    monkeypatch.setattr(
        pre_nixos.network,
        "configure_lan",
        lambda: net_called.append(True) or sample_lan,
    )
    monkeypatch.setattr(
        pre_nixos.install,
        "auto_install",
        lambda *args, **kwargs: AutoInstallResult(status="skipped"),
    )
    pre_nixos.main(["--plan-only"])
    out = capsys.readouterr().out
    assert "main" in out
    assert '"disko"' not in out
    assert called == []
    assert net_called == [True]


def test_cli_install_now(monkeypatch, capsys, tmp_path):
    sample_lan = pre_nixos.network.LanConfiguration(
        authorized_key=tmp_path / "key.pub",
        interface="lan",
        rename_rule=None,
        network_unit=None,
    )

    monkeypatch.setattr(pre_nixos.network, "configure_lan", lambda: sample_lan)

    calls: list[tuple] = []

    def fake_auto_install(lan_config, plan, *, enabled, dry_run):
        calls.append((lan_config, plan, enabled, dry_run))
        return AutoInstallResult(status="success")

    monkeypatch.setattr(pre_nixos.install, "auto_install", fake_auto_install)

    pre_nixos.main(["--install-now"])

    assert calls == [(sample_lan, None, True, False)]
    out = capsys.readouterr().out
    assert "Install completed successfully." in out


def test_cli_plan_only_disko_output(monkeypatch, capsys, tmp_path):
    monkeypatch.setattr(
        pre_nixos.inventory,
        "enumerate_disks",
        lambda: [Disk(name="sda", size=1000, rotational=False)],
    )
    net_called = []

    sample_lan = pre_nixos.network.LanConfiguration(
        authorized_key=tmp_path / "key.pub",
        interface="lan",
        rename_rule=None,
        network_unit=None,
    )

    def noop_apply(plan, dry_run=False):
        return None

    monkeypatch.setattr(pre_nixos.apply, "apply_plan", noop_apply)
    monkeypatch.setattr(
        pre_nixos.network,
        "configure_lan",
        lambda: net_called.append(True) or sample_lan,
    )
    monkeypatch.setattr(
        pre_nixos.install,
        "auto_install",
        lambda *args, **kwargs: AutoInstallResult(status="skipped"),
    )

    pre_nixos.main(["--plan-only", "--output", "disko"])

    out = capsys.readouterr().out
    assert "disko.devices" in out
    assert net_called == [True]


def test_cli_apply_called(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(
        pre_nixos.inventory,
        "enumerate_disks",
        lambda: [Disk(name="sda", size=1000, rotational=False)],
    )
    called = []
    net_called = []
    install_calls = []

    sample_lan = pre_nixos.network.LanConfiguration(
        authorized_key=tmp_path / "key.pub",
        interface="lan",
        rename_rule=None,
        network_unit=None,
    )

    def fake_apply(plan, dry_run=False):
        called.append(dry_run)

    monkeypatch.setattr(pre_nixos.apply, "apply_plan", fake_apply)
    monkeypatch.setattr(
        pre_nixos.network,
        "configure_lan",
        lambda: net_called.append(True) or sample_lan,
    )

    def fake_auto_install(lan_config, plan, *, enabled, dry_run):
        install_calls.append((lan_config, plan, enabled, dry_run))
        return AutoInstallResult(status="skipped", reason="execution-disabled")

    monkeypatch.setattr(pre_nixos.install, "auto_install", fake_auto_install)
    pre_nixos.main([])
    assert called == [False]
    assert net_called == [True]
    assert len(install_calls) == 1
    recorded_lan, recorded_plan, recorded_enabled, recorded_dry_run = install_calls[0]
    assert recorded_lan == sample_lan
    assert isinstance(recorded_plan, dict)
    assert recorded_enabled is True
    assert recorded_dry_run is False
    out = capsys.readouterr()
    assert "Auto-install skipped: execution-disabled." in out.out


def test_cli_interactive_confirms_before_apply(monkeypatch):
    monkeypatch.setattr(
        pre_nixos.inventory,
        "enumerate_disks",
        lambda: [Disk(name="sda", size=1000, rotational=False)],
    )
    monkeypatch.setattr(pre_nixos.network, "configure_lan", lambda: None)
    monkeypatch.setattr(pre_nixos, "_is_interactive", lambda: True)

    confirmations: list[bool] = []

    def fake_confirm() -> bool:
        confirmations.append(True)
        return True

    monkeypatch.setattr(pre_nixos, "_confirm_storage_reset", fake_confirm)
    monkeypatch.setenv("PRE_NIXOS_EXEC", "1")

    called = []

    def fake_apply(plan, dry_run=False):
        called.append(dry_run)

    monkeypatch.setattr(pre_nixos.apply, "apply_plan", fake_apply)

    pre_nixos.main([])

    assert called == [False]
    assert confirmations == [True]


def test_cli_abort_when_confirmation_declined(monkeypatch, capsys):
    monkeypatch.setattr(
        pre_nixos.inventory,
        "enumerate_disks",
        lambda: [Disk(name="sda", size=1000, rotational=False)],
    )
    monkeypatch.setattr(pre_nixos.network, "configure_lan", lambda: None)
    monkeypatch.setattr(pre_nixos, "_is_interactive", lambda: True)
    monkeypatch.setenv("PRE_NIXOS_EXEC", "1")

    def fake_confirm() -> bool:
        return False

    monkeypatch.setattr(pre_nixos, "_confirm_storage_reset", fake_confirm)

    called = []

    def fake_apply(plan, dry_run=False):
        called.append(dry_run)

    monkeypatch.setattr(pre_nixos.apply, "apply_plan", fake_apply)

    pre_nixos.main([])

    assert called == []
    out = capsys.readouterr().out
    assert "Aborting without modifying storage." in out


def test_cli_writes_console(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(
        pre_nixos.inventory,
        "enumerate_disks",
        lambda: [Disk(name="sda", size=1000, rotational=False)],
    )
    sample_lan = pre_nixos.network.LanConfiguration(
        authorized_key=tmp_path / "key.pub",
        interface="lan",
        rename_rule=None,
        network_unit=None,
    )
    import io

    class FakeConsole(io.StringIO):
        def close(self) -> None:  # type: ignore[override]
            # Keep the buffer accessible after ``pre_nixos.main`` closes the
            # console handle.
            self.flush()

    fake_console = FakeConsole()

    def open_console():
        return fake_console

    monkeypatch.setattr(pre_nixos, "_maybe_open_console", open_console)
    monkeypatch.setattr(pre_nixos.network, "configure_lan", lambda: sample_lan)
    monkeypatch.setattr(
        pre_nixos.install,
        "auto_install",
        lambda *args, **kwargs: AutoInstallResult(status="skipped"),
    )
    pre_nixos.main(["--plan-only"])
    out = capsys.readouterr().out
    assert "main" in out
    console_output = fake_console.getvalue()
    assert console_output.endswith("\r\n")
    # There should be no bare line feeds, ensuring console output renders
    # correctly on terminals that require carriage returns.
    assert "\n" not in console_output.replace("\r\n", "")
    assert "main" in console_output
    assert '"disko"' not in console_output


def test_cli_no_auto_install_flag(monkeypatch, tmp_path):
    monkeypatch.setattr(
        pre_nixos.inventory,
        "enumerate_disks",
        lambda: [Disk(name="sda", size=1000, rotational=False)],
    )
    sample_lan = pre_nixos.network.LanConfiguration(
        authorized_key=tmp_path / "key.pub",
        interface="lan",
        rename_rule=None,
        network_unit=None,
    )
    called = []

    def fake_apply(plan, dry_run=False):
        called.append(True)

    monkeypatch.setattr(pre_nixos.apply, "apply_plan", fake_apply)
    monkeypatch.setattr(pre_nixos.network, "configure_lan", lambda: sample_lan)
    auto_flags: list[bool] = []

    def fake_auto_install(lan_config, plan, *, enabled, dry_run):
        auto_flags.append(enabled)
        return AutoInstallResult(status="skipped", reason="disabled")

    monkeypatch.setattr(pre_nixos.install, "auto_install", fake_auto_install)
    pre_nixos.main(["--no-auto-install"])
    assert called == [True]
    assert auto_flags == [False]


def test_cli_auto_install_failure_exits(monkeypatch, tmp_path):
    monkeypatch.setattr(
        pre_nixos.inventory,
        "enumerate_disks",
        lambda: [Disk(name="sda", size=1000, rotational=False)],
    )
    sample_lan = pre_nixos.network.LanConfiguration(
        authorized_key=tmp_path / "key.pub",
        interface="lan",
        rename_rule=None,
        network_unit=None,
    )
    monkeypatch.setattr(pre_nixos.network, "configure_lan", lambda: sample_lan)
    def noop_apply_failure(plan, dry_run=False):
        return None

    monkeypatch.setattr(pre_nixos.apply, "apply_plan", noop_apply_failure)

    def failing_auto_install(*args, **kwargs):
        return AutoInstallResult(status="failed", reason="nixos-install")

    monkeypatch.setattr(pre_nixos.install, "auto_install", failing_auto_install)

    with pytest.raises(SystemExit):
        pre_nixos.main([])
