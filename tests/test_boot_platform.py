"""The installed system's boot chain (AArch64 plan item 8; R-B1).

Design: plans/2026-10-19T132321Z-aarch64-item8-installed-bootloader-design.md.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from pre_nixos import boot_order, boot_platform
from pre_nixos.boot_platform import BootSetup, InstalledBoot


def _firmware(tmp_path: Path) -> Path:
    source = tmp_path / "firmware"
    (source / "overlays").mkdir(parents=True)
    (source / "config.txt").write_text("[pi4]\nkernel=u-boot-rpi4.bin\n")
    (source / "start4.elf").write_bytes(b"start4")
    (source / "u-boot-rpi4.bin").write_bytes(b"uboot-nvme")
    (source / "overlays" / "x.dtbo").write_bytes(b"dtbo")
    return source


def _rpi(source: Path) -> BootSetup:
    return BootSetup(InstalledBoot.RPI4_UBOOT_EXTLINUX, source)


def test_absent_declaration_means_nixos_default() -> None:
    assert boot_platform.boot_setup_from_environment({}) == boot_platform.NIXOS_DEFAULT_SETUP


def test_rpi_declaration_is_parsed(tmp_path: Path) -> None:
    setup = boot_platform.boot_setup_from_environment(
        {
            "PRE_NIXOS_INSTALLED_BOOT": "rpi4-uboot-extlinux",
            "PRE_NIXOS_RPI_FIRMWARE": str(tmp_path),
        }
    )
    assert setup == _rpi(tmp_path)


@pytest.mark.parametrize(
    "env",
    [
        {"PRE_NIXOS_INSTALLED_BOOT": "grub"},
        {"PRE_NIXOS_INSTALLED_BOOT": "rpi4-uboot-extlinux"},
        {"PRE_NIXOS_INSTALLED_BOOT": "nixos-default", "PRE_NIXOS_RPI_FIRMWARE": "/x"},
    ],
)
def test_invalid_declarations_are_rejected(env: dict[str, str]) -> None:
    with pytest.raises(ValueError):
        boot_platform.boot_setup_from_environment(env)


def test_nixos_default_keeps_the_grub_serial_lines() -> None:
    lines = boot_platform.loader_config_lines(boot_platform.NIXOS_DEFAULT_SETUP)
    assert "  boot.loader.grub.extraConfig = ''" in lines
    assert not any("extlinux" in line for line in lines)


def test_rpi_declares_its_loader_in_a_module_not_the_managed_block(tmp_path: Path) -> None:
    """#320: the generator also sets these, so they cannot be lines in configuration.nix."""

    assert boot_platform.loader_config_lines(_rpi(tmp_path)) == []
    name = boot_platform.loader_module_template(_rpi(tmp_path))
    assert name is not None
    text = (Path(boot_platform.__file__).parent / "templates" / name).read_text()
    for line in (
        "boot.loader.grub.enable = lib.mkForce false;",
        "boot.loader.systemd-boot.enable = lib.mkForce false;",
        "boot.loader.generic-extlinux-compatible.enable = lib.mkForce true;",
        # #323: the NVMe root is behind the PCIe bridge, a module.
        'boot.initrd.availableKernelModules = [ "pcie-brcmstb" "nvme" ];',
    ):
        assert line in text


def test_nixos_default_has_no_loader_module() -> None:
    assert boot_platform.loader_module_template(boot_platform.NIXOS_DEFAULT_SETUP) is None


def test_nixos_default_copies_nothing(tmp_path: Path) -> None:
    copied = boot_platform.install_boot_files(
        boot_platform.NIXOS_DEFAULT_SETUP, tmp_path, is_mount=lambda _: False
    )
    assert copied == []
    assert list(tmp_path.iterdir()) == []


def test_rpi_copies_the_firmware_tree_to_boot(tmp_path: Path) -> None:
    source = _firmware(tmp_path)
    root = tmp_path / "mnt"
    (root / "boot" / "extlinux").mkdir(parents=True)
    copied = boot_platform.install_boot_files(_rpi(source), root, is_mount=lambda _: True)

    boot = root / "boot"
    assert sorted(p.relative_to(boot).as_posix() for p in copied) == [
        "config.txt",
        "overlays/x.dtbo",
        "start4.elf",
        "u-boot-rpi4.bin",
    ]
    assert (boot / "u-boot-rpi4.bin").read_bytes() == b"uboot-nvme"
    assert (boot / "extlinux").is_dir()  # what nixos-install manages is left alone


