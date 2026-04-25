# Console policy alignment for booted and installed systems

## Context
- UTC timestamp: 2026-04-25 20:37:02Z
- Request: keep GRUB serial support available, include serial in kernel params by default without making it primary, and carry the boot-image console arrangement into the installed system.

## Actions
1. Reviewed `modules/pre-nixos.nix` and confirmed GRUB serial support is already always enabled via `boot.loader.grub.extraConfig`.
2. Updated `pre_nixos/install.py` so installed-system `boot.kernelParams` are now chosen from boot-time `/proc/cmdline` ordering:
   - default/normal path keeps `console=ttyS0,115200n8` before `console=tty0`.
   - explicit serial-priority selection (serial as last boot console) results in `console=tty0` before `console=ttyS0,115200n8`.
3. Added install tests for:
   - default display-primary fallback,
   - explicit serial-primary selection,
   - generated configuration content when serial is primary.
4. Bumped patch version from `0.8.7` to `0.8.8`.

## Validation
- Ran `pytest tests/test_install.py -q`.
- Result: pass.
