{ pkgs }:
let
  detectStorageCmd = "${pkgs.pre-nixos}/bin/pre-nixos-detect-storage";
  preNixosCmd = "${pkgs.pre-nixos}/bin/pre-nixos";
in ''
  set -euo pipefail

  status_dir="''${PRE_NIXOS_STATE_DIR:-/run/pre-nixos}"
  status_file=$status_dir/storage-status
  mkdir -p "$status_dir"

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
    if [ -w /dev/console ]; then
      printf '%s\r\n' "$message" > /dev/console
    fi

    if [ "$recorded_ipv4" != "$lan_ipv4" ] || [ ! -r "$network_status" ]; then
      mkdir -p "$status_dir"
      printf 'LAN_IPV4=%s\n' "$lan_ipv4" > "$network_status"
    fi
  }

  version_msg="pre-nixos boot image version ''${PRE_NIXOS_VERSION:-unknown}"
  printf '%s\n' "$version_msg"
  if [ -w /dev/console ]; then
    printf '%s\r\n' "$version_msg" > /dev/console
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

  if ${preNixosCmd} $plan_flag; then
    cat > "$status_file" <<EOF_STATUS
STATE=$status_state
DETAIL=$status_detail
EOF_STATUS
    announce_network
  else
    cat > "$status_file" <<EOF_STATUS
STATE=failed
DETAIL=$status_detail
EOF_STATUS
    announce_network
    exit 1
  fi
''
