"""Tests for network module."""

from pre_nixos.network import identify_lan


def test_identify_lan(tmp_path):
    for name, carrier in ("eth0", "0"), ("eth1", "1"):
        iface = tmp_path / name
        iface.mkdir()
        (iface / "device").mkdir()
        (iface / "carrier").write_text(carrier)
    assert identify_lan(tmp_path) == "eth1"
