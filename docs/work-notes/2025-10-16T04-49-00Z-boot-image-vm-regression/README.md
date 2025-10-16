# 2025-10-16T04:49:00Z boot-image VM regression

## Overview
- Command: `nix develop .#bootImageTest -c env TMPDIR=/tmp pytest tests/test_boot_image_vm.py -vv`
- Result: Both VM tests failed after provisioning aborted inside `pre-nixos.service`.
- Boot image: `/nix/store/31i46f1cgfjcqydqcb33yw3nbvwkm80r-nixos-24.05.20241230.b134951-x86_64-linux.iso` (deriver `/nix/store/hh7kq7az10qjm2wkpp1wh6b1np8ffz8r-nixos-24.05.20241230.b134951-x86_64-linux.iso.drv`).

## Findings
- `pre_nixos.apply` invoked `disko --mode destroy,format,mount --yes-wipe-all-disks --root-mountpoint /mnt /var/log/pre-nixos/disko-config.nix`.
- `disko` exited 1 complaining `The option 'disko.devices.disk.vda.content.partitions.vda1.content.label' does not exist`, leaving `/run/pre-nixos/storage-status` stuck at `STATE=failed`/`DETAIL=auto-applied`.
- Networking succeeded (`lan` received `10.0.2.15/24` and `systemctl reload-or-restart --no-block sshd` returned 0), but `systemctl is-active pre-nixos` stayed `failed` because the storage command aborted.

## Artefacts
- `harness.log` - pytest harness transcript.
- `serial.log` - QEMU serial console capture.
