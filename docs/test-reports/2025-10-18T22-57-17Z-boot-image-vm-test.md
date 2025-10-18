# 2025-10-18T22:57:17Z Boot Image VM Regression

## Summary
- Rebuilt the boot image with the test harness provisioning a temporary SSH key and ran the full VM regression suite via `pytest tests/test_boot_image_vm.py -vv`.
- Verified storage provisioning reached `STATE=applied`/`DETAIL=auto-applied`, LVM metadata was readable as root, and `pre-nixos.service` settled to `inactive`.
- Confirmed the guest obtained an IPv4 lease on `lan` and accepted root SSH logins using the generated key.

## Environment
- Repository revision: 9e0c21d82762 (dirty working tree with pending harness fixes)
- Command: `nix develop .#bootImageTest -c pytest tests/test_boot_image_vm.py -vv`
- Duration: 948.55s
- ISO store path: `/nix/store/dc8zlqkvcwm37pswkc7scqzm42nlc810-nixos-24.05.20241230.b134951-x86_64-linux.iso/iso/nixos-24.05.20241230.b134951-x86_64-linux.iso`
- Embedded root key fingerprint: `256 SHA256:Ts/sz8ENaPvHP6iRxI03b31OrsQ3qDxTKwuG4Yi3B6E boot-image-vm-test (ED25519)`

## Observations
- `/run/pre-nixos/storage-status` reported `STATE=applied` and `DETAIL=auto-applied` before post-provisioning checks were executed.
- `vgs --noheadings --separator '|' -o vg_name` and `lvs --noheadings --separator '|' -o lv_name,vg_name` both returned the expected `main` volume group and `slash|main` logical volume without LVM permission errors.
- `systemctl is-active pre-nixos` transitioned to `inactive` immediately after the IPv4 lease was detected, and the SSH identity check returned `root`.

## Artifacts
- Harness log: `docs/work-notes/2025-10-18T22-57-17Z-boot-image-vm-regression/harness.log`
- Serial log: `docs/work-notes/2025-10-18T22-57-17Z-boot-image-vm-regression/serial.log`
