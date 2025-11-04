# shellcheck shell=sh
state_dir=${PRE_NIXOS_STATE_DIR:-/run/pre-nixos}

if [ -n "${PRE_NIXOS_VERSION-}" ]; then
  printf '%s\n' "pre-nixos boot image version ${PRE_NIXOS_VERSION}"
fi
status_file=$state_dir/storage-status
if [ -r "$status_file" ]; then
  state=""
  detail=""
  while IFS='=' read -r key value; do
    case "$key" in
      STATE) state=$value ;;
      DETAIL) detail=$value ;;
    esac
  done < "$status_file"
  case "$state" in
    applied)
      if [ "$detail" = "auto-applied" ]; then
        printf '%s\n' "pre-nixos: Storage provisioning completed automatically."
      fi
      ;;
    plan-only)
      if [ "$detail" = "existing-storage" ]; then
        printf '%s\n' "pre-nixos: Existing storage detected; provisioning ran in plan-only mode."
        printf '%s\n' "             Review and apply the plan with 'pre-nixos' or 'pre-nixos-tui'."
      elif [ "$detail" = "detection-error" ]; then
        printf '%s\n' "pre-nixos: Storage detection encountered an error; provisioning ran in plan-only mode."
        printf '%s\n' "             Check 'journalctl -u pre-nixos' for details before continuing."
      else
        printf '%s\n' "pre-nixos: Provisioning ran in plan-only mode. Review before applying."
      fi
      ;;
    failed)
      case "$detail" in
        existing-storage)
          printf '%s\n' "pre-nixos: Provisioning failed while running in plan-only mode after detecting existing storage."
          ;;
        detection-error)
          printf '%s\n' "pre-nixos: Provisioning failed after a detection error forced plan-only mode."
          ;;
        *)
          printf '%s\n' "pre-nixos: Provisioning failed."
          ;;
      esac
      printf '%s\n' "             Inspect 'journalctl -u pre-nixos' for failure details."
      ;;
    "")
      ;;
    *)
      printf '%s\n' "pre-nixos: Provisioning status is '$state' ($detail)."
      ;;
  esac
fi

network_status_file=$state_dir/network-status
if [ -r "$network_status_file" ]; then
  ipv4=""
  while IFS='=' read -r key value; do
    case "$key" in
      LAN_IPV4) ipv4=$value ;;
    esac
  done < "$network_status_file"
  if [ -n "$ipv4" ]; then
    printf '%s\n' "LAN IPv4 address: $ipv4"
  fi
fi
