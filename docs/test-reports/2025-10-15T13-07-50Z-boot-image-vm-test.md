# 2025-10-15T13:07:50Z boot-image VM pytest run

- Command: `nix develop .#bootImageTest -c env TMPDIR=/tmp pytest tests/test_boot_image_vm.py -vv`
- Result: **FAILED** - both VM cases failed after provisioning errors.

## Failure summary
- `test_boot_image_provisions_clean_disk`
  - `/run/pre-nixos/storage-status` remained `STATE=failed`/`DETAIL=auto-applied`.
  - `journalctl -u pre-nixos.service -b` shows `disko` raising `error: The option 'disko.devices.disk.vda.content.partitions.vda1.content.label' does not exist` when applying the generated plan.
- `test_boot_image_configures_network`
  - `lan` obtained `10.0.2.15/24`, but `systemctl is-active pre-nixos` never reached `inactive` because storage provisioning failed, so the assertion expected `inactive` but received the buffered `ip -o -4 addr` output.

## Artefacts
- Harness + serial logs copied to `docs/work-notes/2025-10-15T13-07-50Z-boot-image-vm-regression/`.
