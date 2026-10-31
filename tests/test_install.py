"""Tests for the automated installation helper."""

import re
from datetime import datetime, timezone
from pathlib import Path

import pytest

from pre_nixos import install
from pre_nixos.network import LanConfiguration


@pytest.fixture
def broadcast_messages(monkeypatch) -> list[str]:
    messages: list[str] = []

    def fake_broadcast(message: str, **_: object):
        messages.append(message)
        path = Path("/dev/console")
        return True, [path], {path: True}

    monkeypatch.setattr(install, "broadcast_to_consoles", fake_broadcast)
    return messages


def _sample_storage_plan() -> dict:
    return {
        "disko": {
            "disk": {
                "sda": {
                    "type": "disk",
                    "device": "/dev/sda",
                    "content": {
                        "type": "gpt",
                        "partitions": {
                            "sda1": {
                                "size": "1G",
                                "type": "EF00",
                                "content": {
                                    "type": "filesystem",
                                    "format": "vfat",
                                    "mountpointPermissions": 0,
                                    "mountpoint": "/boot",
                                    "mountOptions": ["umask=0077"],
                                    "extraArgs": ["-n", "EFI"],
                                },
                            },
                            "sda2": {
                                "size": "100%",
                                "content": {
                                    "type": "lvm_pv",
                                    "vg": "main",
                                },
                            },
                        },
                    },
                }
            },
            "lvm_vg": {
                "main": {
                    "type": "lvm_vg",
                    "lvs": {
                        "slash": {
                            "size": "50G",
                            "content": {
                                "type": "filesystem",
                                "format": "ext4",
                                "mountpointPermissions": 0,
                                "mountpoint": "/",
                                "mountOptions": ["relatime"],
                                "extraArgs": ["-L", "slash"],
                            },
                        },
                        "home": {
                            "size": "25G",
                            "content": {
                                "type": "filesystem",
                                "format": "ext4",
                                "mountpointPermissions": 0,
                                "mountpoint": "/home",
                                "mountOptions": ["relatime"],
                                "extraArgs": ["-L", "home"],
                            },
                        },
                        "swap": {
                            "size": "16G",
                            "content": {
                                "type": "swap",
                                "extraArgs": ["--label", "swap"],
                            },
                        },
                    },
                }
            },
        }
    }


def _make_lan(tmp_path: Path, *, original_name: str = "eth0") -> LanConfiguration:
    key_path = tmp_path / "key.pub"
    key_path.write_text("ssh-ed25519 AAAAB3NzaC1yc2EAAAADAQABAAACAQC7 test@local")
    rename_rule = tmp_path / "10-lan.link"
    rename_rule.write_text(
        "[Match]\n"
        f"OriginalName={original_name}\n"
        "MACAddress=00:11:22:33:44:55\n\n"
        "[Link]\n"
        "Name=lan\n"
    )
    network_unit = tmp_path / "20-lan.network"
    network_unit.write_text("[Match]\nName=lan\n[Network]\nDHCP=yes\n")
    return LanConfiguration(
        authorized_key=key_path,
        interface="lan",
        rename_rule=rename_rule,
        network_unit=network_unit,
        mac_address="00:11:22:33:44:55",
    )


def test_auto_install_skips_when_disabled(tmp_path, monkeypatch, broadcast_messages):
    lan = _make_lan(tmp_path)
    monkeypatch.setenv("PRE_NIXOS_EXEC", "1")
    result = install.auto_install(
        lan,
        _sample_storage_plan(),
        enabled=False,
        root_path=tmp_path / "mnt",
        status_dir=tmp_path / "status",
    )
    assert result.status == "skipped"
    assert result.reason == "disabled"
    status_file = (tmp_path / "status" / "auto-install-status")
    assert status_file.read_text() == "STATE=skipped\nREASON=disabled\n"
    assert broadcast_messages == []


