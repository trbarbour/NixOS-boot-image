{ config, lib, pkgs, ... }:
let
  cfg = config.services.pre-nixos;
  # Site settings (nix/site.nix): set by the flake's mkBootConfiguration from
  # one resolved value, which also builds the package with the same key.
  autoInstallEnabled = cfg.autoInstall;
  autoInstallFlag = if cfg.autoInstall then "1" else "";
  rootKeyEmbedded = cfg.rootKey != null;
  autoInstallNotice =
    if autoInstallEnabled then
      "Automatic installation is enabled; pre-nixos will provision NixOS and reboot into the installed system when finished."
    else
      "Automatic installation is disabled; run pre-nixos to configure networking and start installation.";
  sshNotice =
    if rootKeyEmbedded then
      ''
      SSH access:
        - Use the matching private key for the embedded root SSH key to log in as root.
        - Add additional public keys to /root/.ssh/authorized_keys if needed.
      ''
    else
      ''
      SSH access:
        - No root SSH key is embedded in this image.
        - Set a root password with passwd or add your public key to /root/.ssh/authorized_keys before enabling remote logins.
      '';
  # ``pre-nixos`` only executes disk and network commands when PRE_NIXOS_EXEC is
  # set.  Propagate it to login shells for the TUI and to the systemd unit so the
  # boot-time invocation can configure networking.  ``disko`` relies on
  # ``nixpkgs`` being available on ``$NIX_PATH`` when executing the generated
  # configuration, so expose the evaluated nixpkgs path alongside the execution
  # flag.
  preNixosExecEnv = {
    PRE_NIXOS_EXEC = "1";
    PRE_NIXOS_NIXPKGS = "${pkgs.path}";
    PRE_NIXOS_STATE_DIR = "/run/pre-nixos";
  }
  // lib.optionalAttrs cfg.enable {
    PRE_NIXOS_VERSION = pkgs.pre-nixos.version;
  }
  // lib.optionalAttrs (autoInstallFlag != "") {
    PRE_NIXOS_AUTO_INSTALL = autoInstallFlag;
  }
  # How the installed system boots (AArch64 plan item 8, design D4; R-B1).
  // {
    PRE_NIXOS_INSTALLED_BOOT = cfg.installedBoot;
  }
  // lib.optionalAttrs (cfg.rpiFirmware != null) {
    PRE_NIXOS_RPI_FIRMWARE = "${cfg.rpiFirmware}";
  };
  preNixosServiceEnv = preNixosExecEnv // {
    NIX_PATH = "nixpkgs=${pkgs.path}";
  };
  preNixosLoginNotice = builtins.readFile ./pre-nixos/login-notice.sh;
  preNixosServiceScript = import ./pre-nixos/service-script.nix { inherit pkgs; };
