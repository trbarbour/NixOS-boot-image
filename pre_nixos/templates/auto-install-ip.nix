{ pkgs, ... }:
let
  broadcastConsoleCmd =
    if builtins.hasAttr "pre-nixos" pkgs then
      "${pkgs.pre-nixos}/bin/pre-nixos-console broadcast"
    else
      "pre-nixos-console broadcast";

  announceServicePath =
    let
      preNixosPath = if builtins.hasAttr "pre-nixos" pkgs then [ pkgs.pre-nixos ] else [ ];
    in with pkgs;
      [ coreutils gnused gnugrep iproute2 util-linux findutils busybox ]
      ++ preNixosPath;

  reportServicePath =
    with pkgs;
      [ coreutils iproute2 util-linux systemd procps gnugrep gnused findutils busybox ];

  announceLanIpScript = pkgs.writeShellScript "pre-nixos-announce-lan-ip"
    (builtins.readFile ./pre-nixos-announce-lan-ip.sh);

  networkReportScript = pkgs.writeShellScript "pre-nixos-network-report" ''
    set -euo pipefail

    report_dir="''${PRE_NIXOS_STATE_DIR:-/run/pre-nixos}"
    mkdir -p "$report_dir"
    report_path="$report_dir/network-report"

    {
      echo "# pre-nixos network report $(date -u +"%Y-%m-%dT%H:%M:%SZ")"
      echo "## ip -br link"
      ip -br link || true
      echo
      echo "## networkctl status --all"
      networkctl status --all --no-pager || true
      echo
      echo "## networkctl status lan"
      networkctl status lan --no-pager || true
      echo
      echo "## .link files"
      for dir in /etc/systemd/network /run/systemd/network; do
        if ls "$dir"/*.link > /dev/null 2>&1; then
          for file in "$dir"/*.link; do
            echo "-- $file --"
            cat "$file" || true
            echo
          done
        fi
      done
    } | tee "$report_path" | logger -t pre-nixos-network-report || true
  '';
in {
  systemd.services."pre-nixos-auto-install-ip" = {
    description = "Announce LAN IPv4 on boot";
    wantedBy = [ "multi-user.target" ];
    after = [ "network-online.target" ];
    wants = [ "network-online.target" ];
    path = announceServicePath;
    environment = {
      PRE_NIXOS_STATE_DIR = "/run/pre-nixos";
      ANNOUNCE_STATUS_FILE = "/run/pre-nixos/network-status";
      ANNOUNCE_WRITE_STATUS = "1";
      ANNOUNCE_UPDATE_ISSUE = "0";
      ANNOUNCE_NOTIFY_CONSOLES = "1";
      ANNOUNCE_CONSOLE_FALLBACK = "1";
      ANNOUNCE_STDOUT_MESSAGE = "1";
      ANNOUNCE_PREFERRED_IFACE = "lan";
      ANNOUNCE_MAX_ATTEMPTS = "60";
      ANNOUNCE_DELAY = "1";
      BROADCAST_CONSOLE_CMD = broadcastConsoleCmd;
    };
    serviceConfig = {
      Type = "oneshot";
      StandardOutput = "journal+console";
      StandardError = "journal+console";
    };
    script = "${announceLanIpScript}";
  };

  systemd.services."pre-nixos-network-report" = {
    description = "Collect LAN rename diagnostics for pre-nixos";
    wantedBy = [ "multi-user.target" ];
    after = [ "network-online.target" ];
    wants = [ "network-online.target" ];
    path = reportServicePath;
    serviceConfig = {
      Type = "oneshot";
      StandardOutput = "journal";
      StandardError = "journal";
    };
    script = "${networkReportScript}";
  };
}
