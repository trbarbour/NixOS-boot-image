# Boot image pre-build log (2025-10-11T04:10:39Z)

## Context
- Task queue item: Pre-build boot image before VM regressions.
- Goal: Regenerate the boot image derivation and capture the resulting store path plus completion timestamp for reuse in upcoming VM tests.

## Command
```bash
nix build .#bootImage --impure --print-out-paths
```

## Result
- Store path: `/nix/store/d8xvgbl51svz0axi2n0xzrij330hw6i4-nixos-24.05.20241230.b134951-x86_64-linux.iso`
- Completion (UTC): 2025-10-11T04:10:39Z
- Notes: This run reused many cached dependencies but still spent significant time generating the ISO squashfs image. Future pytest sessions can reference the recorded derivation directly unless code changes invalidate it.

## Next steps
- Proceed to task queue item 2 by rerunning the VM regression against the freshly built ISO.
- If a rebuild is required, add a new log entry with the updated derivation path and timing.
