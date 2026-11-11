# pre-nixos: report degraded or inactive md arrays at login (task queue item
# 49; reqs R-S7).  Run from environment.loginShellInit by
# pre-nixos-raid-alerts.nix.  Prints nothing when every array is complete, and
# never fails, so a login is never blocked.  PRE_NIXOS_MDSTAT overrides the
# input for tests (tests/test_raid_alerts.py).
mdstat="${PRE_NIXOS_MDSTAT:-/proc/mdstat}"
[ -r "$mdstat" ] || exit 0
awk '
  function flush() {
    if (name == "") return
    if (state == "inactive") {
      printf "*** WARNING: RAID array %s is inactive (not running).\n", name
      named = 1
    } else if (total != "" && active + 0 < total + 0) {
      printf "*** WARNING: RAID array %s is degraded (%s of %s devices active)%s.\n", name, active, total, progress
      named = 1
    }
    if (named) {
      printf "    See /proc/mdstat and: mdadm --detail /dev/%s\n", name
    }
    name = ""; state = ""; total = ""; active = ""; progress = ""; named = 0
  }
  /^md[^ ]* : / { flush(); name = $1; state = $3; next }
  name != "" && match($0, /\[[0-9]+\/[0-9]+\]/) {
    split(substr($0, RSTART + 1, RLENGTH - 2), counts, "/")
    total = counts[1]; active = counts[2]
  }
  name != "" && match($0, /(recovery|resync|reshape) *= *[0-9.]+%/) {
    progress = ", " substr($0, RSTART, RLENGTH)
    gsub(/ *= */, " ", progress)
  }
  END { flush() }
' "$mdstat" 2>/dev/null || true
exit 0
