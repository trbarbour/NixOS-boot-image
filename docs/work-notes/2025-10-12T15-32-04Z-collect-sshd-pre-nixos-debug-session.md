# 2025-10-12T15:32:04Z – sshd/pre-nixos debug collector status

## Context
- Script under test: `scripts/collect_sshd_pre_nixos_debug.py` (latest revision hardens SSH key reuse, preserves serial/harness logs, and captures failure metadata).
- Goal: Capture the observable behaviour after the latest adjustments so future runs know what to expect.

## Commands executed
1. `python -m compileall scripts/collect_sshd_pre_nixos_debug.py`

## Outputs
- `python -m compileall scripts/collect_sshd_pre_nixos_debug.py`
  - Result: `Compiling 'scripts/collect_sshd_pre_nixos_debug.py'...`
  - Exit status: 0

## Conclusions
- The module byte-compiles successfully, which sanity-checks the refactored CLI and helper imports.
- Full end-to-end execution (building the ISO and running the VM harness) was not re-run in this session because it requires a long-lived QEMU instance and nix build cache; when scheduled, point the collector at a prepared public key via `--public-key` to avoid unnecessary rebuilds.
- All logs/metadata will land under the requested `--output-dir` even if BootImageVM hangs; verify the preserved `metadata.json`, `serial.log`, and `harness.log` after the next field run to confirm.
