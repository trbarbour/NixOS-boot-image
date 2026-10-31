"""How the installed system boots (AArch64 plan item 8; requirement R-B1).

The boot image declares this at build time (NixOS option
``services.pre-nixos.installedBoot``, exported as ``PRE_NIXOS_INSTALLED_BOOT``)
instead of pre-nixos guessing it at run time (design D4 in
``plans/2026-10-19T132321Z-aarch64-item8-installed-bootloader-design.md``).
The storage layout is the same on every platform (design D1); only the loader
settings and the files placed on the target's FAT ``/boot`` differ.
"""

from __future__ import annotations

import argparse
import enum
import os
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Mapping, Optional, Sequence

from . import boot_order
from .boot_layout import BootLayout

INSTALLED_BOOT_ENV = "PRE_NIXOS_INSTALLED_BOOT"
RPI_FIRMWARE_ENV = "PRE_NIXOS_RPI_FIRMWARE"

# Files the stock Pi firmware chain needs on the boot partition; their presence
# after the copy is a postcondition of ``install_boot_files``.
_RPI_REQUIRED_FILES = ("config.txt", "start4.elf", "u-boot-rpi4.bin")


def _is_mount(path: Path) -> bool:
    return os.path.ismount(path)


# Present only when the running kernel was started by UEFI firmware.
_SYSFS_EFI = Path("/sys/firmware/efi")


class InstalledBoot(enum.Enum):
    """The installed system's boot chain."""

    # nixos-generate-config chooses the loader (the x86 ISO).
    NIXOS_DEFAULT = "nixos-default"
    # Pi 4 / CM4 firmware -> NVMe-capable U-Boot -> extlinux (design §1).
    RPI4_UBOOT_EXTLINUX = "rpi4-uboot-extlinux"
    # An x86 machine booted in legacy BIOS mode -> GRUB (i386-pc) on the disks
    # the BIOS can boot (R-B4).  Never declared by an image: ``effective_setup``
    # derives it at run time from ``NIXOS_DEFAULT`` (plan D1).
    X86_BIOS_GRUB = "x86-bios-grub"


@dataclass(frozen=True)
class BootSetup:
    """The boot chain plus the firmware files it needs."""

    kind: InstalledBoot
    rpi_firmware: Optional[Path] = None

    def __post_init__(self) -> None:
        needs_firmware = self.kind is InstalledBoot.RPI4_UBOOT_EXTLINUX
        if needs_firmware != (self.rpi_firmware is not None):
            raise ValueError(
                f"{self.kind.value} {'requires' if needs_firmware else 'takes no'} "
                f"firmware directory (got {self.rpi_firmware})"
            )


NIXOS_DEFAULT_SETUP = BootSetup(InstalledBoot.NIXOS_DEFAULT)


def boot_setup_from_environment(env: Mapping[str, str] = os.environ) -> BootSetup:
    """Parse the boot image's declaration; raise ``ValueError`` if invalid.

    An absent ``PRE_NIXOS_INSTALLED_BOOT`` means ``nixos-default`` (images built
    before it existed, and development runs).
    """

    raw = env.get(INSTALLED_BOOT_ENV, InstalledBoot.NIXOS_DEFAULT.value)
    try:
        kind = InstalledBoot(raw)
    except ValueError:
        raise ValueError(f"unknown {INSTALLED_BOOT_ENV}={raw!r}") from None
    firmware = env.get(RPI_FIRMWARE_ENV)
    return BootSetup(kind, Path(firmware) if firmware else None)


# Where the loader module goes, beside configuration.nix (which imports it).
LOADER_MODULE_FILE = "pre-nixos-boot.nix"


def effective_setup(setup: BootSetup) -> BootSetup:
    """The boot chain for the machine this runs on (plan D1).

    The ISO boots under UEFI and under legacy BIOS, so an x86 image's
    ``NIXOS_DEFAULT`` becomes ``X86_BIOS_GRUB`` when the kernel was not started
    by UEFI firmware (no ``/sys/firmware/efi``).  The Pi's chain is declared by
    its image and kept.
    """

    if setup.kind is InstalledBoot.NIXOS_DEFAULT and not _SYSFS_EFI.is_dir():
        return BootSetup(InstalledBoot.X86_BIOS_GRUB)
    return setup


def current_setup(env: Mapping[str, str] = os.environ) -> BootSetup:
    """``effective_setup`` of the image's declaration; ``ValueError`` if invalid."""

    return effective_setup(boot_setup_from_environment(env))


def partition_layout(setup: BootSetup) -> BootLayout:
    """The boot partitions the storage plan creates for ``setup`` (D2, D6)."""

    return {
        InstalledBoot.RPI4_UBOOT_EXTLINUX: BootLayout.ESP,
        InstalledBoot.NIXOS_DEFAULT: BootLayout.X86_UEFI,
        InstalledBoot.X86_BIOS_GRUB: BootLayout.X86_BIOS,
    }[setup.kind]


