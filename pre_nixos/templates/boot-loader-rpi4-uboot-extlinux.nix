# Written by pre-nixos: the installed Raspberry Pi 4 / CM4 boots
#   Pi firmware -> NVMe-capable U-Boot -> /boot/extlinux/extlinux.conf
# (plans/2026-10-19T132321Z-aarch64-item8-installed-bootloader-design.md, D3).
#
# A module of its own, not lines in configuration.nix: nixos-generate-config
# also sets some of these there, and an attribute defined twice in one file is
# a parse error (trbarbour/NixOS-boot-image#320).  Across modules the
# definitions merge, and mkForce makes the image's declaration win over
# whichever loader nixos-generate-config guessed from the running system.
{ lib, ... }:
{
  boot.loader.grub.enable = lib.mkForce false;
  boot.loader.systemd-boot.enable = lib.mkForce false;
  boot.loader.generic-extlinux-compatible.enable = lib.mkForce true;
}
