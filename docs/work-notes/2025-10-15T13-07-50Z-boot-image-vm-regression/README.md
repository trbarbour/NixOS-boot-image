# 2025-10-15T13:07:50Z boot-image VM regression

## Overview
- Command: `nix develop .#bootImageTest -c env TMPDIR=/tmp pytest tests/test_boot_image_vm.py -vv`
- Result: Both VM tests failed after booting the fresh ISO.
- Boot image: `/nix/store/p6rvp4xb98zqj8z0dkk99sz5hw3q4rpk-nixos-24.05.20241230.b134951-x86_64-linux.iso` (deriver `/nix/store/1xzfpw97p5qqnzdwd0bjk5wxji752bly-nixos-24.05.20241230.b134951-x86_64-linux.iso.drv`).

## Findings
- `pre-nixos.apply` invoked `disko --mode disko --root-mountpoint /mnt /var/log/pre-nixos/disko-config.nix`.
- `disko` aborted with `error: The option \`disko.devices.disk.vda.content.partitions.vda1.content.label' does not exist`, returning status 1 and leaving `/run/pre-nixos/storage-status` at `STATE=failed`/`DETAIL=auto-applied`.
- Networking configured successfully (`lan` acquired `10.0.2.15/24`), but `systemctl is-active pre-nixos` never reached `inactive` because storage provisioning failed.

## Artefacts
- `harness.log` - pytest harness transcript
- `serial.log` - QEMU serial console capture
