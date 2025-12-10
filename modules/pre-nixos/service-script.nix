{ pkgs }:
let
  detectStorageCmd = "${pkgs.pre-nixos}/bin/pre-nixos-detect-storage";
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

  plan_flag=""
  status_state="applied"
  status_detail="auto-applied"

  if ${detectStorageCmd}; then
    plan_flag="--plan-only"
    status_state="plan-only"
    status_detail="existing-storage"
  else
    status=$?
    if [ "$status" -ne 1 ]; then
      echo "pre-nixos: storage detection failed (exit $status), defaulting to plan-only" >&2
      plan_flag="--plan-only"
      status_state="plan-only"
      status_detail="detection-error"
    fi
  fi

  set +e
  ${preNixosCmd} $plan_flag
  pre_status=$?
  set -e
  read_auto_status

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
