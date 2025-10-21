# shellcheck shell=sh
if [ -n "${PRE_NIXOS_VERSION-}" ]; then
  printf '%s\n' "pre-nixos boot image version ${PRE_NIXOS_VERSION}"
fi
status_file=/run/pre-nixos/storage-status
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
