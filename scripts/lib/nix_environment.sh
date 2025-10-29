#!/usr/bin/env bash

_nix_env_log() {
  if declare -F log >/dev/null 2>&1; then
    log "$@"
  else
    printf '%s\n' "$*"
  fi
}

ensure_nix_command_in_path() {
  local -r home_dir="${HOME:-}"
  if [[ -z "${home_dir}" ]]; then
    _nix_env_log "HOME is not set; skipping Nix PATH integration."
    return 0
  fi

  local -r profile_bin="${home_dir}/.nix-profile/bin"
  if [[ ! -d "${profile_bin}" ]]; then
    _nix_env_log "Nix profile bin directory ${profile_bin} not found; skipping PATH integration."
    return 0
  fi

  local -r target_dir="/usr/local/bin"
  if [[ ! -d "${target_dir}" ]]; then
    mkdir -p "${target_dir}"
  fi

  local -r binaries=(
    nix
    nix-build
    nix-channel
    nix-collect-garbage
    nix-copy-closure
    nix-env
    nix-hash
    nix-instantiate
    nix-prefetch-url
    nix-shell
    nix-store
  )

  local updated=0
  for binary in "${binaries[@]}"; do
    local source_path="${profile_bin}/${binary}"
    local link_path="${target_dir}/${binary}"
    if [[ ! -x "${source_path}" ]]; then
      continue
    fi

    if [[ -L "${link_path}" ]]; then
      local current_target
      current_target="$(readlink -f "${link_path}")"
      if [[ "${current_target}" == "${source_path}" ]]; then
        continue
      fi
    elif [[ -e "${link_path}" ]]; then
      _nix_env_log "Skipping ${link_path}; non-symlink file already exists."
      continue
    fi

    ln -sfn "${source_path}" "${link_path}"
    _nix_env_log "Linked ${binary} to ${link_path}"
    updated=1
  done

  if [[ "${updated}" -eq 0 ]]; then
    _nix_env_log "Nix PATH integration already up to date."
  fi
}
