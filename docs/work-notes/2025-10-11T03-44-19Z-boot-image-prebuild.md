# Boot image pre-build log (2025-10-11T03:44:19Z)

## Context
- Task queue item: Pre-build boot image before VM regressions.
- Goal: Materialize the boot image derivation ahead of pytest runs and capture the resulting store path plus build timing.

## Command
```bash
nix build .#bootImage --impure --print-out-paths
```

## Result
- Store path: `/nix/store/4iyqq7b17l7pnpmwrpzcwhspdbybqfmf-nixos-24.05.20241230.b134951-x86_64-linux.iso`
- Completion (UTC): 2025-10-11T03:44:19Z
- Notes: First invocation on this host required fetching all dependencies from cache; allow ~35 minutes for cold builds. Subsequent test runs can reuse the above ISO unless code changes touch the boot image closure.

## Next steps
- Use the recorded derivation when rerunning `pytest tests/test_boot_image_vm.py` to avoid rebuild latency.
- If the closure changes, append a new log entry with the updated store path and timing.
