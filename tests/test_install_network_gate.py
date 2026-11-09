"""Automatic installs wait for the installer's network (task queue item 44).

User report (2026-11-09): on a network with no DHCP server, the TUI's Apply
provisioned the disks and then started ``nixos-install`` straight away, with
no IPv4 address; it failed downloading.  User decision: an automatic install
needs an IPv4 address **and** a default route on ``lan`` (option b).  An
explicit request (``pre-nixos --install-now``, the TUI's ``N``) still runs,
with a warning.
"""

from __future__ import annotations

import pytest

from pre_nixos import install, network
from pre_nixos.network import NetworkReadiness
from tests.test_install import _make_lan, _sample_storage_plan

# conftest replaces installer_network for every test; keep the real one.
REAL_INSTALLER_NETWORK = network.installer_network


@pytest.fixture
def started(monkeypatch, tmp_path) -> list[str]:
    """Records whether the install went past the gate (mounting /mnt)."""

    calls: list[str] = []
    monkeypatch.setenv("PRE_NIXOS_EXEC", "1")

    def fake_wait(root_path, **kwargs):
        calls.append("mount-wait")
        return False  # stop right after the gate

    monkeypatch.setattr(install, "_wait_for_mount", fake_wait)
    return calls


def _readiness(monkeypatch, readiness: NetworkReadiness) -> None:
    monkeypatch.setattr(network, "installer_network", lambda iface="lan": readiness)


def _run(tmp_path, trigger=install.InstallTrigger.AUTOMATIC):
    return install.auto_install(
        _make_lan(tmp_path),
        _sample_storage_plan(),
        enabled=True,
        trigger=trigger,
        root_path=tmp_path / "mnt",
        status_dir=tmp_path / "status",
    )


@pytest.mark.parametrize(
    "readiness",
    [
        NetworkReadiness(address=None, gateway=None),
        NetworkReadiness(address="10.137.3.9", gateway=None),
    ],
    ids=["no-address", "no-default-route"],
)
def test_automatic_install_waits_for_address_and_route(
    tmp_path, monkeypatch, started, capsys, readiness
) -> None:
    _readiness(monkeypatch, readiness)
    result = _run(tmp_path)
    assert (result.status, result.reason) == ("skipped", "no-network")
    assert started == []
    status = (tmp_path / "status" / "auto-install-status").read_text()
    assert "STATE=skipped" in status and "REASON=no-network" in status
    out = capsys.readouterr().out
    assert "--install-now" in out and "default route" in out


def test_automatic_install_proceeds_with_address_and_route(tmp_path, monkeypatch, started) -> None:
    _readiness(monkeypatch, NetworkReadiness(address="10.137.3.9", gateway="10.137.3.1"))
    result = _run(tmp_path)
    assert started == ["mount-wait"]
    assert result.reason == "mount-unavailable"


def test_requested_install_warns_but_proceeds(tmp_path, monkeypatch, started, capsys) -> None:
    _readiness(monkeypatch, NetworkReadiness(address=None, gateway=None))
    result = _run(tmp_path, trigger=install.InstallTrigger.REQUESTED)
    assert started == ["mount-wait"]
    assert result.reason == "mount-unavailable"
    assert "no IPv4 address" in capsys.readouterr().out


def test_readiness_from_ipv4_details(monkeypatch) -> None:
    monkeypatch.setattr(network, "installer_network", REAL_INSTALLER_NETWORK)
    details = network.IPv4Details(
        address="10.137.3.9", netmask="255.255.255.0", prefix_length=24, gateway="10.137.3.1"
    )
    monkeypatch.setattr(network, "get_ipv4_details", lambda iface="lan": details)
    assert network.installer_network() == NetworkReadiness("10.137.3.9", "10.137.3.1")
    assert network.installer_network().ready
    no_route = network.IPv4Details(address="10.137.3.9", netmask="255.255.255.0", prefix_length=24)
    monkeypatch.setattr(network, "get_ipv4_details", lambda iface="lan": no_route)
    assert not network.installer_network().ready
    monkeypatch.setattr(network, "get_ipv4_details", lambda iface="lan": None)
    assert network.installer_network() == NetworkReadiness(None, None)
    assert "no IPv4 address" in network.installer_network().problem
