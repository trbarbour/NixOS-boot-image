"""A manual run reuses the LAN set up at boot (task queue item 35).

User report (2026-11-06): ``pre-nixos --plan-only`` took 60.76 s on a network
that deliberately gives no DHCP lease.  The events log showed every manual run
redoing ``configure_lan``: renaming and bouncing the link, then waiting 60 s
in ``wait_for_ipv4``.  The boot-time run had already done all of it.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from pre_nixos import lan_reuse, network
from pre_nixos.network import LanConfiguration

MAC = "6c:62:6d:54:8f:1d"


def _boot_setup(tmp_path: Path) -> tuple[Path, LanConfiguration]:
    """The state the boot-time run leaves: ``lan`` present, its files written."""

    net = tmp_path / "sys/class/net"
    (net / "lan").mkdir(parents=True)
    (net / "lan" / "address").write_text(MAC + "\n")
    units = tmp_path / "etc/systemd/network"
    units.mkdir(parents=True)
    rule = units / "10-lan.link"
    unit = units / "20-lan.network"
    rule.write_text("[Match]\n")
    unit.write_text("[Match]\nName=lan\n")
    key = tmp_path / "root_key.pub"
    key.write_text("ssh-ed25519 AAAA test\n")
    config = LanConfiguration(
        authorized_key=key,
        interface="lan",
        rename_rule=rule,
        network_unit=unit,
        mac_address=MAC,
    )
    return net, config


def _forbid_configure(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail() -> None:
        raise AssertionError("configure_lan must not run again")

    monkeypatch.setattr(network, "configure_lan", fail)


def test_record_round_trip(tmp_path: Path) -> None:
    _net, config = _boot_setup(tmp_path)
    path = lan_reuse.record_lan_configuration(config, state_dir=tmp_path / "state")
    assert path == tmp_path / "state" / "lan-configuration.json"
    assert lan_reuse.load_lan_configuration(state_dir=tmp_path / "state") == config


def test_record_round_trip_keeps_absent_optional_fields(tmp_path: Path) -> None:
    config = LanConfiguration(authorized_key=tmp_path / "k.pub", interface="lan")
    lan_reuse.record_lan_configuration(config, state_dir=tmp_path)
    assert lan_reuse.load_lan_configuration(state_dir=tmp_path) == config


@pytest.mark.parametrize(
    "text",
    [
        "not json",
        "[]",
        json.dumps({"interface": "lan"}),
        json.dumps({"authorized_key": 3, "interface": "lan"}),
        json.dumps({"authorized_key": "/k", "interface": "lan", "mac_address": 7}),
    ],
)
def test_malformed_record_is_ignored(tmp_path: Path, text: str) -> None:
    (tmp_path / "lan-configuration.json").write_text(text)
    assert lan_reuse.load_lan_configuration(state_dir=tmp_path) is None


def test_second_run_reuses_the_boot_configuration(tmp_path, monkeypatch) -> None:
    net, config = _boot_setup(tmp_path)
    state_dir = tmp_path / "state"
    calls: list[bool] = []
    monkeypatch.setattr(network, "configure_lan", lambda: calls.append(True) or config)

    first = lan_reuse.ensure_lan(net_path=net, state_dir=state_dir)
    _forbid_configure(monkeypatch)
    second = lan_reuse.ensure_lan(net_path=net, state_dir=state_dir)

    assert calls == [True]
    assert first == second == config


@pytest.mark.parametrize(
    "break_it",
    [
        pytest.param(lambda net, c: (net / "lan" / "address").unlink() or (net / "lan").rmdir(), id="lan-gone"),
        pytest.param(lambda net, c: (net / "lan" / "address").write_text("00:00:00:00:00:01\n"), id="other-nic"),
        pytest.param(lambda net, c: c.network_unit.unlink(), id="unit-gone"),
        pytest.param(lambda net, c: c.rename_rule.unlink(), id="rule-gone"),
        pytest.param(lambda net, c: c.authorized_key.unlink(), id="key-gone"),
    ],
)
def test_stale_record_configures_again(tmp_path, monkeypatch, break_it) -> None:
    net, config = _boot_setup(tmp_path)
    state_dir = tmp_path / "state"
    lan_reuse.record_lan_configuration(config, state_dir=state_dir)
    break_it(net, config)
    fresh = LanConfiguration(authorized_key=tmp_path / "fresh.pub", interface="lan")
    monkeypatch.setattr(network, "configure_lan", lambda: fresh)

    assert lan_reuse.ensure_lan(net_path=net, state_dir=state_dir) == fresh
    # The new configuration replaces the stale record.
    assert lan_reuse.load_lan_configuration(state_dir=state_dir) == fresh


def test_no_carrier_at_boot_is_not_recorded(tmp_path, monkeypatch) -> None:
    """With no link at boot, a later run looks again (a cable plugged in since)."""

    net = tmp_path / "sys/class/net"
    net.mkdir(parents=True)
    state_dir = tmp_path / "state"
    no_link = LanConfiguration(authorized_key=tmp_path / "k.pub", interface=None)
    calls: list[bool] = []
    monkeypatch.setattr(network, "configure_lan", lambda: calls.append(True) or no_link)

    lan_reuse.ensure_lan(net_path=net, state_dir=state_dir)
    lan_reuse.ensure_lan(net_path=net, state_dir=state_dir)

    assert calls == [True, True]
    assert lan_reuse.load_lan_configuration(state_dir=state_dir) is None


def test_no_key_is_not_recorded(tmp_path, monkeypatch) -> None:
    net = tmp_path / "sys/class/net"
    net.mkdir(parents=True)
    calls: list[bool] = []
    monkeypatch.setattr(network, "configure_lan", lambda: calls.append(True) or None)

    assert lan_reuse.ensure_lan(net_path=net, state_dir=tmp_path) is None
    assert lan_reuse.ensure_lan(net_path=net, state_dir=tmp_path) is None
    assert calls == [True, True]


def test_unwritable_state_dir_still_returns_the_configuration(tmp_path, monkeypatch) -> None:
    net, config = _boot_setup(tmp_path)
    blocker = tmp_path / "state"
    blocker.write_text("a file, not a directory")
    monkeypatch.setattr(network, "configure_lan", lambda: config)

    assert lan_reuse.ensure_lan(net_path=net, state_dir=blocker) == config


def test_reuse_is_logged(tmp_path, monkeypatch, capsys) -> None:
    net, config = _boot_setup(tmp_path)
    lan_reuse.record_lan_configuration(config, state_dir=tmp_path / "state")
    _forbid_configure(monkeypatch)
    monkeypatch.setenv("PRE_NIXOS_LOG_EVENTS", "1")

    lan_reuse.ensure_lan(net_path=net, state_dir=tmp_path / "state")

    events = [json.loads(line)["event"] for line in capsys.readouterr().err.splitlines() if line.startswith("{")]
    assert "pre_nixos.network.ensure_lan.reused" in events


def test_cli_manual_run_does_not_reconfigure_the_lan(tmp_path, monkeypatch, capsys) -> None:
    """The CLI uses the boot's configuration (and hands it to the installer)."""

    import pre_nixos.pre_nixos as cli
    from pre_nixos.install import AutoInstallResult

    net, config = _boot_setup(tmp_path)
    monkeypatch.setenv("PRE_NIXOS_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setattr(lan_reuse, "_NET_PATH", net)
    lan_reuse.record_lan_configuration(config)
    _forbid_configure(monkeypatch)
    seen: list[object] = []

    def fake_auto_install(lan_config, plan, **kwargs):
        seen.append(lan_config)
        return AutoInstallResult(status="success")

    monkeypatch.setattr(cli.install, "auto_install", fake_auto_install)
    cli.main(["--install-now"])
    assert seen == [config]
