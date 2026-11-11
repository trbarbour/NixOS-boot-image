# Reference installed systems carried by the x86 image (task queue item 43;
# trbarbour/NixOS-boot-image#340).
#
# The image's store holds only what the installer itself runs.  An installed
# system also needs packages the minimal ISO leaves out (the `info` outputs
# of core tools and texinfo, dhcpcd, openresolv, logrotate, strace, fonts and
# desktop data, and GRUB's Perl modules for install-grub.pl).  Without them,
# nixos-install has to fetch them, or, with no binary cache, rebuild them
# from source down to the compiler bootstrap (notes/*-offline-install-closure.md).
#
# Each reference system is what pre-nixos writes on a target: the
# generator's loader lines (tests/fixtures/nixos-generate-config), pre-nixos's
# boot and network modules (pre_nixos/templates), and the package-relevant
# settings of the block install.py manages in configuration.nix.  A real
# machine's configuration then differs only in configuration files (hardware,
# file systems, keys), which the image's stdenv builds.  Guarded by
# tests/vm/test_offline_install_closure_vm.py, which uses the configuration
# pre-nixos actually wrote.
#
# Installing still needs the network (reqs R-I1, like the stock installer);
# this is for robustness and fewer downloads, not an offline guarantee.
{ pkgs, lib }:
let
  system = pkgs.stdenv.hostPlatform.system;

  evalInstalled = loader:
    (import (pkgs.path + "/nixos/lib/eval-config.nix") {
      inherit system;
      modules = [ loader common ];
    }).config.system.build.toplevel;

  # Mirrors install.py's managed block where it chooses packages or services.
  common = { lib, ... }: {
    imports = [
      ../../pre_nixos/templates/network-networkd.nix
      ../../pre_nixos/templates/pre-nixos-raid-alerts.nix
    ];
    nixpkgs.hostPlatform = lib.mkForce system;
    system.stateVersion = "26.05";
    networking.networkmanager.enable = true; # as the generator writes it; the network module turns it off
    networking.firewall = {
      enable = true;
      allowPing = true;
      allowedTCPPorts = [ 22 ];
    };
    networking.useDHCP = false;
    networking.useNetworkd = true;
    systemd.network.enable = true;
    services.openssh = {
      enable = true;
      settings.PasswordAuthentication = false;
    };
    boot.swraid.enable = true;
    boot.initrd.services.lvm.enable = true;
    nix.settings.experimental-features = [ "nix-command" "flakes" ];
    # Typical hardware-configuration.nix lines on the user's machines.
    boot.initrd.availableKernelModules = [ "ahci" "xhci_pci" "ehci_pci" "usb_storage" "sd_mod" "nvme" "usbhid" ];
    boot.kernelModules = [ "kvm-intel" "kvm-amd" ];
    fileSystems."/" = { device = "/dev/main/slash"; fsType = "ext4"; };
    fileSystems."/boot" = { device = "/dev/disk/by-label/EFI"; fsType = "vfat"; };
    swapDevices = [ { device = "/dev/disk/by-label/swap"; } ];
  };

  # Legacy BIOS (R-B4): the generator's GRUB line plus pre-nixos's BIOS module.
  biosGrub = {
    imports = [
      (builtins.toFile "pre-nixos-boot.nix" (builtins.replaceStrings
        [ "@BIOS_BOOT_DEVICES@" ]
        [ ''[ "/dev/disk/by-id/ata-REFERENCE" ]'' ]
        (builtins.readFile ../../pre_nixos/templates/boot-x86-bios-grub.nix)))
    ];
    boot.loader.grub.enable = true;
  };

  # UEFI: the generator's systemd-boot lines.
  uefiSystemdBoot = {
    boot.loader.systemd-boot.enable = true;
    boot.loader.efi.canTouchEfiVariables = true;
  };
  # Tools that build the configuration derivations a real machine does not
  # share with the references (system-path's post-build steps, the unit
  # directories, the D-Bus configuration).  They are build-time inputs, so
  # the references' runtime closures do not carry them.  Found by computing,
  # against the image's store, what an installed configuration that differs
  # from the references must build (notes/*-offline-install-closure.md).
  builderTools = [
    pkgs.desktop-file-utils
    pkgs.findXMLCatalogs
    pkgs.getconf
    pkgs.libxslt.bin
    pkgs.lndir
    pkgs.texinfo
  ];
in
[ (evalInstalled biosGrub) (evalInstalled uefiSystemdBoot) ] ++ builderTools
