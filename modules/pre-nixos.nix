{ config, lib, pkgs, ... }:
let
  cfg = config.services.pre-nixos;
in {
  options.services.pre-nixos.enable = lib.mkEnableOption "run pre-nixos planning tool";

  config = lib.mkIf cfg.enable {
    environment.systemPackages = [ pkgs.pre-nixos ];
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
