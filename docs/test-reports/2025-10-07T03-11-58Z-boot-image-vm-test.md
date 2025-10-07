# Boot image VM regression test

- **Timestamp:** 2025-10-07T03:11:58Z
- **Command:** `pytest tests/test_boot_image_vm.py`
- **Result:** Failed (2 failures)

## Observations

- The login handshake now proceeds past the auto-login banner. The serial log shows the new ANSI-aware prompt matcher accepting the coloured `[nixos@nixos:~]$` shell without timing out.
- After logging in, every `command -v` probe reported `OK` even though the aggregated check still flagged the utilities as missing. Inspecting the raw output reveals bracketed paste toggles wrapping the responses (for example `\x1b[?2004l`), which `BootImageVM.run` currently leaves intact.
- `pre-nixos` continues to emit `Storage detection encountered an error; provisioning ran in plan-only mode.` leading to `disko`, `findmnt`, `lsblk`, and `wipefs` reporting as unavailable. Networking likewise never acquired an IPv4 lease on `lan`.

## Failures

1. `test_boot_image_provisions_clean_disk`
   - `assert_commands_available` raised because `disko`, `findmnt`, `lsblk`, and `wipefs` reported as `MISSING`.
2. `test_boot_image_configures_network`
   - Timed out waiting for IPv4 address on `lan`.

## Artifacts

- Serial console capture: `docs/boot-logs/2025-10-07T03-11-58Z-serial.log`
