# pre-nixos: report degraded md arrays on the installed system (task queue
# item 49; reqs R-S7).  pre-nixos writes this module and its two scripts into
# /etc/nixos and imports it; the reference installed systems in the image
# (modules/pre-nixos/reference-installed.nix) import it too.
#
# mdadm's monitor mailed `root` (MAILADDR root), but there is no sendmail, so a
# degraded array went unnoticed (#344).  Instead:
# - at every login shell (console and SSH), pre-nixos-md-status.sh prints a
#   warning for each degraded or inactive array, read from /proc/mdstat;
# - mdadm runs pre-nixos-md-event.sh for each event (PROGRAM): failures go to
#   the journal at crit and to logged-in terminals (wall);
# - mdadm's daily "Reminder for degraded MD arrays" timer is enabled (NixOS
#   ignores its [Install] section), so a degraded array is reported again
#   through the same hook every day.
{ pkgs, lib, ... }:
let
  script = name: file: tools:
    pkgs.writeShellScript name (
      "PATH=${lib.makeBinPath tools}:$PATH\n" + builtins.readFile file
    );
  status = script "pre-nixos-md-status" ./pre-nixos-md-status.sh [ pkgs.gawk ];
  event = script "pre-nixos-md-event" ./pre-nixos-md-event.sh [ pkgs.util-linux ];
in
{
  boot.swraid.mdadmConf = "PROGRAM ${event}";
  environment.loginShellInit = "${status}";
  systemd.timers.mdmonitor-oneshot.wantedBy = [ "timers.target" ];
}
