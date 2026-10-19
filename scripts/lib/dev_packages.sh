#!/usr/bin/env bash
# Single definition of the APT packages the development workflow needs, shared
# by scripts/codex-setup.sh and .claude/hooks/session-start.sh.
#
# Why each package is needed:
#   ca-certificates curl gnupg xz-utils  - fetching the Nix installer (Codex)
#   python3 python3-venv python3-pip python3-dev build-essential
#                                        - the .venv used to run pytest
#   qemu-system-x86 qemu-utils           - booting the ISO in tests/vm
#   qemu-user-static                     - building aarch64-linux under binfmt
#                                          (scripts/lib/aarch64_emulation.sh)
#   qemu-system-arm                      - booting the AArch64 image (qemu-system-aarch64)
#   zstd                                 - unpacking the AArch64 SD image (.img.zst)
#   openssh-client                       - ssh/ssh-keygen used by tests/vm fixtures

DEV_APT_PACKAGES=(
  ca-certificates
  curl
  gnupg
  xz-utils
  python3
  python3-venv
  python3-pip
  python3-dev
  build-essential
  qemu-system-x86
  qemu-utils
  qemu-user-static
  qemu-system-arm
  zstd
  openssh-client
)

_dev_packages_log() {
  if declare -F log >/dev/null 2>&1; then
    log "$@"
  else
    printf '%s\n' "$*"
  fi
}

# Print the subset of DEV_APT_PACKAGES that is not installed.
missing_dev_apt_packages() {
  local pkg status
  for pkg in "${DEV_APT_PACKAGES[@]}"; do
    status="$(dpkg-query -W -f='${Status}' "${pkg}" 2>/dev/null || true)"
    if [[ "${status}" != "install ok installed" ]]; then
      printf '%s\n' "${pkg}"
    fi
  done
}

# Install whichever DEV_APT_PACKAGES are missing; a no-op when all are present.
install_missing_dev_apt_packages() {
  if ! command -v apt-get >/dev/null 2>&1; then
    _dev_packages_log "apt-get not available; skipping APT package installation."
    return 0
  fi

  local -a missing
  mapfile -t missing < <(missing_dev_apt_packages)
  if [[ ${#missing[@]} -eq 0 ]]; then
    _dev_packages_log "All required APT packages already installed."
    return 0
  fi

  _dev_packages_log "Installing missing APT packages: ${missing[*]}"
  apt-get update
  DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends "${missing[@]}"
}
