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
    PRE_NIXOS_STATE_DIR = "/run/pre-nixos";
  } // lib.optionalAttrs cfg.enable {
    PRE_NIXOS_VERSION = pkgs.pre-nixos.version;
  };
  preNixosServiceEnv = preNixosExecEnv // {
    NIX_PATH = "nixpkgs=${pkgs.path}";
  };
  preNixosLoginNotice = builtins.readFile ./pre-nixos/login-notice.sh;
  preNixosServiceScript = import ./pre-nixos/service-script.nix { inherit pkgs; };
in {
  options.services.pre-nixos.enable = lib.mkEnableOption "run pre-nixos planning tool";

  config = lib.mkIf cfg.enable {
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
      <<< Welcome to NixOS ${config.system.nixos.label} (\m) - \l >>>
      The "nixos" and "root" accounts have empty passwords for console logins.

      SSH access:
        - If this image was built with PRE_NIXOS_ROOT_KEY, use the matching private key to log in as root.
        - Otherwise, add your public key to /root/.ssh/authorized_keys or set a password with passwd.

      Networking starts automatically; verify connectivity with ip addr or networkctl.

      Run "nixos-help" for the NixOS manual.
    '';
    systemd.network.enable = true;
    networking.useNetworkd = lib.mkForce true;
    networking.useDHCP = lib.mkForce false;
    networking.networkmanager.enable = lib.mkForce false;
    boot.kernelParams = [ "console=tty0" "console=ttyS0,115200n8" ];
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
  };
}
