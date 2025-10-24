"""Tests for network module."""

import errno
import json
import subprocess
from pathlib import Path

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


def test_identify_lan_uses_operstate_on_transient_carrier_error(tmp_path, monkeypatch):
    netdir = tmp_path / "net"
    netdir.mkdir()

    iface = netdir / "eth0"
    iface.mkdir()
    (iface / "device").mkdir()
    (iface / "operstate").write_text("up")

    other = netdir / "eth1"
    other.mkdir()
    (other / "device").mkdir()
    (other / "carrier").write_text("0")

    original_read_text = Path.read_text

    def fake_read_text(self, *args, **kwargs):
        if self == iface / "carrier":
            raise OSError(errno.EINVAL, "Invalid argument")
        return original_read_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", fake_read_text)

    assert identify_lan(netdir) == "eth0"


def test_identify_lan_logs_operstate_detection(tmp_path, monkeypatch):
    netdir = tmp_path / "net"
    netdir.mkdir()

    iface = netdir / "eth0"
    iface.mkdir()
    (iface / "device").mkdir()
    (iface / "operstate").write_text("up")

    other = netdir / "eth1"
    other.mkdir()
    (other / "device").mkdir()
    (other / "carrier").write_text("0")

    events: list[tuple[str, dict[str, object]]] = []

    def record_event(event: str, **fields: object) -> None:
        events.append((event, fields))

    monkeypatch.setattr("pre_nixos.network.log_event", record_event)

    original_read_text = Path.read_text

    def fake_read_text(self, *args, **kwargs):
        if self == iface / "carrier":
            error = OSError("transient carrier failure")
            error.errno = 0
            raise error
        return original_read_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", fake_read_text)

    assert identify_lan(netdir) == "eth0"

    detection_events = [
        fields for event, fields in events if event == "pre_nixos.network.identify_lan.detected"
    ]
    assert detection_events, "expected structured detection log event"
    assert detection_events[0]["interface"] == "eth0"
    assert detection_events[0]["signal"] == "operstate"


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


def test_configure_lan_secures_ssh_without_detected_iface(tmp_path):
    netdir = tmp_path / "sys/class/net"
    netdir.mkdir(parents=True)

    network_dir = tmp_path / "etc/systemd/network"
    ssh_dir = tmp_path / "etc/ssh"
    root_home = tmp_path / "root"

    key = tmp_path / "id_ed25519.pub"
    key.write_text("ssh-ed25519 AAAAB3NzaC1yc2EAAAADAQABAAACAQC7 test@local")

    result = configure_lan(
        netdir, network_dir, ssh_dir, authorized_key=key, root_home=root_home
    )
    assert result is None
    auth_keys = root_home / ".ssh/authorized_keys"
    assert auth_keys.read_text() == key.read_text()
    ssh_conf = ssh_dir / "sshd_config"
    assert "PasswordAuthentication no" in ssh_conf.read_text()


def test_configure_lan_emits_structured_logs(tmp_path, monkeypatch, capsys):
    netdir = tmp_path / "sys/class/net"
    netdir.mkdir(parents=True)
    iface = netdir / "eth0"
    iface.mkdir()
    (iface / "device").mkdir()
    (iface / "carrier").write_text("1")

    network_dir = tmp_path / "etc/systemd/network"
    ssh_dir = tmp_path / "etc/ssh"
    root_home = tmp_path / "root"

    key = tmp_path / "id_ed25519.pub"
    key.write_text("ssh-ed25519 AAAAB3NzaC1yc2EAAAADAQABAAACAQC7 test@local")

    monkeypatch.setenv("PRE_NIXOS_EXEC", "0")

    configure_lan(
        netdir, network_dir, ssh_dir, authorized_key=key, root_home=root_home
    )

    captured = capsys.readouterr()
    events = [json.loads(line)["event"] for line in captured.err.splitlines() if line.strip()]
    assert "pre_nixos.network.configure_lan.start" in events
    assert "pre_nixos.network.configure_lan.detected_interface" in events
    assert "pre_nixos.network.configure_lan.finished" in events
    assert "pre_nixos.network.command.skip" in events


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


def test_secure_ssh_queues_non_blocking_restart(tmp_path, monkeypatch):
    ssh_dir = tmp_path / "etc/ssh"
    ssh_dir.mkdir(parents=True)

    key = tmp_path / "id_ed25519.pub"
    key.write_text("ssh-ed25519 AAAAB3NzaC1yc2EAAAADAQABAAACAQC7 test@local")

    calls: list[tuple[list[str], bool]] = []

    def fake_systemctl(args, *, ignore_missing=False):
        calls.append((list(args), ignore_missing))

    monkeypatch.setattr("pre_nixos.network._systemctl", fake_systemctl)

    secure_ssh(ssh_dir, authorized_key=key, root_home=tmp_path / "root")

    assert calls == [(["reload-or-restart", "--no-block", "sshd"], False)]


def test_secure_ssh_logs_key_propagation(tmp_path, monkeypatch):
    ssh_dir = tmp_path / "etc/ssh"
    ssh_dir.mkdir(parents=True)

    key = tmp_path / "id_ed25519.pub"
    key.write_text("ssh-ed25519 AAAAB3NzaC1yc2EAAAADAQABAAACAQC7 test@local")

    events: list[tuple[str, dict[str, object]]] = []

    def record_event(event: str, **fields: object) -> None:
        events.append((event, fields))

    monkeypatch.setattr("pre_nixos.network.log_event", record_event)
    monkeypatch.setattr("pre_nixos.network._systemctl", lambda *a, **k: None)

    conf_path = secure_ssh(ssh_dir, authorized_key=key, root_home=tmp_path / "root")

    event_names = [event for event, _ in events]
    assert "pre_nixos.network.secure_ssh.authorized_key_written" in event_names
    assert event_names[-1] == "pre_nixos.network.secure_ssh.finished"

    finished_fields = next(
        fields for event, fields in events if event == "pre_nixos.network.secure_ssh.finished"
    )
    expected_auth_path = tmp_path / "root" / ".ssh" / "authorized_keys"
    assert finished_fields["authorized_keys_path"] == expected_auth_path
    assert conf_path == ssh_dir / "sshd_config"


def test_get_ip_address_parses_output(monkeypatch):
    class DummyResult:
        stdout = json.dumps(
            [
                {
                    "ifname": "lan",
                    "addr_info": [
                        {"family": "inet", "local": "192.0.2.5", "prefixlen": 24}
                    ],
                }
            ]
        )

    monkeypatch.setattr(
        subprocess, "run", lambda *a, **k: DummyResult()
    )
    assert get_ip_address("lan") == "192.0.2.5"


def test_get_ip_address_returns_none_for_malformed_json(monkeypatch):
    class DummyResult:
        stdout = "{not-json}"

    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *a, **k: DummyResult(),
    )
    assert get_ip_address("lan") is None


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
        stdout = json.dumps(
            [
                {
                    "ifname": "lan",
                    "addr_info": [
                        {"family": "inet", "local": "203.0.113.9", "prefixlen": 24}
                    ],
                }
            ]
        )

    monkeypatch.setattr(subprocess, "run", lambda *a, **k: DummyResult())
    assert get_lan_status(authorized_key=key) == "203.0.113.9"
