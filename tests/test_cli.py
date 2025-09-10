"""Tests for CLI entry point."""

from pre_nixos import pre_nixos
from pre_nixos.inventory import Disk


def test_cli_plan_only(monkeypatch, capsys):
    monkeypatch.setattr(
        pre_nixos.inventory,
        "enumerate_disks",
        lambda: [Disk(name="sda", size=1000, rotational=False)],
    )
    called = []
    net_called = []

    def fake_apply(plan, dry_run=False):
        called.append(dry_run)

    monkeypatch.setattr(pre_nixos.apply, "apply_plan", fake_apply)
    monkeypatch.setattr(pre_nixos.network, "configure_lan", lambda: net_called.append(True))
    pre_nixos.main(["--plan-only"])
    out = capsys.readouterr().out
    assert "main" in out
    assert called == []
    assert net_called == [True]


def test_cli_apply_called(monkeypatch):
    monkeypatch.setattr(
        pre_nixos.inventory,
        "enumerate_disks",
        lambda: [Disk(name="sda", size=1000, rotational=False)],
    )
    called = []
    net_called = []

    def fake_apply(plan, dry_run=False):
        called.append(dry_run)

    monkeypatch.setattr(pre_nixos.apply, "apply_plan", fake_apply)
    monkeypatch.setattr(pre_nixos.network, "configure_lan", lambda: net_called.append(True))
    pre_nixos.main([])
    assert called == [False]
    assert net_called == [True]


def test_cli_writes_console(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(
        pre_nixos.inventory,
        "enumerate_disks",
        lambda: [Disk(name="sda", size=1000, rotational=False)],
    )
    fake_console = tmp_path / "console.log"
    console_file = fake_console.open("w")

    def open_console():
        return console_file

    monkeypatch.setattr(pre_nixos, "_maybe_open_console", open_console)
    pre_nixos.main(["--plan-only"])
    console_file.close()
    out = capsys.readouterr().out
    assert "main" in out
    assert "main" in fake_console.read_text()
