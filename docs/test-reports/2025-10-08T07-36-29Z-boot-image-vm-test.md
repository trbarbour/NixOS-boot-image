# Boot Image VM Test - 2025-10-08T07:36:29Z

- **Command:** `pytest tests/test_boot_image_vm.py`
- **Result:** FAILURE (2 failing tests)
- **Boot image:** `/nix/store/4hsa8bvg3d073am0pp9ajv056rhqsfr4-nixos-24.05.20241230.b134951-x86_64-linux.iso/iso/nixos-24.05.20241230.b134951-x86_64-linux.iso`
- **Embedded root key:** `/tmp/pytest-of-root/pytest-4/boot-image-ssh-key0/id_ed25519.pub`
- **Serial log:** [`docs/boot-logs/2025-10-08T07-36-29Z-serial.log`](../boot-logs/2025-10-08T07-36-29Z-serial.log)

## Failure summary

1. `test_boot_image_provisions_clean_disk`
   - `command -v` checks for `disko`, `lsblk`, and `wipefs` reported `MISSING` even though the ISO should include these tools.
   - `pre-nixos.service` exited with `status=1` before the test reached provisioning assertions.

2. `test_boot_image_configures_network`
   - Timed out waiting for an IPv4 address on `lan` after 240 seconds.
   - SSH login could not be validated because the service never configured networking.

The serial console captured `pre-nixos: Provisioning failed` immediately after boot. Unlike the previous log (2025-10-08T06-10-00Z) no journal snippet was collected automatically; a follow-up run should scrape `journalctl -u pre-nixos.service` to confirm whether the new `_systemctl(..., ignore_missing=True)` helper is in use and why networking still fails to converge.

## Next steps

- Instrument the VM harness to record the resolved store path and copy `journalctl -u pre-nixos.service` on failure.
- Confirm that the boot image build actually embeds the freshly generated root key and the updated `pre_nixos/network.py` logic.
- Re-run the VM tests once diagnostics confirm the ISO refresh.
