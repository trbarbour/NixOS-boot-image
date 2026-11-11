"""The target's network comes from the managed block only (#342, item 46).

User report (2026-11-09): an install with a static address booted, but
networkd configured ``lan`` with ``/etc/systemd/network/20-lan.network``,
the installer's DHCP unit, so it had no address (no DHCP server).  An
earlier, failed DHCP install on the same root file system had copied that
unit into the target, and the static install left it there.  NixOS does not
manage that file name, and ``20-`` sorts before the declared ``40-lan`` and
``lan`` units, so the leftover won.

pre-nixos no longer copies the installer's ``10-lan.link`` or
``20-lan.network`` into the target (the managed block declares both the
rename and the network), and it removes copies an earlier attempt left.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from pre_nixos import install
from tests.test_install import _make_lan, _sample_storage_plan

STALE_DHCP = "[Match]\nName=lan\n\n[Network]\nDHCP=yes\n"
STALE_LINK = "[Match]\nOriginalName=eth0\n\n[Link]\nName=lan\n"


@pytest.fixture
def target(tmp_path, monkeypatch) -> Path:
    root = tmp_path / "mnt"
    (root / "etc").mkdir(parents=True)

    def fake_run(cmd, check=False):
        class Result:
            returncode = 0

        if cmd[0] == "nixos-generate-config":
            config_dir = root / "etc/nixos"
            config_dir.mkdir(parents=True, exist_ok=True)
            if not (config_dir / "configuration.nix").exists():
                (config_dir / "configuration.nix").write_text("{\n}\n", encoding="utf-8")
            (config_dir / "hardware-configuration.nix").write_text("{\n}\n", encoding="utf-8")
        return Result()

    monkeypatch.setattr(install.subprocess, "run", fake_run)
    monkeypatch.setattr(install, "_request_reboot", lambda: False)
    monkeypatch.setattr(install, "broadcast_to_consoles", lambda *a, **k: (False, [], {}))
    monkeypatch.setenv("PRE_NIXOS_EXEC", "1")
    return root


def _install(tmp_path: Path, root: Path, install_network=None):
    return install.auto_install(
        _make_lan(tmp_path),
        _sample_storage_plan(),
        enabled=True,
        trigger=install.InstallTrigger.REQUESTED,
        install_network=install_network,
        root_path=root,
        status_dir=tmp_path / "status",
        mount_attempts=1,
        mount_delay=0,
    )


def _plant_leftovers(root: Path) -> Path:
    network_dir = root / "etc/systemd/network"
    network_dir.mkdir(parents=True)
    (network_dir / "20-lan.network").write_text(STALE_DHCP)
    (network_dir / "10-lan.link").write_text(STALE_LINK)
    return network_dir


def test_static_install_over_an_earlier_dhcp_attempt(tmp_path, target) -> None:
    """The user's case: the earlier DHCP attempt's unit must not survive."""

    network_dir = _plant_leftovers(target)
    static = install.build_install_network_config("10.137.3.9", "255.255.255.0", "10.137.3.254")
    result = _install(tmp_path, target, static)
    assert result.status == "success", result
    assert not (network_dir / "20-lan.network").exists()
    assert not (network_dir / "10-lan.link").exists()
    content = (target / "etc/nixos/configuration.nix").read_text()
    assert 'networkConfig.Address = [ "10.137.3.9/24" ];' in content
    # Item 41 (R-N2): DNS reaches the installed system; it defaults to the gateway.
    assert 'networkConfig.DNS = [ "10.137.3.254" ];' in content


def test_dhcp_install_copies_no_unit_and_clears_leftovers(tmp_path, target) -> None:
    network_dir = _plant_leftovers(target)
    result = _install(tmp_path, target)
    assert result.status == "success", result
    assert sorted(p.name for p in network_dir.iterdir()) == []
    content = (target / "etc/nixos/configuration.nix").read_text()
    assert 'networkConfig.DHCP = "yes";' in content
    assert 'systemd.network.links."10-lan" = {' in content


def test_other_files_in_the_target_network_dir_are_kept(tmp_path, target) -> None:
    """Only pre-nixos's own unit names are removed."""

    network_dir = target / "etc/systemd/network"
    network_dir.mkdir(parents=True)
    (network_dir / "50-wlan.network").write_text("[Match]\nName=wlan0\n")
    _install(tmp_path, target)
    assert (network_dir / "50-wlan.network").exists()
