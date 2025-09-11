"""Tests for network module."""

import subprocess

from pre_nixos.network import (
    configure_lan,
    identify_lan,
    get_ip_address,
    get_lan_status,
    secure_ssh,
    write_lan_rename_rule,
)


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
    ssh_dir = tmp_path / "etc/ssh"
    root_home = tmp_path / "root"
    key = tmp_path / "id_ed25519.pub"
    key.write_text("ssh-ed25519 AAAAB3NzaC1yc2EAAAADAQABAAACAQC7 test@local")

    network_file = configure_lan(
        netdir, network_dir, ssh_dir, authorized_key=key, root_home=root_home
    )
    assert network_file == network_dir / "20-lan.network"
    assert "DHCP=yes" in network_file.read_text()
    auth_keys = root_home / ".ssh/authorized_keys"
    assert auth_keys.read_text() == key.read_text()
    ssh_conf = ssh_dir / "sshd_config"
    assert "PasswordAuthentication no" in ssh_conf.read_text()


def test_configure_lan_skips_without_key(tmp_path):
    netdir = tmp_path / "sys/class/net"
    netdir.mkdir(parents=True)
    iface = netdir / "eth0"
    iface.mkdir()
    (iface / "device").mkdir()
    (iface / "carrier").write_text("1")

    network_dir = tmp_path / "etc/systemd/network"
    ssh_dir = tmp_path / "etc/ssh"
    root_home = tmp_path / "root"

    result = configure_lan(netdir, network_dir, ssh_dir, root_home=root_home)
    assert result is None
    assert not (network_dir / "20-lan.network").exists()
    assert not (root_home / ".ssh/authorized_keys").exists()


def test_secure_ssh_replaces_symlink_and_filters_insecure_directives(tmp_path):
    ssh_dir = tmp_path / "etc/ssh"
    ssh_dir.mkdir(parents=True)
    store_dir = tmp_path / "nix/store/abcd-sshd"
    store_dir.mkdir(parents=True)
    store_conf = store_dir / "sshd_config"
    store_conf.write_text(
        "X11Forwarding no\nPasswordAuthentication yes\nPermitRootLogin yes\n"
    )
    store_conf.chmod(0o444)
    (ssh_dir / "sshd_config").symlink_to(store_conf)

    key = tmp_path / "id_ed25519.pub"
    key.write_text("ssh-ed25519 AAAAB3NzaC1yc2EAAAADAQABAAACAQC7 test@local")

    conf_path = secure_ssh(ssh_dir, authorized_key=key, root_home=tmp_path / "root")
    assert conf_path == ssh_dir / "sshd_config"
    assert conf_path.is_file() and not conf_path.is_symlink()
    text = conf_path.read_text()
    assert "X11Forwarding no" in text
    assert "PasswordAuthentication yes" not in text
    assert "PermitRootLogin yes" not in text
    assert "PasswordAuthentication no" in text
    assert "PermitRootLogin prohibit-password" in text


def test_get_ip_address_parses_output(monkeypatch):
    class DummyResult:
        stdout = "2: lan    inet 192.0.2.5/24 brd 192.0.2.255 scope global lan\n"

    monkeypatch.setattr(
        subprocess, "run", lambda *a, **k: DummyResult()
    )
    assert get_ip_address("lan") == "192.0.2.5"


def test_get_lan_status_reports_missing_key(tmp_path):
    missing = tmp_path / "no_key.pub"
    assert get_lan_status(authorized_key=missing) == "missing SSH public key"


def test_get_lan_status_reports_missing_ip(tmp_path, monkeypatch):
    key = tmp_path / "id_ed25519.pub"
    key.write_text("ssh-ed25519 AAAAB3NzaC1 test@local")
    def raise_err(*args, **kwargs):
        raise subprocess.CalledProcessError(1, args[0])

    monkeypatch.setattr(subprocess, "run", raise_err)
    assert get_lan_status(authorized_key=key) == "no IP address"


def test_get_lan_status_returns_ip(tmp_path, monkeypatch):
    key = tmp_path / "id_ed25519.pub"
    key.write_text("ssh-ed25519 AAAAB3NzaC1 test@local")

    class DummyResult:
        stdout = "2: lan    inet 203.0.113.9/24 brd 203.0.113.255 scope global lan\n"

    monkeypatch.setattr(subprocess, "run", lambda *a, **k: DummyResult())
    assert get_lan_status(authorized_key=key) == "203.0.113.9"