def loader_config_lines(setup: BootSetup) -> list[str]:
    """Return the loader lines for the managed ``configuration.nix`` block.

    Only settings nixos-generate-config never writes may go here: an attribute
    defined twice in one file is a Nix parse error (#320).
    """

    if setup.kind is not InstalledBoot.RPI4_UBOOT_EXTLINUX:
        # x86: GRUB on the serial console too, when GRUB is the loader.
        return [
            "  boot.loader.grub.extraConfig = ''",
            "    serial --speed=115200 --unit=0 --word=8 --parity=no --stop=1",
            "    terminal_input serial console",
            "    terminal_output serial console",
            "  '';",
        ]
    return []


def loader_module_template(setup: BootSetup) -> Optional[str]:
    """The packaged template (under ``pre_nixos/templates``) to install as
    ``LOADER_MODULE_FILE``, or ``None`` when nixos-generate-config's choice stands.

    Design D3: the Pi's loader is declared explicitly, not left to
    nixos-generate-config having seen /boot/extlinux on the running SD image.
    It is a separate module so that its definitions merge with the generator's
    instead of clashing with them (trbarbour/NixOS-boot-image#320).
    """

    if setup.kind is InstalledBoot.RPI4_UBOOT_EXTLINUX:
        return "boot-rpi4-uboot-extlinux.nix"
    if setup.kind is InstalledBoot.X86_BIOS_GRUB:
        # Rendered: BIOS_BOOT_DEVICES_PLACEHOLDER becomes the GRUB target disks.
        return "boot-x86-bios-grub.nix"
    return None


# In boot-x86-bios-grub.nix: replaced by a Nix list of the disks' stable paths.
BIOS_BOOT_DEVICES_PLACEHOLDER = "@BIOS_BOOT_DEVICES@"


def legacy_bios_refusal(setup: BootSetup, boot_disks: Sequence[str]) -> Optional[str]:
    """Why an install on this machine must be refused, or ``None``.

    ``setup`` is the effective setup; ``boot_disks`` are the disks the storage
    plan put the boot partitions on (``plan["boot"]["disks"]``).  Under legacy
    BIOS the plan finds none when every disk is NVMe, which old BIOSes cannot
    boot (R-B4, plan D6); nixos-install would then fail, or install a system
    that cannot boot, after the disks were provisioned (task queue item 33).
    """

    if setup.kind is not InstalledBoot.X86_BIOS_GRUB or boot_disks:
        return None
    return (
        "Refusing to install: this machine booted in legacy BIOS mode, and "
        "none of its disks can be booted by a legacy BIOS (NVMe cannot). Add a "
        "SATA/SAS disk, or reboot the installer in UEFI mode."
    )


def install_boot_files(
    setup: BootSetup,
    root_path: Path,
    *,
    is_mount: Optional[Callable[[Path], bool]] = None,
) -> list[Path]:
    """Copy the firmware files to ``root_path``/boot; return what was copied.

    Raises ``RuntimeError`` when ``/boot`` is not a mounted filesystem (the
    files would land on the root LV, which the Pi firmware cannot read) or when
    the copy did not produce the required files.
    """

    if setup.kind is not InstalledBoot.RPI4_UBOOT_EXTLINUX:
        return []
    assert setup.rpi_firmware is not None  # guaranteed by BootSetup

    source = setup.rpi_firmware
    boot = root_path / "boot"
    if not source.is_dir():
        raise RuntimeError(f"firmware directory {source} is missing")
    missing = [name for name in _RPI_REQUIRED_FILES if not (source / name).is_file()]
    if missing:
        raise RuntimeError(f"firmware directory {source} lacks {', '.join(missing)}")
    if not (is_mount or _is_mount)(boot):
        raise RuntimeError(f"{boot} is not a mounted filesystem")

    copied: list[Path] = []
    for path in sorted(source.rglob("*")):
        destination = boot / path.relative_to(source)
        if path.is_dir():
            destination.mkdir(parents=True, exist_ok=True)
            continue
        # copyfile: store files are read-only; vfat keeps no modes anyway.
        shutil.copyfile(path, destination)
        copied.append(destination)

    for name in _RPI_REQUIRED_FILES:
        written = boot / name
        if not written.is_file() or written.read_bytes() != (source / name).read_bytes():
            raise RuntimeError(f"{written} does not match {source / name}")
    return copied


def main(argv: Optional[Sequence[str]] = None) -> int:
    """``pre-nixos-install-boot-files``: the same step for manual installs."""

    parser = argparse.ArgumentParser(
        description="Copy the declared boot firmware to ROOT/boot (before nixos-install)."
    )
    parser.add_argument("--root", type=Path, default=Path("/mnt"))
    parser.add_argument(
        "--ignore-boot-order",
        action="store_true",
        help="copy even if the EEPROM BOOT_ORDER would boot the SD card first (R-B2)",
    )
    args = parser.parse_args(argv)
    try:
        setup = boot_setup_from_environment()
        if setup.kind is InstalledBoot.RPI4_UBOOT_EXTLINUX and not args.ignore_boot_order:
            verdict = boot_order.verify_for_install(args.root)
            if isinstance(verdict, boot_order.Refused):
                print(boot_order.describe_refusal(verdict), file=sys.stderr)
                return 2
        copied = install_boot_files(setup, args.root)
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"pre-nixos-install-boot-files: {exc}", file=sys.stderr)
        return 1
    print(f"{setup.kind.value}: copied {len(copied)} files to {args.root / 'boot'}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
