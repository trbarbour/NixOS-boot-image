# Boot Image VM Test - 2025-10-08T13:51:16Z

- **Command:** `pytest tests/test_boot_image_vm.py`
- **Result:** FAILURE (2 failing tests)
- **Boot image:** `/nix/store/f8sfxra0rcp60cq2mv5cs9kigndx6ska-nixos-24.05.20241230.b134951-x86_64-linux.iso/iso/nixos-24.05.20241230.b134951-x86_64-linux.iso`
- **Embedded root key:** `/tmp/pytest-of-root/pytest-0/boot-image-ssh-key0/id_ed25519.pub`
- **Serial log:** [`docs/boot-logs/2025-10-08T13-51-16Z-serial.log`](../boot-logs/2025-10-08T13-51-16Z-serial.log)
- **pre-nixos journal:** [`docs/boot-logs/2025-10-08T13-56-18Z-pre-nixos-journal.log`](../boot-logs/2025-10-08T13-56-18Z-pre-nixos-journal.log)

## Failure summary

1. `test_boot_image_provisions_clean_disk`
   - The harness reported `disko`, `lsblk`, and `wipefs` as missing even though later probe attempts in the serial log returned `OK`. The first `command -v` invocation appears to run before the prompt is reconfigured, causing the assertion to fail immediately.
   - `pre-nixos.service` crashed with `OSError: [Errno 22] Invalid argument` while reading the NIC carrier file during `identify_lan`. See the captured journal for the full stack trace.

2. `test_boot_image_configures_network`
   - Timed out after repeatedly polling `ip -o -4 addr show dev lan`; no IPv4 address was assigned within 240 seconds.
   - Because `pre-nixos` aborted, SSH verification never executed.

## Observations

- The new journal capture confirms `_systemctl(..., ignore_missing=True)` succeeded in starting `pre-nixos.service`, but the service failed when the kernel exposed an unreadable `/sys/class/net/*/carrier` entry.
- The failure mode is consistent with the provisioning/network regression tracked in earlier runs; the additional stack trace narrows the root cause to carrier detection when the virtual NIC lacks link state.

## Next steps

- Update the provisioning harness to retry `command -v` checks after the prompt stabilises so that transient shell state does not trigger false negatives.
- Harden `pre_nixos.network.identify_lan` against `OSError` when reading `carrier` and fall back to interface enumeration.
- Investigate why the virtio NIC reports an invalid carrier value and whether the qemu invocation needs `link=on` or `multifd=on` adjustments.
- Re-run `pytest tests/test_boot_image_vm.py` after addressing the carrier exception to confirm IPv4 configuration succeeds and SSH login passes.
