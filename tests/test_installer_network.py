"""The installer adopts the static network settings (task queue item 41).

Design: plans/2026-11-11T183853Z-installer-static-network-design.md
(R-N1 adopt when the installer has no address, R-N2 DNS, R-N3 undo).
"""

from __future__ import annotations

from pathlib import Path
from typing import List

import pytest

from pre_nixos import install, installer_network
from pre_nixos.installer_network import Mode
from pre_nixos.network import NetworkReadiness

STATIC = install.build_install_network_config("10.0.2.20", "255.255.255.0", "10.0.2.2", dns=["10.0.2.3", "9.9.9.9"])


class Runner:
    def __init__(self) -> None:
        self.calls: List[List[str]] = []

    def __call__(self, cmd: List[str]) -> None:
        self.calls.append(cmd)


def test_unit_matched_by_mac() -> None:
    text = installer_network.render_unit(STATIC, mac_address="52:54:00:12:34:56")
    assert text == (
        "# pre-nixos: the installer's static network (task queue item 41)\n"
        "[Match]\n"
        "MACAddress=52:54:00:12:34:56\n"
        "\n"
        "[Network]\n"
        "DHCP=no\n"
        "Address=10.0.2.20/24\n"
        "Gateway=10.0.2.2\n"
        "DNS=10.0.2.3\n"
        "DNS=9.9.9.9\n"
    )


def test_unit_matched_by_name_without_mac() -> None:
    text = installer_network.render_unit(STATIC, mac_address=None)
    assert "[Match]\nName=lan\n" in text


def test_unit_sorts_before_the_dhcp_unit() -> None:
    assert installer_network.UNIT_NAME < "20-lan.network"
    assert installer_network.UNIT_DIR == Path("/run/systemd/network")


@pytest.fixture(autouse=True)
def _executing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PRE_NIXOS_EXEC", "1")


def test_apply_writes_the_unit_and_reconfigures(tmp_path: Path) -> None:
    run = Runner()
    path = installer_network.apply(STATIC, mac_address=None, unit_dir=tmp_path, run=run)
    assert path == tmp_path / installer_network.UNIT_NAME
    assert "Address=10.0.2.20/24" in path.read_text()
    assert run.calls == [["networkctl", "reload"], ["networkctl", "reconfigure", "lan"]]


def test_remove_restores_dhcp(tmp_path: Path) -> None:
    run = Runner()
    installer_network.apply(STATIC, mac_address=None, unit_dir=tmp_path, run=run)
    run.calls.clear()
    assert installer_network.remove(unit_dir=tmp_path, run=run)
    assert not (tmp_path / installer_network.UNIT_NAME).exists()
    assert run.calls == [["networkctl", "reload"], ["networkctl", "reconfigure", "lan"]]
    run.calls.clear()
    assert not installer_network.remove(unit_dir=tmp_path, run=run)  # nothing to undo
    assert run.calls == []


@pytest.mark.parametrize("value", [None, "0", ""])
def test_nothing_happens_unless_pre_nixos_exec(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, value) -> None:
    """Codex on #351: like every other system command, only with PRE_NIXOS_EXEC=1."""

    if value is None:
        monkeypatch.delenv("PRE_NIXOS_EXEC", raising=False)
    else:
        monkeypatch.setenv("PRE_NIXOS_EXEC", value)
    run = Runner()
    assert installer_network.apply(STATIC, mac_address=None, unit_dir=tmp_path, run=run) is None
    assert not (tmp_path / installer_network.UNIT_NAME).exists()
    (tmp_path / installer_network.UNIT_NAME).write_text("left by an earlier run\n")
    assert not installer_network.remove(unit_dir=tmp_path, run=run)
    assert (tmp_path / installer_network.UNIT_NAME).exists()
    assert run.calls == []


@pytest.mark.parametrize(
    "mode,readiness,expected",
    [
        (Mode.AUTO, NetworkReadiness(None, None), True),
        (Mode.AUTO, NetworkReadiness("10.0.2.15", "10.0.2.2"), False),
        (Mode.AUTO, NetworkReadiness("10.0.2.15", None), False),
        (Mode.YES, NetworkReadiness("10.0.2.15", "10.0.2.2"), True),
        (Mode.NO, NetworkReadiness(None, None), False),
    ],
)
def test_decide(mode: Mode, readiness: NetworkReadiness, expected: bool) -> None:
    assert installer_network.decide(mode, readiness) is expected


# --- DNS in the static settings (R-N2) ----------------------------------------


def test_dns_defaults_to_the_gateway() -> None:
    config = install.build_install_network_config("10.0.2.20", "255.255.255.0", "10.0.2.2")
    assert config.dns == ("10.0.2.2",)


def test_dns_is_validated() -> None:
    with pytest.raises(ValueError, match="DNS"):
        install.build_install_network_config("10.0.2.20", "255.255.255.0", "10.0.2.2", dns=["resolver.example"])


def test_dns_round_trips_and_old_payloads_load(tmp_path: Path, monkeypatch) -> None:
    from pre_nixos import state

    assert STATIC.to_payload()["dns"] == ["10.0.2.3", "9.9.9.9"]
    state.record_install_network_config(STATIC.to_payload(), state_dir=tmp_path)
    assert install.load_install_network_config(state_dir=tmp_path) == STATIC
    old = {"address": "10.0.2.20", "netmask": "255.255.255.0", "gateway": "10.0.2.2"}
    state.record_install_network_config(old, state_dir=tmp_path)
    loaded = install.load_install_network_config(state_dir=tmp_path)
    assert loaded is not None and loaded.dns == ("10.0.2.2",)


def test_parse_dns_list() -> None:
    assert installer_network.parse_dns("10.0.2.3, 9.9.9.9") == ["10.0.2.3", "9.9.9.9"]
    assert installer_network.parse_dns("10.0.2.3 9.9.9.9") == ["10.0.2.3", "9.9.9.9"]
    assert installer_network.parse_dns("") == []
