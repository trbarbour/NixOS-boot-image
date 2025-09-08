"""Tests for network module."""

from pre_nixos.network import identify_lan, write_lan_rename_rule


def test_identify_lan(tmp_path):
    for name, carrier in ("eth0", "0"), ("eth1", "1"):
        iface = tmp_path / name
        iface.mkdir()
        (iface / "device").mkdir()
        (iface / "carrier").write_text(carrier)
    assert identify_lan(tmp_path) == "eth1"


def test_write_lan_rename_rule(tmp_path):
    for name, carrier in ("eth0", "0"), ("eth1", "1"):
        iface = tmp_path / name
        iface.mkdir()
        (iface / "device").mkdir()
        (iface / "carrier").write_text(carrier)

    rules_dir = tmp_path / "etc/systemd/network"
    path = write_lan_rename_rule(tmp_path, rules_dir)
    assert path == rules_dir / "10-lan.link"
    assert path.read_text() == "[Match]\nOriginalName=eth1\n\n[Link]\nName=lan\n"


def test_write_lan_rename_rule_no_iface(tmp_path):
    rules_dir = tmp_path / "etc/systemd/network"
    assert write_lan_rename_rule(tmp_path, rules_dir) is None
    assert not (rules_dir / "10-lan.link").exists()
