# Boot Image VM Test - 2025-10-09T01:32:01Z

- **Command:** `pytest tests/test_boot_image_vm.py`
- **Result:** FAILURE (2 failing tests)
- **Boot image:** `/nix/store/82b1vxxhzq5mjm9f6vbmmxb18z7kh1s9-nixos-24.05.20241230.b134951-x86_64-linux.iso/iso/nixos-24.05.20241230.b134951-x86_64-linux.iso`
- **Embedded root key:** `/tmp/pytest-of-root/pytest-5/boot-image-ssh-key0/id_ed25519.pub`
- **Serial log:** [`docs/boot-logs/2025-10-09T01-32-01Z-serial.log`](../boot-logs/2025-10-09T01-32-01Z-serial.log)

## Failure summary

1. `test_boot_image_provisions_clean_disk`
   - The updated `assert_commands_available` now reports `OK` for `disko`, `findmnt`, `lsblk`, and `wipefs`, confirming the prompt race is resolved.
   - Provisioning timed out after 420 seconds because `/run/pre-nixos/storage-status` never gained `STATE`/`DETAIL` entries; `pre-nixos` remained running instead of exiting.

2. `test_boot_image_configures_network`
   - The LAN rename and DHCP configuration still failed to produce an IPv4 lease on `lan`, so the polling loop exhausted its 240-second timeout.
   - `identify_lan` tolerated repeated `EINVAL` reads from `/sys/class/net/*/carrier`, falling back to `operstate`, so the crash from previous runs no longer occurs.

## Observations

- Serial logs show each `command -v` probe returning `OK`, validating the command-availability retries.
- Despite the carrier guard, `pre-nixos` does not advance to writing storage status or configuring DHCP; additional diagnostics (e.g. `journalctl -u pre-nixos.service`) are still required.

## Next steps

- Capture the `pre-nixos` journal from the next run to understand why storage provisioning stalls after interface detection.
- Investigate whether the virtio NIC requires additional configuration (e.g. ensuring `systemd-networkd` is active) so DHCP can complete.
- Once provisioning/networking issues are resolved, rerun `pytest tests/test_boot_image_vm.py` to confirm the regression is fixed.
