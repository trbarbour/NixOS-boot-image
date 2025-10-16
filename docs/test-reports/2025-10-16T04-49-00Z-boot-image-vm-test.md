# 2025-10-16T04:49:00Z boot-image VM pytest run

- Command: `nix develop .#bootImageTest -c env TMPDIR=/tmp pytest tests/test_boot_image_vm.py -vv`
- Result: **FAILED** - both VM cases aborted after `pre-nixos.service` hit the disko label assertion.

## Failure summary
- `test_boot_image_provisions_clean_disk`
  - `/run/pre-nixos/storage-status` stayed `STATE=failed`/`DETAIL=auto-applied` after `disko --mode destroy,format,mount --yes-wipe-all-disks --root-mountpoint /mnt /var/log/pre-nixos/disko-config.nix` exited 1.
  - `journalctl -u pre-nixos.service -b` shows `error: The option 'disko.devices.disk.vda.content.partitions.vda1.content.label' does not exist` from the embedded disko (version 1.12.0-dirty).
- `test_boot_image_configures_network`
  - `lan` acquired `10.0.2.15/24`, but `systemctl is-active pre-nixos` returned `failed` because storage provisioning never completed, so the test saw buffered `systemctl` output instead of `inactive`.

## Artefacts
- Harness + serial logs copied to `docs/work-notes/2025-10-16T04-49-00Z-boot-image-vm-regression/`.
