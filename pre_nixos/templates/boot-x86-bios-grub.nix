# Written by pre-nixos: the installed x86 system boots in legacy BIOS mode,
# through GRUB (i386-pc) on the disks the BIOS can boot (reqs R-B1, R-B4;
# plans/2026-10-31T010024Z-x86-bios-support-plan.md, D3, D4, D6).
#
# A module of its own, not lines in configuration.nix: nixos-generate-config
# also sets boot.loader.grub.enable there, and an attribute defined twice in
# one file is a parse error (trbarbour/NixOS-boot-image#320).  mkForce makes
# this declaration win over whatever the generator guessed.
{ lib, ... }:
{
  boot.loader.grub.enable = lib.mkForce true;
  boot.loader.grub.efiSupport = lib.mkForce false;
  boot.loader.efi.canTouchEfiVariables = lib.mkForce false;
  boot.loader.systemd-boot.enable = lib.mkForce false;

  # GRUB's core image goes into each disk's BIOS boot partition; every copy
  # loads the kernels from /boot, the first disk's ESP (plan D3).
  boot.loader.grub.devices = @BIOS_BOOT_DEVICES@;
}