in {
  options.services.pre-nixos.enable = lib.mkEnableOption "run pre-nixos planning tool";
  options.services.pre-nixos.rootKey = lib.mkOption {
    type = lib.types.nullOr lib.types.path;
    default = null;
    description = ''
      The root SSH public key embedded in the image (reqs §2.7).  Set it
      through a site (nix/site.nix), not here: the flake builds the pre-nixos
      package with the same key.
    '';
  };
  options.services.pre-nixos.autoInstall = lib.mkOption {
    type = lib.types.bool;
    default = false;
    description = "Install NixOS automatically once storage and network are ready.";
  };
  options.services.pre-nixos.installedBoot = lib.mkOption {
    type = lib.types.enum [ "nixos-default" "rpi4-uboot-extlinux" ];
    default = "nixos-default";
    description = ''
      How the installed system boots.  "nixos-default" leaves the loader to
      nixos-generate-config (the x86 ISO).  "rpi4-uboot-extlinux" puts the Pi
      firmware and an NVMe-capable U-Boot on the target's FAT /boot and enables
      generic-extlinux-compatible (Raspberry Pi 4 / CM4; AArch64 plan item 8).
    '';
  };
  options.services.pre-nixos.rpiFirmware = lib.mkOption {
    type = lib.types.nullOr lib.types.package;
    default = null;
    description = "Files copied to the target's /boot for rpi4-uboot-extlinux.";
  };

  config = lib.mkIf cfg.enable (lib.mkMerge [ {
    assertions = [ {
      assertion = (cfg.installedBoot == "rpi4-uboot-extlinux") == (cfg.rpiFirmware != null);
      message = "services.pre-nixos.rpiFirmware is required by, and only used with, installedBoot = \"rpi4-uboot-extlinux\".";
    } ];
    environment.systemPackages = [
      pkgs.pre-nixos
      pkgs.disko
      pkgs.util-linux
      pkgs.minicom
      pkgs.nixos-install-tools
      pkgs.nix
    ];
    environment.sessionVariables = lib.mkMerge [
      preNixosExecEnv
      { NIX_PATH = lib.mkForce "nixpkgs=${pkgs.path}"; }
    ];
    environment.interactiveShellInit = preNixosLoginNotice;
    environment.etc."issue".text = lib.mkForce ''
      <<< Welcome to the pre-nixos auto-install boot image (${config.system.nixos.label}, \m) - \l >>>
      ${autoInstallNotice}
      (PRE_NIXOS_AUTO_INSTALL=${autoInstallFlag})
      The "nixos" and "root" accounts have empty passwords for console logins.

      ${sshNotice}

      Networking starts automatically; verify connectivity with ip addr or networkctl.

      Run "nixos-help" for the NixOS manual.
    '';
    systemd.network.enable = true;
    networking.useNetworkd = lib.mkForce true;
    networking.useDHCP = lib.mkForce false;
    networking.networkmanager.enable = lib.mkForce false;
    # The installer modules enable ZFS support; pools are out of scope (reqs
    # §7), so adopt the safer 26.11 default rather than forcing imports.
    boot.zfs.forceImportRoot = false;
    # disko builds its generated script at run time, offline.  The script uses
    # makeBinaryWrapper; until 25.05 the guest could build that hook with the
    # image's pkgs.stdenv, but since 26.05 the installer modules keep only
    # stdenvNoCC.  Ship the hook itself (its closure carries the C compiler it
    # needs).  Guarded by tests/vm/test_disko_offline_closure.py.
    system.extraDependencies = [ pkgs.makeBinaryWrapper ];
    systemd.services.pre-nixos = {
      description = "Pre-NixOS setup";
      wantedBy = [ "multi-user.target" ];
      serviceConfig.Type = "oneshot";
      environment = preNixosServiceEnv;
      path = with pkgs; [
        coreutils
        disko
        dosfstools
        e2fsprogs
        ethtool
        gptfdisk
        iproute2
        lvm2
        mdadm
        nix
        nixos-install-tools
        parted
        systemd
        util-linux
      ];
      script = preNixosServiceScript;
    };

    # Keep OpenSSH disabled until secure_ssh hardens the configuration.
    # ``wantedBy = []`` ensures no other units pull ``sshd`` in automatically,
    # so only ``secure_ssh`` queues the non-blocking restart once the config is safe.
    services.openssh.enable = true;
    systemd.services.sshd.wantedBy = lib.mkForce [ ];
    systemd.services.sshd.after = [ "pre-nixos.service" ];
    systemd.services.sshd.serviceConfig.ExecStart =
      lib.mkForce "${pkgs.openssh}/bin/sshd -D -e -f /etc/ssh/sshd_config";
  }
  # The ISO's boot chain and console settings.  On AArch64 the stock SD image's
  # boot chain and kernel console parameters stay untouched (reqs §2.9 R-P2;
  # AArch64 plan §3.4), checked by the flake check stock-aarch64-boot-settings.
  (lib.mkIf pkgs.stdenv.hostPlatform.isx86 {
    boot.kernelParams = [ "console=ttyS0,115200n8" "console=tty0" ];
    boot.loader.grub.memtest86.enable = true;
    boot.loader.grub.extraConfig = ''
      serial --speed=115200 --unit=0 --word=8 --parity=no --stop=1
      terminal_input serial console
      terminal_output serial console
    '';
  })
  ]);
}
