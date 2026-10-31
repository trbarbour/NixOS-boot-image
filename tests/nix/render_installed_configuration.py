"""Render the installed configuration from real nixos-generate-config output.

Used by the flake check ``installed-configuration-parses``
(trbarbour/NixOS-boot-image#320).  Copies ``FIXTURE``'s generator output into
``ROOT/etc/nixos`` and applies pre-nixos's configuration rewrite to it, as
``auto_install`` does on the target after ``nixos-generate-config``.

Usage: render_installed_configuration.py FIXTURE ROOT {nixos-default,rpi4-uboot-extlinux,x86-bios-grub}
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

from pre_nixos import boot_platform, install
from pre_nixos.network import LanConfiguration


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print(__doc__, file=sys.stderr)
        return 2
    fixture, root, kind = Path(argv[0]), Path(argv[1]), boot_platform.InstalledBoot(argv[2])
    config_dir = root / "etc/nixos"
    config_dir.mkdir(parents=True)
    for name in ("configuration.nix", "hardware-configuration.nix"):
        shutil.copyfile(fixture / name, config_dir / name)
    key = root / "key.pub"
    key.write_text("ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAITestKeyOnly test@render\n")
    firmware = root / "firmware" if kind is boot_platform.InstalledBoot.RPI4_UBOOT_EXTLINUX else None
    install._inject_configuration(
        root,
        key.read_text().strip(),
        LanConfiguration(authorized_key=key, mac_address="00:11:22:33:44:55"),
        None,
        console_kernel_params=["console=ttyS0,115200n8"],
        boot_setup=boot_platform.BootSetup(kind, firmware),
        boot_devices=(
            ["/dev/disk/by-id/ata-TEST_DISK_A", "/dev/disk/by-id/ata-TEST_DISK_B"]
            if kind is boot_platform.InstalledBoot.X86_BIOS_GRUB
            else ()
        ),
    )
    install._rewrite_hardware_configuration(root)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
