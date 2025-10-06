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
  local -r marker="# Added by ${SCRIPT_NAME} to ensure USER before sourcing nix profile"
  local -r export_line='export USER=${USER:-$(id -un)}'
  local -r source_line='. "$HOME/.nix-profile/etc/profile.d/nix.sh"'

  if [[ ! -f "${nix_profile}" ]]; then
    log "Nix profile script not found; skipping shell integration."
    return 0
  fi

  if [[ ! -f "${shell_profile}" ]]; then
    log "Creating ${shell_profile} for Nix integration"
    printf '#!/usr/bin/env sh\n' > "${shell_profile}"
    chmod 644 "${shell_profile}"
  fi

  if grep -Fqs "${marker}" "${shell_profile}"; then
    log "Shell profile already patched for Nix integration"
    return 0
  fi

  if grep -Fqs "${source_line}" "${shell_profile}"; then
    log "Ensuring USER is exported before existing nix.sh sourcing in ${shell_profile}"
    python3 - "$shell_profile" "$marker" "$export_line" "$source_line" <<'PY'
import sys
from pathlib import Path

profile_path = Path(sys.argv[1])
marker = sys.argv[2]
export_line = sys.argv[3]
source_line = sys.argv[4]

lines = profile_path.read_text().splitlines()

for idx, line in enumerate(lines):
    if source_line in line:
        lines.insert(idx, marker)
        lines.insert(idx + 1, export_line)
        break
else:
    lines.extend(["", marker, export_line, source_line])

profile_path.write_text("\n".join(lines) + "\n")
PY
    return 0
  fi

  log "Adding Nix profile sourcing to ${shell_profile}"
  {
    printf '\n%s\n' "${marker}"
    printf '%s\n' "${export_line}"
    printf '%s\n' "${source_line}"
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
