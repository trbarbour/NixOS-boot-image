# Boot image VM regression test

- **Timestamp:** 2025-10-08T00:41:32Z
- **Command:** `pytest tests/test_boot_image_vm.py`
- **Result:** Failed (2 failures, 1000.26s wall clock)

## Observations

- `pre-nixos` exited early with `Provisioning failed`, so the boot image never provisioned the blank disk. The command check fixture subsequently reported `disko`, `lsblk`, and `wipefs` as missing because `command -v` ran in the unprovisioned environment and the tooling never became available.
- Networking also stalled; repeated `ip -o -4 addr show dev lan` probes never returned an address and the serial log contains no `configure_lan` progress messages, suggesting the LAN rename/DHCP configuration still bails out.
- The VM shut down only after the harness attempted to power off; QEMU remained at the login prompt with the custom `PRE-NIXOS>` shell prompt active throughout.

## Failures

1. `test_boot_image_provisions_clean_disk`
   - `assert_commands_available` raised `AssertionError: required commands missing from boot image: disko, lsblk, wipefs`.
2. `test_boot_image_configures_network`
   - `wait_for_ipv4` timed out after 240 seconds waiting for an address on `lan`.

## Artifacts

- Serial console capture: `docs/boot-logs/2025-10-08T00-41-32Z-serial.log`
