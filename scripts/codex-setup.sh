#!/usr/bin/env bash
set -euo pipefail

SCRIPT_NAME="$(basename "$0")"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG_PREFIX="[${SCRIPT_NAME}]"

# shellcheck source=./lib/nix_environment.sh
source "${REPO_ROOT}/scripts/lib/nix_environment.sh"
# shellcheck source=./lib/dev_packages.sh
source "${REPO_ROOT}/scripts/lib/dev_packages.sh"
# shellcheck source=./lib/python_venv.sh
source "${REPO_ROOT}/scripts/lib/python_venv.sh"

usage() {
  cat <<USAGE
Usage: ${SCRIPT_NAME} [--skip-nix]

Provision development dependencies for the Pre-NixOS project. The script is
idempotent and safe to run multiple times.

Options:
  --skip-nix   Do not attempt to install the Nix package manager. Useful when
               running in environments where Nix is preinstalled or managed
               separately.
USAGE
}

log() {
  printf '%s %s\n' "${LOG_PREFIX}" "$*"
}

install_nix() {
  if command -v nix >/dev/null 2>&1; then
    log "Nix already installed; skipping."
    return 0
  fi

  if [[ "${SKIP_NIX:-0}" == "1" ]]; then
    log "Skipping Nix installation because --skip-nix was provided."
    return 0
  fi

  log "Installing Nix (single-user mode)..."
  local installer
  installer="$(mktemp -t nix-installer-XXXXXX.sh)"

  if [[ "${EUID:-$(id -u)}" -eq 0 ]]; then
    if ! getent group nixbld >/dev/null 2>&1; then
      log "Creating system group 'nixbld' for single-user root installation"
      groupadd --system nixbld
    fi

    if [[ ! -d /var/empty ]]; then
      mkdir -p /var/empty
      chmod 755 /var/empty
    fi

    for idx in $(seq 1 10); do
      local user="nixbld${idx}"
      if ! id -u "${user}" >/dev/null 2>&1; then
        log "Creating build user ${user}"
        useradd --system --home-dir /var/empty --no-create-home --shell /usr/sbin/nologin "${user}"
      fi
      usermod -a -G nixbld "${user}"
    done
  fi

  curl -fsSL -o "${installer}" https://nixos.org/nix/install
  chmod +x "${installer}"
  if ! "${installer}" --no-daemon; then
    rm -f "${installer}"
    log "Nix installer failed." >&2
    exit 1
  fi

  rm -f "${installer}"

  log "Nix installation completed. Ensure future shells source \"$HOME/.nix-profile/etc/profile.d/nix.sh\"."
}

configure_nix_features() {
  if [[ -z "${HOME:-}" ]]; then
    log "HOME is not set; skipping Nix configuration"
    return 0
  fi

  local -r conf_dir="${HOME}/.config/nix"
  local -r conf_file="${conf_dir}/nix.conf"
  mkdir -p "${conf_dir}"

  local desired="experimental-features = nix-command flakes"

  if [[ -f "${conf_file}" ]]; then
    if grep -Eq '^experimental-features = .*(nix-command).*(flakes)' "${conf_file}"; then
      log "Nix experimental features already enabled in ${conf_file}"
      return 0
    fi

    if grep -Eq '^experimental-features' "${conf_file}"; then
      log "Updating experimental features entry in ${conf_file}"
      sed -i 's/^experimental-features.*/experimental-features = nix-command flakes/' "${conf_file}"
    else
      log "Appending experimental features entry to ${conf_file}"
      printf '%s\n' "${desired}" >> "${conf_file}"
    fi
  else
    log "Creating ${conf_file} with required experimental features"
    printf '%s\n' "${desired}" > "${conf_file}"
  fi
}

main() {
  local SKIP_NIX=0

  while [[ $# -gt 0 ]]; do
    case "$1" in
      --skip-nix)
        SKIP_NIX=1
        shift
        ;;
      -h|--help)
        usage
        exit 0
        ;;
      *)
        printf 'Unknown option: %s\n\n' "$1" >&2
        usage >&2
        exit 1
        ;;
    esac
  done

  install_missing_dev_apt_packages
  SKIP_NIX="${SKIP_NIX}" install_nix
  create_python_venv
  configure_nix_features
  ensure_nix_command_in_path

  log "Setup completed successfully."
}

main "$@"
