{ config, lib, pkgs, ... }:
let
  cfg = config.services.pre-nixos;
in {
  options.services.pre-nixos.enable = lib.mkEnableOption "run pre-nixos planning tool";

  config = lib.mkIf cfg.enable {
    environment.systemPackages = [ pkgs.pre-nixos ];
    boot.kernelParams = [ "console=ttyS0,115200n8" "console=tty0" ];
    boot.loader.grub.extraConfig = ''
      serial --speed=115200 --unit=0 --word=8 --parity=no --stop=1
      terminal_input serial console
      terminal_output serial console
    '';
    systemd.services.pre-nixos = {
      description = "Pre-NixOS setup";
      wantedBy = [ "multi-user.target" ];
      serviceConfig.Type = "oneshot";
      environment = { PRE_NIXOS_EXEC = "1"; };
      script = ''
        ${pkgs.pre-nixos}/bin/pre-nixos --plan-only
      '';
    };

    # Keep OpenSSH disabled until secure_ssh hardens the configuration.
    services.openssh.enable = true;
    systemd.services.sshd.wantedBy = lib.mkForce [ ];
    systemd.services.sshd.after = [ "pre-nixos.service" ];
    systemd.services.sshd.serviceConfig.ExecStart =
      lib.mkForce "${pkgs.openssh}/sbin/sshd -D -e -f /etc/ssh/sshd_config";
  };
}
