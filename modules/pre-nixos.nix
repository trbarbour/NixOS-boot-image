{ config, lib, pkgs, ... }:
let
  cfg = config.services.pre-nixos;
  # ``pre-nixos`` only executes disk and network commands when PRE_NIXOS_EXEC is
  # set.  Propagate it to login shells for the TUI and to the systemd unit so the
  # boot-time invocation can configure networking.  ``disko`` relies on
  # ``nixpkgs`` being available on ``$NIX_PATH`` when executing the generated
  # configuration, so expose the evaluated nixpkgs path alongside the execution
  # flag.
  preNixosExecEnv = {
    PRE_NIXOS_EXEC = "1";
    PRE_NIXOS_NIXPKGS = "${pkgs.path}";
  };
  preNixosServiceEnv = preNixosExecEnv // {
    NIX_PATH = "nixpkgs=${pkgs.path}";
  };
  preNixosLoginNotice = builtins.readFile ./pre-nixos/login-notice.sh;
  preNixosServiceScript = import ./pre-nixos/service-script.nix { inherit pkgs; };
in {
  options.services.pre-nixos.enable = lib.mkEnableOption "run pre-nixos planning tool";

  config = lib.mkIf cfg.enable {
    environment.systemPackages = [ pkgs.pre-nixos pkgs.disko pkgs.util-linux pkgs.minicom ];
    environment.sessionVariables = lib.mkMerge [
      preNixosExecEnv
      { NIX_PATH = lib.mkForce "nixpkgs=${pkgs.path}"; }
    ];
    environment.interactiveShellInit = preNixosLoginNotice;
    systemd.network.enable = true;
    networking.useNetworkd = lib.mkForce true;
    networking.useDHCP = lib.mkForce false;
    networking.networkmanager.enable = lib.mkForce false;
    boot.kernelParams = [ "console=ttyS0,115200n8" "console=tty0" ];
    boot.loader.grub.memtest86.enable = true;
    boot.loader.grub.extraConfig = ''
      serial --speed=115200 --unit=0 --word=8 --parity=no --stop=1
      terminal_input serial console
      terminal_output serial console
    '';
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
  };
}