def test_auto_install_success_writes_configuration(tmp_path, monkeypatch, broadcast_messages):
    root = tmp_path / "mnt"
    (root / "etc").mkdir(parents=True)
    lan = _make_lan(tmp_path)

    commands: list[list[str]] = []

    start_time = datetime(2025, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
    completion_time = datetime(2025, 1, 2, 3, 14, 5, tzinfo=timezone.utc)

    class FakeDateTime:
        calls = 0

        @classmethod
        def now(cls, tz=None):
            cls.calls += 1
            return start_time if cls.calls == 1 else completion_time

    def fake_run(cmd, check=False):
        commands.append(cmd)

        class Result:
            returncode = 0

        if cmd[0] == "nixos-generate-config":
            config_dir = root / "etc/nixos"
            config_dir.mkdir(parents=True, exist_ok=True)
            (config_dir / "configuration.nix").write_text("{\n}\n", encoding="utf-8")
            (config_dir / "hardware-configuration.nix").write_text(
                "{\n"
                "  fileSystems.\"/\" = { device = \"/dev/disk/by-uuid/OLD\"; };\n"
                "  swapDevices = [ { device = \"/dev/disk/by-uuid/OLD-SWAP\"; } ];\n"
                "  networking.useDHCP = lib.mkDefault true;\n"
                "}\n",
                encoding="utf-8",
            )
        return Result()

    monkeypatch.setattr(install.subprocess, "run", fake_run)
    monkeypatch.setenv("PRE_NIXOS_EXEC", "1")
    monkeypatch.setattr(install, "datetime", FakeDateTime)
    monkeypatch.setattr(
        install,
        "_read_kernel_cmdline_tokens",
        lambda: ("console=ttyS0,115200n8", "console=tty0"),
    )

    reboot_called: list[bool] = []

    def fake_reboot() -> bool:
        reboot_called.append(True)
        return True

    monkeypatch.setattr(install, "_request_reboot", fake_reboot)

    result = install.auto_install(
        lan,
        _sample_storage_plan(),
        root_path=root,
        status_dir=tmp_path / "status",
    )
    assert result.status == "success"
    assert commands == [
        ["nixos-generate-config", "--root", str(root)],
        ["nixos-install", "--root", str(root), "--no-root-passwd"],
    ]
    assert reboot_called == [True]

    config_path = root / "etc/nixos/configuration.nix"
    content = config_path.read_text()
    assert "networking.firewall" in content
    assert "networking.useDHCP = false;" in content
    assert "networking.useNetworkd = true;" in content
    assert "networking.interfaces.lan = {" in content
    assert "useDHCP = true;" in content
    assert 'matchConfig.MACAddress = "00:11:22:33:44:55";' in content
    assert 'systemd.network.links."10-lan"' in content
    assert content.count('matchConfig.MACAddress = "00:11:22:33:44:55";') >= 2
    assert 'matchConfig.OriginalName' not in content
    assert 'matchConfig.Name = "lan";' not in content
    assert "./pre-nixos-auto-install-ip.nix" in content
    assert 'boot.kernelParams = [ "console=ttyS0,115200n8" "console=tty0" ];' in content
    serial_index = content.find('"console=ttyS0,115200n8"')
    vga_index = content.find('"console=tty0"')
    assert serial_index != -1
    assert vga_index != -1
    assert serial_index < vga_index
    assert "boot.loader.grub.extraConfig = ''" in content
    assert "serial --speed=115200 --unit=0 --word=8 --parity=no --stop=1" in content
    assert "experimental-features = [ \"nix-command\" \"flakes\" ]" in content
    authorized_line = '"ssh-ed25519 AAAAB3NzaC1yc2EAAAADAQABAAACAQC7 test@local"'
    assert authorized_line in content
    assert 'fileSystems = {' in content
    assert '"/" = {' in content
    assert 'label = "slash";' in content
    assert 'neededForBoot = true;' in content
    assert '"/boot" = {' in content
    assert 'label = "EFI";' in content
    assert '"/home" = {' in content
    assert 'label = "home";' in content
    assert 'systemd.tmpfiles.rules = [' in content
    assert '    "d /boot 000 root root -"' in content
    assert '    "d /home 000 root root -"' in content
    assert 'swapDevices = [' in content
    assert 'label = "swap";' in content
    assert 'boot.swraid.enable = true;' in content
    assert "boot.swraid.mdadmConf = ''" in content
    assert 'MAILADDR root' in content
    assert 'boot.initrd.services.lvm.enable = true;' in content

    hardware_text = (root / "etc/nixos/hardware-configuration.nix").read_text()
    assert 'fileSystems."/' not in hardware_text
    assert "swapDevices" not in hardware_text
    assert "networking.useDHCP" not in hardware_text

    module_content = (root / "etc/nixos/pre-nixos-auto-install-ip.nix").read_text()
    assert 'systemd.services."pre-nixos-auto-install-ip"' in module_content
    assert 'description = "Announce LAN IPv4 on boot";' in module_content
    assert 'BROADCAST_CONSOLE_CMD = broadcastConsoleCmd;' in module_content
    assert '++ preNixosPath;' in module_content
    assert 'systemd.services."pre-nixos-network-report"' in module_content
    assert "report_dir=\"''${PRE_NIXOS_STATE_DIR:-/run/pre-nixos}\"" in module_content
    assert "ip -br link" in module_content
    assert "networkctl status --all" in module_content

    announce_script = (root / "etc/nixos/pre-nixos-announce-lan-ip.sh").read_text()
    assert "preferred interface" in announce_script

    network_dir = root / "etc/systemd/network"
    assert (network_dir / "10-lan.link").read_text() == lan.rename_rule.read_text()
    assert (network_dir / "20-lan.network").read_text() == lan.network_unit.read_text()

    start_stamp = start_time.strftime("%Y-%m-%d %H:%M:%SZ")
    completion_stamp = completion_time.strftime("%Y-%m-%d %H:%M:%SZ")
    assert broadcast_messages == [
        f"Starting automatic NixOS installation at {start_stamp} UTC.",
        f"Automatic NixOS installation completed at {completion_stamp} UTC.",
    ]

    issue_text = (root / "etc/issue").read_text()
    assert "Automatic NixOS installation completed by pre-nixos." in issue_text
    assert f"Installation timestamp (UTC): {completion_stamp}" in issue_text

    status_file = (tmp_path / "status" / "auto-install-status")
    status_text = status_file.read_text()
    assert "STATE=success" in status_text
    assert f"COMPLETED_AT={completion_stamp}" in status_text
    assert "REBOOT=requested" in status_text
    assert "CONSOLE_WRITTEN=true" in status_text
    assert f"ISSUE_PATH={root}/etc/issue" in status_text


def test_auto_install_static_network_skips_dhcp_unit(
    tmp_path, monkeypatch, broadcast_messages
):
    root = tmp_path / "mnt"
    (root / "etc").mkdir(parents=True)
    lan = _make_lan(tmp_path)

    commands: list[list[str]] = []

    start_time = datetime(2025, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
    completion_time = datetime(2025, 1, 2, 3, 14, 5, tzinfo=timezone.utc)

    class FakeDateTime:
        calls = 0

        @classmethod
        def now(cls, tz=None):
            cls.calls += 1
            return start_time if cls.calls == 1 else completion_time

    def fake_run(cmd, check=False):
        commands.append(cmd)

        class Result:
            returncode = 0

        if cmd[0] == "nixos-generate-config":
            config_dir = root / "etc/nixos"
            config_dir.mkdir(parents=True, exist_ok=True)
            (config_dir / "configuration.nix").write_text("{\n}\n", encoding="utf-8")
            (config_dir / "hardware-configuration.nix").write_text(
                "{\n"
                "  fileSystems.\"/\" = { device = \"/dev/disk/by-uuid/OLD\"; };\n"
                "  swapDevices = [ { device = \"/dev/disk/by-uuid/OLD-SWAP\"; } ];\n"
                "  networking.useDHCP = lib.mkDefault true;\n"
                "}\n",
                encoding="utf-8",
            )
        return Result()

    monkeypatch.setattr(install.subprocess, "run", fake_run)
    monkeypatch.setenv("PRE_NIXOS_EXEC", "1")
    monkeypatch.setattr(install, "datetime", FakeDateTime)
    monkeypatch.setattr(
        install,
        "_read_kernel_cmdline_tokens",
        lambda: ("console=ttyS0,115200n8", "console=tty0"),
    )

    reboot_called: list[bool] = []

    def fake_reboot() -> bool:
        reboot_called.append(True)
        return True

    monkeypatch.setattr(install, "_request_reboot", fake_reboot)

    install_network = install.build_install_network_config(
        "192.0.2.10", "255.255.255.0", "192.0.2.1"
    )

    result = install.auto_install(
        lan,
        _sample_storage_plan(),
        root_path=root,
        status_dir=tmp_path / "status",
        install_network=install_network,
    )

    assert result.status == "success"
    assert commands == [
        ["nixos-generate-config", "--root", str(root)],
        ["nixos-install", "--root", str(root), "--no-root-passwd"],
    ]
    assert reboot_called == [True]

    network_dir = root / "etc/systemd/network"
    assert (network_dir / "10-lan.link").exists()
    assert not (network_dir / "20-lan.network").exists()

    content = (root / "etc/nixos/configuration.nix").read_text()
    assert 'networkConfig.DHCP = "no";' in content
    assert 'networkConfig.Address = [ "192.0.2.10/24" ];' in content
    assert 'networkConfig.Gateway = "192.0.2.1";' in content


def test_inject_configuration_prefers_mac_matches(tmp_path):
    root = tmp_path / "mnt"
    lan = _make_lan(tmp_path, original_name="lan")
    install._inject_configuration(
        root,
        lan.authorized_key.read_text(),
        lan,
        _sample_storage_plan(),
    )
    content = (root / "etc/nixos/configuration.nix").read_text()
    assert 'matchConfig.MACAddress = "00:11:22:33:44:55";' in content
    assert 'matchConfig.Name = "lan";' not in content
    assert 'matchConfig.OriginalName' not in content


def test_inject_configuration_static_network(tmp_path):
    root = tmp_path / "mnt"
    lan = _make_lan(tmp_path, original_name="lan")
    network_config = install.build_install_network_config(
        "192.0.2.10", "255.255.255.0", "192.0.2.1"
    )
    install._inject_configuration(
        root,
        lan.authorized_key.read_text(),
        lan,
        _sample_storage_plan(),
        network_config,
    )
    content = (root / "etc/nixos/configuration.nix").read_text()
    assert 'networking.interfaces.lan = {' in content
    assert 'useDHCP = false;' in content
    assert 'ipv4.addresses = [ { address = "192.0.2.10"; prefixLength = 24; } ];' in content
    assert 'networkConfig.DHCP = "no";' in content
    assert 'networkConfig.Address = [ "192.0.2.10/24" ];' in content
    assert 'networkConfig.Gateway = "192.0.2.1";' in content
    assert "  networking.defaultGateway = {" in content
    assert ' address = "192.0.2.1";' in content
    assert ' interface = "lan";' in content
    assert " };" in content
    assert 'networkConfig.DHCP = "yes";' not in content


def test_build_install_network_config_validates_inputs():
    with pytest.raises(ValueError):
        install.build_install_network_config("192.0.2.10", "255.0.0", "192.0.2.1")


def test_build_install_network_config_with_defaulted_values(monkeypatch):
    monkeypatch.setattr(
        install.network,
        "get_ipv4_details",
        lambda iface="lan": install.network.IPv4Details(
            address="192.0.2.10",
            netmask="255.255.255.0",
            prefix_length=24,
            gateway="192.0.2.1",
        ),
    )

    config = install.build_install_network_config_with_defaults("192.0.2.50")

    assert config.netmask == "255.255.255.0"
    assert config.gateway == "192.0.2.1"
    assert config.prefix_length == 24


def test_build_install_network_config_with_defaults_requires_values(monkeypatch):
    monkeypatch.setattr(install.network, "get_ipv4_details", lambda iface="lan": None)

    with pytest.raises(ValueError):
        install.build_install_network_config_with_defaults("192.0.2.50")


def test_auto_install_missing_plan_fails(tmp_path, monkeypatch, broadcast_messages):
    root = tmp_path / "mnt"
    (root / "etc").mkdir(parents=True)
    lan = _make_lan(tmp_path)

    monkeypatch.setenv("PRE_NIXOS_EXEC", "1")

    result = install.auto_install(
        lan,
        None,
        root_path=root,
        status_dir=tmp_path / "status",
    )

    assert result.status == "failed"
    assert result.reason == "missing-storage-plan"
    status_text = (tmp_path / "status" / "auto-install-status").read_text()
    assert "STATE=failed" in status_text
    assert "REASON=missing-storage-plan" in status_text
    assert broadcast_messages == []


def test_auto_install_failure_returns_failed(tmp_path, monkeypatch, broadcast_messages):
    root = tmp_path / "mnt"
    (root / "etc").mkdir(parents=True)
    lan = _make_lan(tmp_path)

    start_time = datetime(2025, 2, 3, 4, 5, 6, tzinfo=timezone.utc)

    class FakeDateTime:
        @classmethod
        def now(cls, tz=None):
            return start_time

    def fake_run(cmd, check=False):
        class Result:
            returncode = 0 if cmd[0] == "nixos-generate-config" else 1

        if cmd[0] == "nixos-generate-config":
            config_dir = root / "etc/nixos"
            config_dir.mkdir(parents=True, exist_ok=True)
            (config_dir / "configuration.nix").write_text("{\n}\n", encoding="utf-8")
        return Result()

    monkeypatch.setattr(install.subprocess, "run", fake_run)
    monkeypatch.setenv("PRE_NIXOS_EXEC", "1")
    monkeypatch.setattr(install, "datetime", FakeDateTime)
    monkeypatch.setattr(
        install,
        "_read_kernel_cmdline_tokens",
        lambda: ("console=ttyS0,115200n8", "console=tty0"),
    )

    result = install.auto_install(
        lan,
        _sample_storage_plan(),
        root_path=root,
        status_dir=tmp_path / "status",
    )
    assert result.status == "failed"
    assert result.reason == "nixos-install"
    status_text = (tmp_path / "status" / "auto-install-status").read_text()
    assert "STATE=failed" in status_text
    assert "REASON=nixos-install" in status_text
    start_stamp = start_time.strftime("%Y-%m-%d %H:%M:%SZ")
    assert broadcast_messages == [
        f"Starting automatic NixOS installation at {start_stamp} UTC.",
    ]


def test_auto_install_dry_run_skips(monkeypatch, tmp_path, broadcast_messages):
    lan = _make_lan(tmp_path)
    monkeypatch.setenv("PRE_NIXOS_EXEC", "1")

    called = []

    def fail_run(*args, **kwargs):
        called.append(True)
        raise AssertionError("subprocess.run should not be called in dry-run mode")

    monkeypatch.setattr(install.subprocess, "run", fail_run)
    result = install.auto_install(
        lan,
        _sample_storage_plan(),
        dry_run=True,
        root_path=tmp_path / "mnt",
        status_dir=tmp_path / "status",
    )
    assert result.status == "skipped"
    assert result.reason == "dry-run"
    assert called == []
    status_text = (tmp_path / "status" / "auto-install-status").read_text()
    assert status_text.startswith("STATE=skipped\nREASON=dry-run")
    assert broadcast_messages == []


def test_select_console_kernel_params_defaults_to_display_primary() -> None:
    params = install._select_console_kernel_params(())
    assert params == ["console=ttyS0,115200n8", "console=tty0"]


def test_select_console_kernel_params_uses_serial_primary_when_selected() -> None:
    params = install._select_console_kernel_params(
        ("foo=bar", "console=ttyS0,115200n8", "console=tty0", "console=ttyS0,115200n8")
    )
    assert params == ["console=tty0", "console=ttyS0,115200n8"]


def test_inject_configuration_uses_serial_last_when_serial_is_primary(tmp_path) -> None:
    root = tmp_path / "mnt"
    lan = _make_lan(tmp_path, original_name="lan")
    install._inject_configuration(
        root,
        lan.authorized_key.read_text(),
        lan,
        _sample_storage_plan(),
        console_kernel_params=("console=tty0", "console=ttyS0,115200n8"),
    )
    content = (root / "etc/nixos/configuration.nix").read_text()
    assert 'boot.kernelParams = [ "console=tty0" "console=ttyS0,115200n8" ];' in content


_GENERATE_CONFIG_FIXTURES = Path(__file__).parent / "fixtures" / "nixos-generate-config"


def _fake_install_run(
    root: Path,
    commands: list[list[str]],
    *,
    expect_firmware: bool = True,
    generated: str | None = None,
):
    """``generated``: a variant under ``fixtures/nixos-generate-config`` whose real
    output the fake ``nixos-generate-config`` writes (default: an empty set)."""

    def fake_run(cmd, check=False):
        commands.append(cmd)

        class Result:
            returncode = 0

        if cmd[0] == "nixos-generate-config":
            config_dir = root / "etc/nixos"
            config_dir.mkdir(parents=True, exist_ok=True)
            if generated is None:
                (config_dir / "configuration.nix").write_text("{\n}\n", encoding="utf-8")
            else:
                for name in ("configuration.nix", "hardware-configuration.nix"):
                    source = _GENERATE_CONFIG_FIXTURES / generated / name
                    (config_dir / name).write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
        if cmd[0] == "nixos-install" and expect_firmware:
            # The firmware is on /boot before nixos-install writes extlinux.conf.
            assert (root / "boot" / "u-boot-rpi4.bin").read_bytes() == b"uboot-nvme"
        return Result()

    return fake_run


def _rpi_environment(tmp_path: Path, monkeypatch) -> Path:
    firmware = tmp_path / "firmware"
    firmware.mkdir()
    for name, data in {
        "config.txt": b"[pi4]\nkernel=u-boot-rpi4.bin\n",
        "start4.elf": b"start4",
        "u-boot-rpi4.bin": b"uboot-nvme",
    }.items():
        (firmware / name).write_bytes(data)
    monkeypatch.setenv("PRE_NIXOS_EXEC", "1")
    monkeypatch.setenv("PRE_NIXOS_INSTALLED_BOOT", "rpi4-uboot-extlinux")
    monkeypatch.setenv("PRE_NIXOS_RPI_FIRMWARE", str(firmware))
    monkeypatch.setattr(install, "_request_reboot", lambda: False)
    # R-B2: the user's CM4 (NVMe first) with an NVMe target.
    monkeypatch.setattr(install.boot_order, "read_current", lambda: install.boot_order.Known(0xF2516, "test"))
    monkeypatch.setattr(install.boot_order, "_disk_of_mount", lambda path: "nvme0n1")
    return firmware


def test_auto_install_rpi_puts_firmware_on_boot_and_enables_extlinux(
    tmp_path, monkeypatch, broadcast_messages
):
    """AArch64 plan item 8 (R-B1): Pi firmware + U-Boot on /boot, extlinux loader."""

    root = tmp_path / "mnt"
    (root / "boot").mkdir(parents=True)
    (root / "etc").mkdir()  # _is_mount_ready's test-only fallback
    _rpi_environment(tmp_path, monkeypatch)
    monkeypatch.setattr(install.boot_platform, "_is_mount", lambda path: path == root / "boot")
    commands: list[list[str]] = []
    monkeypatch.setattr(install.subprocess, "run", _fake_install_run(root, commands))

    result = install.auto_install(
        _make_lan(tmp_path), _sample_storage_plan(), root_path=root, status_dir=tmp_path / "status"
    )

    assert result.status == "success", result
    assert [cmd[0] for cmd in commands] == ["nixos-generate-config", "nixos-install"]
    content = (root / "etc/nixos/configuration.nix").read_text()
    assert "boot.loader" not in content  # in pre-nixos-boot.nix (#320)
    assert "./pre-nixos-boot.nix" in content
    module = (root / "etc/nixos/pre-nixos-boot.nix").read_text()
    assert "boot.loader.generic-extlinux-compatible.enable = lib.mkForce true;" in module


_TOP_LEVEL_ASSIGNMENT = re.compile(r"^  (?P<path>[A-Za-z0-9_.\"-]+)\s*=")


def _top_level_paths(text: str) -> list[str]:
    """Attribute paths assigned at the top level of a generated NixOS module
    (two-space indentation, as nixos-generate-config and the managed block use)."""

    return [m.group("path") for m in map(_TOP_LEVEL_ASSIGNMENT.match, text.splitlines()) if m]


@pytest.mark.parametrize("generated", ["extlinux", "grub", "efi"])
def test_auto_install_rpi_config_defines_no_attribute_twice(
    tmp_path, monkeypatch, broadcast_messages, generated
):
    """trbarbour/NixOS-boot-image#320: on the CM4, nixos-generate-config itself
    writes boot.loader.grub.enable (the SD image has /boot/extlinux), and a
    second definition in the same file is a Nix parse error."""

    root = tmp_path / "mnt"
    (root / "boot").mkdir(parents=True)
    (root / "etc").mkdir()  # _is_mount_ready's test-only fallback
    _rpi_environment(tmp_path, monkeypatch)
    monkeypatch.setattr(install.boot_platform, "_is_mount", lambda path: path == root / "boot")
    commands: list[list[str]] = []
    monkeypatch.setattr(
        install.subprocess, "run", _fake_install_run(root, commands, generated=generated)
    )

    result = install.auto_install(
        _make_lan(tmp_path), _sample_storage_plan(), root_path=root, status_dir=tmp_path / "status"
    )

    assert result.status == "success", result
    config_dir = root / "etc/nixos"
    paths = _top_level_paths((config_dir / "configuration.nix").read_text())
    duplicates = sorted({path for path in paths if paths.count(path) > 1})
    assert duplicates == []
    # The loader is declared in its own module, imported from configuration.nix.
    module = config_dir / "pre-nixos-boot.nix"
    template = Path(install.__file__).parent / "templates" / "boot-rpi4-uboot-extlinux.nix"
    assert module.read_text() == template.read_text()
    assert "./pre-nixos-boot.nix" in (config_dir / "configuration.nix").read_text()
    # #326: NetworkManager (enabled by the generator) is switched off in a
    # module of its own, so networkd is the only DHCP client on lan.
    network = config_dir / "pre-nixos-network.nix"
    network_template = Path(install.__file__).parent / "templates" / "network-networkd.nix"
    assert network.read_text() == network_template.read_text()
    assert "networking.networkmanager.enable = lib.mkForce false;" in network.read_text()
    assert "./pre-nixos-network.nix" in (config_dir / "configuration.nix").read_text()


def test_auto_install_rpi_fails_before_nixos_install_without_mounted_boot(
    tmp_path, monkeypatch, broadcast_messages
):
    root = tmp_path / "mnt"
    (root / "boot").mkdir(parents=True)
    (root / "etc").mkdir()  # _is_mount_ready's test-only fallback
    _rpi_environment(tmp_path, monkeypatch)
    monkeypatch.setattr(install.boot_platform, "_is_mount", lambda path: False)
    commands: list[list[str]] = []
    monkeypatch.setattr(install.subprocess, "run", _fake_install_run(root, commands))

    result = install.auto_install(
        _make_lan(tmp_path), _sample_storage_plan(), root_path=root, status_dir=tmp_path / "status"
    )

    assert (result.status, result.reason) == ("failed", "boot-files")
    assert [cmd[0] for cmd in commands] == ["nixos-generate-config"]


def test_auto_install_rejects_an_unknown_installed_boot(tmp_path, monkeypatch, broadcast_messages):
    monkeypatch.setenv("PRE_NIXOS_EXEC", "1")
    monkeypatch.setenv("PRE_NIXOS_INSTALLED_BOOT", "uefi-shim")
    commands: list[list[str]] = []
    monkeypatch.setattr(install.subprocess, "run", _fake_install_run(tmp_path / "mnt", commands))

    result = install.auto_install(
        _make_lan(tmp_path),
        _sample_storage_plan(),
        root_path=tmp_path / "mnt",
        status_dir=tmp_path / "status",
    )

    assert (result.status, result.reason) == ("failed", "installed-boot-config")
    assert commands == []


def test_auto_install_rpi_refuses_when_the_card_boots_first(tmp_path, monkeypatch, broadcast_messages):
    """R-B2 (AArch64 plan item 9): stop before nixos-generate-config, and say why."""

    root = tmp_path / "mnt"
    (root / "boot").mkdir(parents=True)
    (root / "etc").mkdir()  # _is_mount_ready's test-only fallback
    _rpi_environment(tmp_path, monkeypatch)
    monkeypatch.setattr(install.boot_order, "read_current", lambda: install.boot_order.Known(0xF41, "test"))
    commands: list[list[str]] = []
    monkeypatch.setattr(install.subprocess, "run", _fake_install_run(root, commands))

    result = install.auto_install(
        _make_lan(tmp_path), _sample_storage_plan(), root_path=root, status_dir=tmp_path / "status"
    )

    assert (result.status, result.reason) == ("failed", "boot-order")
    assert commands == []
    assert any("BOOT_ORDER=0xf416" in message for message in broadcast_messages)
    status = (tmp_path / "status" / "auto-install-status").read_text()
    assert "REASON=boot-order" in status and "MESSAGE=Refusing to install" in status


def test_auto_install_x86_does_not_check_the_boot_order(tmp_path, monkeypatch, broadcast_messages):
    root = tmp_path / "mnt"
    (root / "etc").mkdir(parents=True)
    monkeypatch.setenv("PRE_NIXOS_EXEC", "1")
    monkeypatch.setattr(install, "_request_reboot", lambda: False)

    def must_not_run(*_args, **_kwargs):
        raise AssertionError("boot order checked on nixos-default")

    monkeypatch.setattr(install.boot_order, "verify_for_install", must_not_run)
    monkeypatch.setattr(
        install.subprocess, "run", _fake_install_run(root, [], expect_firmware=False)
    )
    result = install.auto_install(
        _make_lan(tmp_path), _sample_storage_plan(), root_path=root, status_dir=tmp_path / "status"
    )
    assert result.status == "success", result


def test_auto_install_refuses_bios_before_running_anything(tmp_path, monkeypatch, broadcast_messages):
    """Task queue item 33: on a legacy-BIOS x86 machine, nixos-install fails
    ("You must set the option 'boot.loader.grub.devices'"), so refuse first."""

    monkeypatch.setattr(install.boot_platform, "_SYSFS_EFI", tmp_path / "no-efi")
    monkeypatch.setenv("PRE_NIXOS_EXEC", "1")
    commands: list[list[str]] = []
    root = tmp_path / "mnt"
    monkeypatch.setattr(install.subprocess, "run", _fake_install_run(root, commands, expect_firmware=False))

    result = install.auto_install(
        _make_lan(tmp_path), _sample_storage_plan(), root_path=root, status_dir=tmp_path / "status"
    )

    assert (result.status, result.reason) == ("failed", "bios-unsupported")
    assert commands == []
    status = (tmp_path / "status" / "auto-install-status").read_text()
    assert "REASON=bios-unsupported" in status
    assert any("legacy BIOS" in message for message in broadcast_messages)