def test_rpi_refuses_an_unmounted_boot(tmp_path: Path) -> None:
    root = tmp_path / "mnt"
    (root / "boot").mkdir(parents=True)
    with pytest.raises(RuntimeError, match="not a mounted filesystem"):
        boot_platform.install_boot_files(
            _rpi(_firmware(tmp_path)), root, is_mount=lambda _: False
        )
    assert list((root / "boot").iterdir()) == []


def test_rpi_refuses_incomplete_firmware(tmp_path: Path) -> None:
    source = _firmware(tmp_path)
    (source / "start4.elf").unlink()
    with pytest.raises(RuntimeError, match="lacks start4.elf"):
        boot_platform.install_boot_files(_rpi(source), tmp_path, is_mount=lambda _: True)


def _good_boot_order(monkeypatch) -> None:
    """The user's CM4 (EEPROM 2022-11-04): NVMe first, NVMe target."""

    monkeypatch.setattr(boot_order, "read_current", lambda: boot_order.Known(0xF2516, "test"))
    monkeypatch.setattr(boot_order, "_disk_of_mount", lambda path: "nvme0n1")


def test_cli_copies_for_a_manual_install(tmp_path: Path, monkeypatch, capsys) -> None:
    _good_boot_order(monkeypatch)
    source = _firmware(tmp_path)
    root = tmp_path / "mnt"
    (root / "boot").mkdir(parents=True)
    monkeypatch.setenv("PRE_NIXOS_INSTALLED_BOOT", "rpi4-uboot-extlinux")
    monkeypatch.setenv("PRE_NIXOS_RPI_FIRMWARE", str(source))
    monkeypatch.setattr(boot_platform, "_is_mount", lambda path: path == root / "boot")

    assert boot_platform.main(["--root", str(root)]) == 0
    assert "copied 4 files" in capsys.readouterr().out
    assert (root / "boot" / "u-boot-rpi4.bin").read_bytes() == b"uboot-nvme"


def test_cli_fails_on_an_unmounted_boot(tmp_path: Path, monkeypatch, capsys) -> None:
    _good_boot_order(monkeypatch)
    monkeypatch.setenv("PRE_NIXOS_INSTALLED_BOOT", "rpi4-uboot-extlinux")
    monkeypatch.setenv("PRE_NIXOS_RPI_FIRMWARE", str(_firmware(tmp_path)))
    monkeypatch.setattr(boot_platform, "_is_mount", lambda path: False)

    assert boot_platform.main(["--root", str(tmp_path / "mnt")]) == 1
    assert "not a mounted filesystem" in capsys.readouterr().err


def test_cli_refuses_a_boot_order_that_boots_the_card_first(tmp_path: Path, monkeypatch, capsys) -> None:
    """R-B2: exit 2, nothing copied; --ignore-boot-order overrides."""

    source = _firmware(tmp_path)
    root = tmp_path / "mnt"
    (root / "boot").mkdir(parents=True)
    monkeypatch.setenv("PRE_NIXOS_INSTALLED_BOOT", "rpi4-uboot-extlinux")
    monkeypatch.setenv("PRE_NIXOS_RPI_FIRMWARE", str(source))
    monkeypatch.setattr(boot_platform, "_is_mount", lambda path: path == root / "boot")
    monkeypatch.setattr(boot_order, "read_current", lambda: boot_order.Known(0xF41, "test"))
    monkeypatch.setattr(boot_order, "_disk_of_mount", lambda path: "nvme0n1")

    assert boot_platform.main(["--root", str(root)]) == 2
    assert "BOOT_ORDER=0xf416" in capsys.readouterr().err
    assert list((root / "boot").iterdir()) == []

    assert boot_platform.main(["--root", str(root), "--ignore-boot-order"]) == 0


def _bios(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(boot_platform, "_SYSFS_EFI", tmp_path / "no-efi")


def test_x86_booted_in_bios_mode_is_refused(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Task queue item 33 (R-B1: x86 installs need UEFI): refuse rather than
    provision disks that nixos-install cannot then make bootable."""

    _bios(monkeypatch, tmp_path)
    message = boot_platform.legacy_bios_refusal(boot_platform.NIXOS_DEFAULT_SETUP)
    assert message is not None
    assert message.startswith("Refusing to install: this machine booted in legacy BIOS mode")
    assert "UEFI" in message


def test_x86_booted_in_uefi_mode_is_accepted() -> None:
    # conftest makes /sys/firmware/efi exist.
    assert boot_platform.legacy_bios_refusal(boot_platform.NIXOS_DEFAULT_SETUP) is None


def test_the_pi_has_no_efi_and_is_not_refused(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _bios(monkeypatch, tmp_path)
    assert boot_platform.legacy_bios_refusal(_rpi(_firmware(tmp_path))) is None
