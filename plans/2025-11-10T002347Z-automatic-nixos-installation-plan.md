# Automatic NixOS Installation Feature Plan (2025-11-10T00:23:47Z UTC)

## Context
- Branch: `codex/add-automatic-nixos-installation-feature`
- Goal: Restore passing boot-image VM tests by fixing automatic installation workflow.

## Task Checklist
- [x] Investigate current mount detection logic and identify incorrect assumption about `/mnt/etc`.
- [x] Fix mount detection to avoid premature reliance on `/mnt/etc`.
- [x] Audit required tooling for the NixOS install process; ensure missing tools are provided.
- [x] Run boot-image VM test to reproduce failure and validate fixes. (Result: service timed out; follow-up required.)
- [x] Document findings, updates, and test outcomes in repository notes or code comments as appropriate.
- [x] Verify automatic NixOS installation succeeds on real hardware (sandbox download restrictions were the root cause of earlier failures).
- [x] Announce automatic installation start/completion across all consoles for operator visibility.
- [x] Trigger a reboot after successful installation to finish provisioning.
- [x] Stamp the freshly installed system's `/etc/issue` with the installation timestamp for post-boot verification.

## Notes
- Record each major finding with UTC timestamps in subsequent update commits.
- Keep commits focused per logical change to aid bisecting.
