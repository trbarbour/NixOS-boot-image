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
    pre_nixos.main(["--plan-only"])
    out = capsys.readouterr().out
    assert "main" in out
    console_output = fake_console.getvalue()
    assert console_output.endswith("\r\n")
    # There should be no bare line feeds, ensuring console output renders
    # correctly on terminals that require carriage returns.
    assert "\n" not in console_output.replace("\r\n", "")
    assert "main" in console_output
