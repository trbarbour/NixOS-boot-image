#!/usr/bin/env bash
set -euo pipefail

SCRIPT_NAME="$(basename "$0")"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG_PREFIX="[${SCRIPT_NAME}]"

log() {
  printf '%s %s\n' "${LOG_PREFIX}" "$*"
}

# shellcheck source=./lib/nix_environment.sh
source "${REPO_ROOT}/scripts/lib/nix_environment.sh"

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
  ensure_nix_command_in_path
  update_python_dependencies
  log "Maintenance tasks completed."
}

main "$@"
