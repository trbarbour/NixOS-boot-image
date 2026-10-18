#!/usr/bin/env bash
# Python virtual environment (.venv) used to run the test suite, shared by
# scripts/codex-setup.sh and .claude/hooks/session-start.sh.
# Callers must set REPO_ROOT.

_python_venv_log() {
  if declare -F log >/dev/null 2>&1; then
    log "$@"
  else
    printf '%s\n' "$*"
  fi
}

# Create .venv if needed and (re)install the developer requirements.
create_python_venv() {
  : "${REPO_ROOT:?REPO_ROOT must be set}"
  local -r venv_path="${REPO_ROOT}/.venv"

  if [[ ! -d "${venv_path}" ]]; then
    _python_venv_log "Creating Python virtual environment at ${venv_path}"
    python3 -m venv "${venv_path}"
  else
    _python_venv_log "Virtual environment already exists at ${venv_path}"
  fi

  _python_venv_log "Upgrading pip inside the virtual environment"
  "${venv_path}/bin/python" -m pip install --upgrade pip

  if [[ -f "${REPO_ROOT}/requirements-dev.txt" ]]; then
    _python_venv_log "Installing Python developer requirements"
    "${venv_path}/bin/pip" install --upgrade -r "${REPO_ROOT}/requirements-dev.txt"
  else
    _python_venv_log "requirements-dev.txt not found; skipping Python dependency installation."
  fi
}

# Hash of every input that determines the venv's contents.
_python_venv_inputs_hash() {
  local -a inputs=("${REPO_ROOT}/pyproject.toml" "${REPO_ROOT}/requirements-dev.txt")
  { python3 --version; cat "${inputs[@]}"; } | sha256sum | cut -d' ' -f1
}

# Run create_python_venv only when .venv is missing or its inputs changed
# since the last successful run (recorded in .venv/.inputs-sha256).
ensure_python_venv_current() {
  : "${REPO_ROOT:?REPO_ROOT must be set}"
  local -r stamp="${REPO_ROOT}/.venv/.inputs-sha256"
  local current
  current="$(_python_venv_inputs_hash)"
  if [[ -x "${REPO_ROOT}/.venv/bin/python" && -f "${stamp}" && "$(cat "${stamp}")" == "${current}" ]]; then
    _python_venv_log "Python virtual environment is up to date."
    return 0
  fi
  create_python_venv
  printf '%s\n' "${current}" > "${stamp}"
}
