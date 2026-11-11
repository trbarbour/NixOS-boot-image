{ pkgs }:
let
  detectStorageCmd = "${pkgs.pre-nixos}/bin/pre-nixos-detect-storage";
  waitDisksCmd = "${pkgs.pre-nixos}/bin/pre-nixos-wait-disks";
  preNixosCmd = "${pkgs.pre-nixos}/bin/pre-nixos";
  broadcastConsoleCmd = "${pkgs.pre-nixos}/bin/pre-nixos-console broadcast";
  announceLanIpScript = pkgs.writeShellScript "pre-nixos-announce-lan-ip"
    (builtins.readFile ../../pre_nixos/scripts/announce-lan-ip.sh);
  defaultLogFile = builtins.replaceStrings ["\n"] [""]
    (builtins.readFile ../../pre_nixos/default_log_file_path.txt);
in ''
  set -euo pipefail

  log_file="''${PRE_NIXOS_LOG_FILE:-${defaultLogFile}}"
  mkdir -p "$(dirname "$log_file")"
  export PRE_NIXOS_LOG_FILE="$log_file"

  if [ -z "''${PRE_NIXOS_PLAN_STDOUT:-}" ]; then
    export PRE_NIXOS_PLAN_STDOUT=0
  fi

  if [ -r /proc/cmdline ] && grep -qw "pre-nixos-force-cleanup=1" /proc/cmdline; then
    export PRE_NIXOS_FORCE_CLEANUP=1
  fi

  status_dir="''${PRE_NIXOS_STATE_DIR:-/run/pre-nixos}"
  status_file=$status_dir/storage-status
  auto_status_file=$status_dir/auto-install-status
  mkdir -p "$status_dir"

  read_auto_status() {
    auto_install_state="skipped"
    auto_install_reason=""
    if [ ! -r "$auto_status_file" ]; then
      return
    fi
    while IFS='=' read -r key value; do
      case "$key" in
        STATE)
          auto_install_state=$(printf %s "$value" | tr -d "\r")
          ;;
        REASON)
          auto_install_reason=$(printf %s "$value" | tr -d "\r")
          ;;
      esac
    done < "$auto_status_file"
  }

  announce_network() {
    PRE_NIXOS_STATE_DIR="$status_dir" \
      ANNOUNCE_STATUS_FILE="$status_dir/network-status" \
      ANNOUNCE_WRITE_STATUS=1 \
      ANNOUNCE_NOTIFY_CONSOLES=1 \
      ANNOUNCE_CONSOLE_FALLBACK=1 \
      ANNOUNCE_STDOUT_MESSAGE=1 \
      ANNOUNCE_PREFERRED_IFACE="lan" \
      ANNOUNCE_MAX_ATTEMPTS=120 \
      ANNOUNCE_DELAY=1 \
      BROADCAST_CONSOLE_CMD='${broadcastConsoleCmd}' \
      ${announceLanIpScript}
  }

  version_msg="pre-nixos boot image version ''${PRE_NIXOS_VERSION:-unknown}"
  printf '%s\n' "$version_msg"
  if ! ${broadcastConsoleCmd} "$version_msg"; then
    if [ -w /dev/console ]; then
      printf '%s\r\n' "$version_msg" > /dev/console
    fi
  fi

  # Task queue item 50 (R-D1): before detection and the plan, which both read
  # the disks, wait until the set of disks has settled.
  wait_status=0
  ${waitDisksCmd} || wait_status=$?

  plan_flag=""
  status_state="applied"
  status_detail="auto-applied"

  if ${detectStorageCmd}; then
    if [ "''${PRE_NIXOS_FORCE_CLEANUP:-0}" = "1" ]; then
      plan_flag="--plan-only"
      status_state="plan-only"
      status_detail="existing-storage-force-cleanup"
    else
      plan_flag="--plan-only"
      status_state="plan-only"
      status_detail="existing-storage"
    fi
  else
    status=$?
    if [ "$status" -ne 1 ]; then
      echo "pre-nixos: storage detection failed (exit $status), defaulting to plan-only" >&2
      plan_flag="--plan-only"
      status_state="plan-only"
      status_detail="detection-error"
    fi
  fi

  # R-D2: disks still changing at the bound, or the wait failed: plan only.
  # A forced cleanup would wipe on an incomplete view of the disks, so it is
  # dropped too.
  if [ "$wait_status" -ne 0 ]; then
    unset PRE_NIXOS_FORCE_CLEANUP
    plan_flag="--plan-only"
    status_state="plan-only"
    if [ "$wait_status" -eq 2 ]; then
      status_detail="disks-unsettled"
    else
      echo "pre-nixos: the disk wait failed (exit $wait_status), defaulting to plan-only" >&2
      status_detail="disk-wait-error"
    fi
  fi

  set +e
  ${preNixosCmd} $plan_flag
  pre_status=$?
  set -e
  read_auto_status

  # R-S3 (task queue item 34): pre-nixos stopped before touching any disk,
  # because a disk named SSD is reported as rotating and needs the user's
  # answer.  That is plan-only, not a failure (pre_nixos.EXIT_NEEDS_ANSWER).
  if [ "$pre_status" -eq 3 ]; then
    pre_status=0
    status_state="plan-only"
    status_detail="disk-class-unconfirmed"
  fi

  # Task queue item 50 (R-D3): the disks changed between the plan and the
  # first write, so pre-nixos wrote nothing (pre_nixos.EXIT_DISKS_CHANGED).
  if [ "$pre_status" -eq 4 ]; then
    pre_status=0
    status_state="plan-only"
    status_detail="disks-changed"
  fi

  if [ "$pre_status" -eq 0 ]; then
    {
      printf 'STATE=%s\n' "$status_state"
      printf 'DETAIL=%s\n' "$status_detail"
      printf 'AUTO_INSTALL=%s\n' "''${auto_install_state:-skipped}"
      if [ -n "$auto_install_reason" ]; then
        printf 'AUTO_INSTALL_REASON=%s\n' "$auto_install_reason"
      fi
    } > "$status_file"
    announce_network
  else
    {
      printf 'STATE=failed\n'
      printf 'DETAIL=%s\n' "$status_detail"
      printf 'AUTO_INSTALL=%s\n' "''${auto_install_state:-failed}"
      if [ -n "$auto_install_reason" ]; then
        printf 'AUTO_INSTALL_REASON=%s\n' "$auto_install_reason"
      fi
    } > "$status_file"
    if [ "''${auto_install_state}" = "failed" ] && [ -n "$auto_install_reason" ]; then
      echo "pre-nixos: auto-install failed: $auto_install_reason" >&2
    fi
    announce_network
    exit 1
  fi
''
