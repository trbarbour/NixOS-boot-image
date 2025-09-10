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
    systemd.services."serial-getty@ttyS0".enable = true;
    systemd.services.pre-nixos = {
      description = "Pre-NixOS setup";
      wantedBy = [ "multi-user.target" ];
      serviceConfig.Type = "oneshot";
      environment = { PRE_NIXOS_EXEC = "1"; };
      script = ''
        ${pkgs.pre-nixos}/bin/pre-nixos --plan-only
      '';
    };
  };
}
