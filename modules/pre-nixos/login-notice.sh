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
      elif [ "$detail" = "disk-class-unconfirmed" ]; then
        printf '%s\n' "pre-nixos: A disk named SSD is reported as rotating; nothing was provisioned or installed."
        printf '%s\n' "             Confirm its type with 'pre-nixos-tui', or 'pre-nixos --ssd DISK' (or --hdd DISK)."
      elif [ "$detail" = "detection-error" ]; then
        printf '%s\n' "pre-nixos: Storage detection encountered an error; provisioning ran in plan-only mode."
        printf '%s\n' "             Check 'journalctl -u pre-nixos' for details before continuing."
      elif [ "$detail" = "disks-unsettled" ]; then
        printf '%s\n' "pre-nixos: Disks were still appearing or disappearing at boot; nothing was provisioned or installed."
        printf '%s\n' "             Check the disks with 'lsblk', then apply with 'pre-nixos-tui' (it plans for the disks present)."
      elif [ "$detail" = "disk-wait-error" ]; then
        printf '%s\n' "pre-nixos: The wait for the disks failed; provisioning ran in plan-only mode."
        printf '%s\n' "             Check 'journalctl -u pre-nixos' for details before continuing."
      elif [ "$detail" = "disks-changed" ]; then
        printf '%s\n' "pre-nixos: The disks changed after the plan was made; nothing was written."
        printf '%s\n' "             Re-plan and apply with 'pre-nixos-tui' ([R] rescans), or run 'pre-nixos' again."
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

auto_status_file=$state_dir/auto-install-status
if [ -r "$auto_status_file" ] && grep -qx 'REASON=no-network' "$auto_status_file"; then
  printf '%s\n' "pre-nixos: Auto-install is waiting for the network (an IPv4 address and a default route on lan)."
  printf '%s\n' "             Configure it, then run 'pre-nixos --install-now' or press N in 'pre-nixos-tui'."
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
