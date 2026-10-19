#!/usr/bin/env bash
# Let this x86_64 host build aarch64-linux derivations under QEMU user-mode
# emulation (AArch64 plan §3.3, requirement R-T1; experiment E2).
#
# - binfmt_misc rule for AArch64 ELF binaries pointing straight at
#   /usr/bin/qemu-aarch64-static with the F flag: the kernel opens the
#   interpreter at registration, so it also works inside the Nix build sandbox,
#   where the packaged rule's wrapper (/usr/libexec/qemu-binfmt/...-P) does not
#   exist.
# - Nix: aarch64-linux appended to extra-platforms (single-user install, so it applies
#   to the next nix invocation).
#
# Paths are overridable for tests: BINFMT_DIR, QEMU_BINFMT_CONF,
# QEMU_AARCH64_STATIC, NIX_CUSTOM_CONF.

: "${BINFMT_DIR:=/proc/sys/fs/binfmt_misc}"
: "${QEMU_BINFMT_CONF:=/usr/lib/binfmt.d/qemu-aarch64.conf}"
: "${QEMU_AARCH64_STATIC:=/usr/bin/qemu-aarch64-static}"
: "${NIX_CUSTOM_CONF:=/etc/nix/nix.custom.conf}"

_aarch64_log() {
  if declare -F log >/dev/null 2>&1; then
    log "$@"
  else
    printf '%s\n' "$*" >&2
  fi
}

# Print the registration line: the packaged rule with our interpreter and F.
aarch64_binfmt_rule() {
  local rule
  rule="$(grep -m1 '^:qemu-aarch64:' "${QEMU_BINFMT_CONF}")" || return 1
  printf '%s\n' "$(sed -E "s#:[^:]*:[^:]*\$#:${QEMU_AARCH64_STATIC}:F#" <<<"${rule}")"
}

# True when the registered rule already uses our interpreter with flag F.
aarch64_binfmt_current() {
  local entry="${BINFMT_DIR}/qemu-aarch64"
  [[ -f "${entry}" ]] \
    && grep -qx 'enabled' "${entry}" \
    && grep -qx "interpreter ${QEMU_AARCH64_STATIC}" "${entry}" \
    && grep -qx 'flags: F' "${entry}"
}

ensure_aarch64_binfmt() {
  if [[ ! -x "${QEMU_AARCH64_STATIC}" ]]; then
    _aarch64_log "WARNING: ${QEMU_AARCH64_STATIC} missing (package qemu-user-static); AArch64 builds unavailable."
    return 1
  fi
  if [[ ! -e "${BINFMT_DIR}/register" ]]; then
    mount -t binfmt_misc binfmt_misc "${BINFMT_DIR}" 2>/dev/null || {
      _aarch64_log "WARNING: cannot mount binfmt_misc at ${BINFMT_DIR}; AArch64 builds unavailable."
      return 1
    }
  fi
  if aarch64_binfmt_current; then
    return 0
  fi
  if [[ -f "${BINFMT_DIR}/qemu-aarch64" ]]; then
    # Remove a different rule.
    printf -- '-1' >"${BINFMT_DIR}/qemu-aarch64" || {
      _aarch64_log "WARNING: cannot remove the existing qemu-aarch64 rule; AArch64 builds unavailable."
      return 1
    }
  fi
  local rule
  rule="$(aarch64_binfmt_rule)" || {
    _aarch64_log "WARNING: no qemu-aarch64 rule in ${QEMU_BINFMT_CONF}; AArch64 builds unavailable."
    return 1
  }
  # Every write's status is checked explicitly: callers use these functions as
  # conditions ("if ! ensure_aarch64_emulation"), where errexit is off.
  printf '%s' "${rule}" >"${BINFMT_DIR}/register" || {
    _aarch64_log "WARNING: cannot register the binfmt rule; AArch64 builds unavailable."
    return 1
  }
  _aarch64_log "Registered binfmt rule for AArch64 (${QEMU_AARCH64_STATIC}, flag F)."
}

ensure_nix_aarch64_platform() {
  # "extra-" appends to a list option; plain "extra-platforms = …" would replace
  # Nix's computed default (i686-linux, x86_64-v*-linux), as observed 2026-10-19.
  local line='extra-extra-platforms = aarch64-linux'
  if [[ -f "${NIX_CUSTOM_CONF}" ]] && grep -qx "${line}" "${NIX_CUSTOM_CONF}"; then
    return 0
  fi
  printf '%s\n' "${line}" >>"${NIX_CUSTOM_CONF}" || {
    _aarch64_log "WARNING: cannot write ${NIX_CUSTOM_CONF}; AArch64 builds unavailable."
    return 1
  }
  _aarch64_log "Added '${line}' to ${NIX_CUSTOM_CONF}."
}

ensure_aarch64_emulation() {
  ensure_aarch64_binfmt && ensure_nix_aarch64_platform
}
