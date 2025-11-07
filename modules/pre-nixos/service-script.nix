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
    local network_status lan_ipv4 key value message
    network_status="$status_dir/network-status"
    if [ ! -r "$network_status" ]; then
      return
    fi
    lan_ipv4=""
    while IFS='=' read -r key value; do
      if [ "$key" = "LAN_IPV4" ] && [ -n "$value" ]; then
        lan_ipv4=$value
        break
      fi
    done < "$network_status"
    if [ -z "$lan_ipv4" ]; then
      return
    fi
    message="LAN IPv4 address: $lan_ipv4"
    printf '%s\n' "$message"
    if [ -w /dev/console ]; then
      printf '%s\r\n' "$message" > /dev/console
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
