# Minix Z350 boot-console investigation (2026-04-24T10:58:47Z)

## Context
- User reported boot appearing to hang at `efi stub: measured initrd data into pcr 9` on a Minix Z350 (Intel N350, no serial port).

## Hypothesis
- The pre-installer image set `console=ttyS0,115200n8` as the final console kernel parameter, which can make `/dev/console` serial-first and hide subsequent output on display-only systems.

## Actions
- Reordered kernel parameters in `modules/pre-nixos.nix` to put serial first and `tty0` last.
- Added a regression test to lock the ordering and avoid future regressions.
- Bumped patch version from `0.8.2` to `0.8.3` for this bug fix.

## Expected result
- Boot progress remains visible on the local display for systems without serial ports while preserving serial logs on systems with serial console access.
