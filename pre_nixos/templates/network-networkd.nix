# Written by pre-nixos: the installed system's only network manager is
# systemd-networkd, which the managed block in configuration.nix configures
# (DHCP or the install's static address on lan).
#
# nixos-generate-config enables NetworkManager in every configuration.nix it
# writes; with both running, lan holds two DHCP leases
# (trbarbour/NixOS-boot-image#326).  A module of its own, because a second
# definition of that attribute in configuration.nix is a parse error (#320).
{ lib, ... }:
{
  networking.networkmanager.enable = lib.mkForce false;
}
