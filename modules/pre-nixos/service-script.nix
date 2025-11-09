{ pkgs }:
let
  detectStorageCmd = "${pkgs.pre-nixos}/bin/pre-nixos-detect-storage";
  preNixosCmd = "${pkgs.pre-nixos}/bin/pre-nixos";
  broadcastConsoleCmd = "${pkgs.python3}/bin/python3 -m pre_nixos.console broadcast";
in ''
  set -euo pipefail

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
    local network_status lan_ipv4 recorded_ipv4 key value message attempt max_attempts ip_output ip_line ip_field
    network_status="$status_dir/network-status"
    lan_ipv4=""
    recorded_ipv4=""
    max_attempts=120
    attempt=0

    while [ "$attempt" -lt "$max_attempts" ]; do
      attempt=$((attempt + 1))
      recorded_ipv4=""
      if [ -r "$network_status" ]; then
        while IFS='=' read -r key value; do
          if [ "$key" = "LAN_IPV4" ] && [ -n "$value" ]; then
            recorded_ipv4=$(printf %s "$value" | tr -d "\r")
            break
          fi
        done < "$network_status"
      fi

      lan_ipv4="$recorded_ipv4"

      if [ -z "$lan_ipv4" ]; then
        if ip_output=$(ip -4 -o addr show dev lan 2>/dev/null); then
          ip_line=$(printf %s "$ip_output" | head -n1)
          ip_field=''${ip_line#* inet }
          if [ "$ip_field" != "$ip_line" ]; then
            ip_field=''${ip_field%% *}
            lan_ipv4=''${ip_field%%/*}
          else
            lan_ipv4=""
          fi
        else
          lan_ipv4=""
        fi
      fi

      if [ -n "$lan_ipv4" ]; then
        lan_ipv4=$(printf %s "$lan_ipv4" | tr -d "\r\n")
      fi

      if [ -n "$lan_ipv4" ]; then
        break
      fi

      sleep 1
    done

    if [ -z "$lan_ipv4" ]; then
      return
    fi

    message="LAN IPv4 address: $lan_ipv4"
    printf '%s\n' "$message"
    if ! ${broadcastConsoleCmd} "$message"; then
      if [ -w /dev/console ]; then
        printf '%s\r\n' "$message" > /dev/console
      fi
    fi

    if [ "$recorded_ipv4" != "$lan_ipv4" ] || [ ! -r "$network_status" ]; then
      mkdir -p "$status_dir"
      printf 'LAN_IPV4=%s\n' "$lan_ipv4" > "$network_status"
    fi
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
      printf 'AUTO_INSTALL=%s\n' "${auto_install_state:-skipped}"
      if [ -n "$auto_install_reason" ]; then
        printf 'AUTO_INSTALL_REASON=%s\n' "$auto_install_reason"
      fi
    } > "$status_file"
    announce_network
  else
    {
      printf 'STATE=failed\n'
      printf 'DETAIL=%s\n' "$status_detail"
      printf 'AUTO_INSTALL=%s\n' "${auto_install_state:-failed}"
      if [ -n "$auto_install_reason" ]; then
        printf 'AUTO_INSTALL_REASON=%s\n' "$auto_install_reason"
      fi
    } > "$status_file"
    if [ "${auto_install_state}" = "failed" ] && [ -n "$auto_install_reason" ]; then
      echo "pre-nixos: auto-install failed: $auto_install_reason" >&2
    fi
    announce_network
    exit 1
  fi
''
