# Installed system console-order follow-up (2026-04-25T01:56:44Z)

## Context
- User report: the Minix Z350 can install NixOS from the boot image, but the installed system later appears to stall at `efi stub: measured initrd data into pcr 9` with no display output.
- Prior fix only changed the pre-installer module (`modules/pre-nixos.nix`) so `tty0` is the final `console=` target.

## Investigation
- Checked the auto-install configuration generator in `pre_nixos/install.py`.
- Found generated installed-system config still emitted `boot.kernelParams = [ "console=tty0" "console=ttyS0,115200n8" ];`, making serial the final console parameter.
- Confirmed unit coverage in `tests/test_install.py` asserted that old ordering, so the regression could persist unnoticed for installed systems.

## Changes
- Reordered generated installed-system kernel params to `"console=ttyS0,115200n8" "console=tty0"` so display console remains primary while preserving serial logs.
- Updated installation test assertions to enforce the corrected ordering and added explicit index checks.
- Bumped patch version from `0.8.3` to `0.8.4`.

## Validation
- Ran: `pytest tests/test_install.py -q`.
- Result: pass.
