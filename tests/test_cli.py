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

    def fake_apply(plan, dry_run=False):
        called.append(dry_run)

    monkeypatch.setattr(pre_nixos.apply, "apply_plan", fake_apply)
    pre_nixos.main(["--plan-only"])
    out = capsys.readouterr().out
    assert "main" in out
    assert called == []


def test_cli_apply_called(monkeypatch):
    monkeypatch.setattr(
        pre_nixos.inventory,
        "enumerate_disks",
        lambda: [Disk(name="sda", size=1000, rotational=False)],
    )
    called = []

    def fake_apply(plan, dry_run=False):
        called.append(dry_run)

    monkeypatch.setattr(pre_nixos.apply, "apply_plan", fake_apply)
    pre_nixos.main([])
    assert called == [False]
