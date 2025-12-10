set -euo pipefail

preferred_iface="${ANNOUNCE_PREFERRED_IFACE:-lan}"
status_dir="${PRE_NIXOS_STATE_DIR:-/run/pre-nixos}"
status_file="${ANNOUNCE_STATUS_FILE:-}"
if [ -z "$status_file" ] && [ -n "$status_dir" ]; then
  status_file="$status_dir/network-status"
fi
update_status="${ANNOUNCE_WRITE_STATUS:-0}"
update_issue="${ANNOUNCE_UPDATE_ISSUE:-0}"
notify_consoles="${ANNOUNCE_NOTIFY_CONSOLES:-0}"
console_fallback="${ANNOUNCE_CONSOLE_FALLBACK:-0}"
stdout_message="${ANNOUNCE_STDOUT_MESSAGE:-1}"
issue_path="${ANNOUNCE_ISSUE_PATH:-/etc/issue}"
max_attempts="${ANNOUNCE_MAX_ATTEMPTS:-60}"
delay="${ANNOUNCE_DELAY:-1}"
route_target="${ANNOUNCE_ROUTE_TARGET:-1.1.1.1}"
  broadcast_cmd="${BROADCAST_CONSOLE_CMD:-}"
  preferred_missing_message=""
  shell_bin="${BASH:-sh}"

read_recorded_ipv4() {
  local path="$1" key value record=""
  if [ -z "$path" ] || [ ! -r "$path" ]; then
    return 1
  fi
  while IFS='=' read -r key value; do
    if [ "$key" = "LAN_IPV4" ] && [ -n "$value" ]; then
      record=$(printf '%s' "$value" | tr -d '\r')
      break
    fi
  done < "$path"
  if [ -n "$record" ]; then
    printf '%s' "$record"
    return 0
  fi
  return 1
}

read_iface_ipv4() {
  local iface="$1" output line field
  if [ -z "$iface" ]; then
    return 1
  fi
  if ! output=$(ip -o -4 addr show dev "$iface" scope global 2>/dev/null); then
    return 1
  fi
  line=${output%%$'\n'*}
  field=${line#* inet }
  if [ "$field" = "$line" ]; then
    return 1
  fi
  field=${field%% *}
  field=${field%%/*}
  if [ -n "$field" ]; then
    printf '%s' "$field"
    return 0
  fi
  return 1
}

read_route_ipv4() {
  local target="$1" output
  if ! output=$(ip route get "$target" 2>/dev/null); then
    return 1
  fi
  set -- $output
  while [ "$#" -gt 0 ]; do
    if [ "$1" = "src" ] && [ "$#" -ge 2 ]; then
      printf '%s' "$2"
      return 0
    fi
    shift
  done
  return 1
}

attempt=0
ip_address=""
while [ "$attempt" -lt "$max_attempts" ]; do
  attempt=$((attempt + 1))
  ip_address=""
  if recorded=$(read_recorded_ipv4 "$status_file"); then
    ip_address="$recorded"
  fi
  if [ -z "$ip_address" ] && iface_ip=$(read_iface_ipv4 "$preferred_iface"); then
    ip_address="$iface_ip"
  fi
  if [ -z "$ip_address" ] && route_ip=$(read_route_ipv4 "$route_target"); then
    ip_address="$route_ip"
  fi
  if [ -z "$ip_address" ] && [ -n "$preferred_iface" ]; then
    if ! ip link show dev "$preferred_iface" >/dev/null 2>&1; then
      preferred_missing_message="preferred interface \"$preferred_iface\" not found"
    fi
  fi
  if [ -n "$ip_address" ]; then
    break
  fi
  if [ "$attempt" -lt "$max_attempts" ]; then
    sleep "$delay"
  fi
done

ip_address=$(printf '%s' "$ip_address" | tr -d '\r\n')
message="LAN IPv4 address unavailable"
if [ -n "$ip_address" ]; then
  message="LAN IPv4 address: $ip_address"
  if [ "$update_status" = "1" ] && [ -n "$status_file" ]; then
    mkdir -p "$(dirname "$status_file")"
    printf 'LAN_IPV4=%s\n' "$ip_address" > "$status_file"
  fi
elif [ -n "$preferred_missing_message" ]; then
  message="LAN IPv4 address unavailable ($preferred_missing_message)"
fi

if [ "$stdout_message" != "0" ]; then
  printf '%s\n' "$message"
fi

broadcast_failed=1
  if [ -n "$broadcast_cmd" ]; then
    # Parse the configured broadcast command with the shell so quoted arguments are
    # preserved, allowing paths with spaces or additional flags. The first token is
    # used to verify the executable exists before invoking the full command with
    # the message passed as the first positional parameter.
    broadcast_bin=$("$shell_bin" -c "set -- $broadcast_cmd; printf '%s' \"\$1\"")
    if command -v "$broadcast_bin" >/dev/null 2>&1; then
      if "$shell_bin" -c "exec $broadcast_cmd \"\$1\"" broadcast "$message"; then
        broadcast_failed=0
      fi
    else
    logger -t pre-nixos-announce-lan-ip \
      "broadcast command '$broadcast_bin' not found; skipping LAN IP console broadcast" || true
  fi
fi

if [ "$update_issue" = "1" ]; then
  tmp=""
  if tmp=$(mktemp); then
    if [ -f "$issue_path" ]; then
      sed '/^# pre-nixos auto-install ip start$/,/^# pre-nixos auto-install ip end$/d' "$issue_path" > "$tmp"
    else
      : > "$tmp"
    fi
    if [ -n "$ip_address" ]; then
      {
        cat "$tmp"
        echo '# pre-nixos auto-install ip start'
        printf 'LAN IPv4 address: %s\n' "$ip_address"
        echo '# pre-nixos auto-install ip end'
      } > "$issue_path"
    else
      mv "$tmp" "$issue_path"
    fi
    rm -f "$tmp"
  fi
fi

if [ "$notify_consoles" = "1" ] && [ -r /sys/class/tty/console/active ]; then
  while IFS= read -r name; do
    [ -n "$name" ] || continue
    target="/dev/$name"
    if [ -w "$target" ]; then
      printf '%s\n' "$message" > "$target"
    fi
  done < /sys/class/tty/console/active
fi

if [ "$console_fallback" = "1" ] && [ -w /dev/console ]; then
  printf '%s\n' "$message" > /dev/console
fi

