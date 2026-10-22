# Real `nixos-generate-config` output (trbarbour/NixOS-boot-image#320)

Produced 2026-10-22 by the AArch64 image's own generator
(`nixosConfigurations.pre-installer-aarch64.config.system.build.nixos-generate-config`,
nixpkgs 26.05.20261015.26f4107). Its loader section depends on the **running**
system, so each variant was produced in a private mount namespace:

| Directory | Running system had | Loader lines written |
|---|---|---|
| `extlinux/` | `/boot/extlinux` (the SD image, as on the CM4) | `grub.enable = false`, `generic-extlinux-compatible.enable = true` |
| `grub/` | neither | `grub.enable = true` |
| `efi/` | `/sys/firmware/efi/efivars` | `systemd-boot.enable = true`, `efi.canTouchEfiVariables = true` |

`hardware-configuration.nix` is the generator's output for an empty root, so it
describes no real machine. Regenerate these files when nixpkgs changes the template.
