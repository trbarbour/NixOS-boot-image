"""Tests for network module."""

from pre_nixos.network import identify_lan, write_lan_rename_rule, configure_lan


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


def test_configure_lan_writes_network_file(tmp_path):
    netdir = tmp_path / "sys/class/net"
    netdir.mkdir(parents=True)
    for name, carrier in ("eth0", "0"), ("eth1", "1"):
        iface = netdir / name
        iface.mkdir()
        (iface / "device").mkdir()
        (iface / "carrier").write_text(carrier)

    network_dir = tmp_path / "etc/systemd/network"
    network_file = configure_lan(netdir, network_dir)
    assert network_file == network_dir / "20-lan.network"
    assert "DHCP=yes" in network_file.read_text()
