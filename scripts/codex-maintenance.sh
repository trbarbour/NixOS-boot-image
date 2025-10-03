#!/usr/bin/env bash
set -euo pipefail

SCRIPT_NAME="$(basename "$0")"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG_PREFIX="[${SCRIPT_NAME}]"

log() {
  printf '%s %s\n' "${LOG_PREFIX}" "$*"
}

authorise_nix_profile() {
  local -r nix_profile="$HOME/.nix-profile/etc/profile.d/nix.sh"
  local -r shell_profile="$HOME/.profile"

  if [[ ! -f "${nix_profile}" ]]; then
    log "Nix profile script not found; skipping shell integration."
    return 0
  fi

  if [[ -f "${shell_profile}" ]] && grep -Fqs 'nix.sh' "${shell_profile}"; then
    log "Shell profile already sources nix.sh"
    return 0
  fi

  log "Adding Nix profile sourcing to ${shell_profile}"
  {
    printf '\n# Added by %s on %s\n' "${SCRIPT_NAME}" "$(date --iso-8601=seconds)"
    printf 'export USER=${USER:-$(id -un)}\n'
    printf '. "$HOME/.nix-profile/etc/profile.d/nix.sh"\n'
  } >> "${shell_profile}"
}

update_python_dependencies() {
  local -r venv_path="${REPO_ROOT}/.venv"

  if [[ ! -d "${venv_path}" ]]; then
    log "Virtual environment missing; running setup script without Nix install."
    "${REPO_ROOT}/scripts/codex-setup.sh" --skip-nix
    return 0
  fi

  if [[ ! -f "${REPO_ROOT}/requirements-dev.txt" ]]; then
    log "requirements-dev.txt not present; nothing to update."
    return 0
  fi

  log "Upgrading Python developer dependencies"
  "${venv_path}/bin/pip" install --upgrade -r "${REPO_ROOT}/requirements-dev.txt"
}

main() {
  authorise_nix_profile
  update_python_dependencies
  log "Maintenance tasks completed."
}

main "$@"
