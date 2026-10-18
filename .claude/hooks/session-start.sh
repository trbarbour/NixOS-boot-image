#!/usr/bin/env bash
# SessionStart hook for Claude Code cloud sessions: provision what the test
# suite needs (see docs/work-notes/2026-10-18T02-01-07Z-claude-code-environment-migration.md).
# Idempotent; installs only what is missing. Does nothing outside the cloud.
set -euo pipefail

if [[ "${CLAUDE_CODE_REMOTE:-}" != "true" ]]; then
  exit 0
fi

REPO_ROOT="${CLAUDE_PROJECT_DIR:?CLAUDE_PROJECT_DIR must be set}"
LOG_PREFIX="[session-start]"

log() {
  printf '%s %s\n' "${LOG_PREFIX}" "$*" >&2
}

# shellcheck source=../../scripts/lib/dev_packages.sh
source "${REPO_ROOT}/scripts/lib/dev_packages.sh"
# shellcheck source=../../scripts/lib/python_venv.sh
source "${REPO_ROOT}/scripts/lib/python_venv.sh"

install_missing_dev_apt_packages
ensure_python_venv_current

if ! command -v nix >/dev/null 2>&1; then
  log "ERROR: nix is not in PATH; boot-image builds and VM tests cannot run."
  exit 1
fi

# The session proxy refuses GitHub archive tarballs for unattached repositories,
# so fetch github: flake inputs over git (verified against flake.lock).
if [[ -n "${CLAUDE_ENV_FILE:-}" ]]; then
  printf 'export PRE_NIXOS_NIX_GIT_INPUTS=1\n' >> "${CLAUDE_ENV_FILE}"
  log "Set PRE_NIXOS_NIX_GIT_INPUTS=1 for this session."
else
  log "WARNING: CLAUDE_ENV_FILE unset; PRE_NIXOS_NIX_GIT_INPUTS not persisted."
fi

log "Session environment ready."
