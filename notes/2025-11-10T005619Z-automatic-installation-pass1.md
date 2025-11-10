# Automatic NixOS Installation - Pass 1 (2025-11-10T00:56:19Z UTC)

## Summary
- Updated the auto-install mount readiness check to rely on mountpoints instead of `/mnt/etc` while retaining pytest compatibility.
- Added `nix` and `nixos-install-tools` to the boot image environment packages and service PATH to supply the executables required by `nixos-install` and `nixos-generate-config`.
- Escaped `${auto_install_state}` references inside the pre-nixos service script to keep Nix string interpolation from breaking the shell parameter expansion.

## Testing
- `pytest tests/test_install.py`
- `pytest tests/test_boot_image_vm.py`

## Results
- Unit tests passed.
- Boot image VM suite failed: `pre-nixos` service never reached the inactive state (timeout after 180 s) and the harness could not observe a storage status update. Logs show `nixos-install` running for several minutes and repeated attempts to download the Nix channel, suggesting the install is blocked on fetching substitutes or completing the build. Follow-up work must investigate why the installation does not finish within the expected window.

## Next Steps
- Examine `nixos-install` invocation behaviour inside the VM, ensuring substitutes are available or unnecessary tasks are disabled so the install can complete promptly.
- Audit the `pre-nixos` journal for earlier Python module import errors (notably `pre_nixos.console`) to confirm they are benign or require packaging adjustments.
