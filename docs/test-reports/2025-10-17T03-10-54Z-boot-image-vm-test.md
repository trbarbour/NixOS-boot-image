# 2025-10-17T03:10:54Z boot-image VM pytest run

- Command: `nix develop .#bootImageTest -c env TMPDIR=/tmp pytest tests/test_boot_image_vm.py -vv`
- Result: **FAILED** - both VM cases now reach `STATE=applied`, but post-provisioning checks fail.

## Failure summary
- `test_boot_image_provisions_clean_disk`
  - `/run/pre-nixos/storage-status` reports `STATE=applied`/`DETAIL=auto-applied`, indicating the storage plan succeeded.
  - The follow-up `vgs --noheadings --separator '|' -o vg_name` probe runs as the unprivileged `nixos` user and returns LVM lock permission errors, so the parsed output lacks the expected `main` VG name.
- `test_boot_image_configures_network`
  - Networking succeeds (`lan` acquires `10.0.2.15/24`), and `systemctl is-active pre-nixos` eventually prints `inactive`.
  - The captured command output still includes the buffered `ip -o -4 addr` output, so the assertion receives the wrong string.

## Artefacts
- Harness + serial logs copied to `docs/work-notes/2025-10-17T03-20-16Z-boot-image-vm-regression/`.
