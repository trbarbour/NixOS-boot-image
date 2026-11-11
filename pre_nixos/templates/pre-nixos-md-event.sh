# pre-nixos: mdadm's PROGRAM for md array events (task queue item 49; reqs
# R-S7).  mdadm --monitor runs it as: EVENT MD-DEVICE [COMPONENT-DEVICE].
# Failures go to the journal at crit and to every logged-in terminal (wall);
# other events to the journal at info.  It replaces MAILADDR root: the
# installed system has no sendmail (#344).  Never fails, so mdadm keeps going.
event="${1:-unknown}"
device="${2:-}"
component="${3:-}"
message="mdadm: ${event} on ${device:-an md array}${component:+ (${component})}"
case "$event" in
  Fail | FailSpare | DegradedArray | DeviceDisappeared | SparesMissing)
    logger -p daemon.crit -t mdadm-alert "$message" || true
    printf '%s\n%s\n' "*** RAID WARNING: $message" "    See /proc/mdstat and: mdadm --detail ${device:-/dev/md*}" | wall || true
    ;;
  *)
    logger -p daemon.info -t mdadm-event "$message" || true
    ;;
esac
exit 0
