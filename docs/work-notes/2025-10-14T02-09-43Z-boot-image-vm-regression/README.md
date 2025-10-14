# 2025-10-14T02-09-43Z boot-image VM regression

## Commands
- `nix build .#bootImage`
- `pytest tests/test_boot_image_vm.py -vv`

## Result
- `nix build .#bootImage` completed and produced `/nix/store/jrcayxlgnd4va45sjcqv692k8ynlr61n-nixos-24.05.20241230.b134951-x86_64-linux.iso`.
- The VM regression failed after ~10 minutes:
  - `pre-nixos.service` wrote `/run/pre-nixos/storage-status` with `STATE=failed`/`DETAIL=auto-applied` and exited with `CalledProcessError` while running `disko --yes-wipe-all-disks --mode destroy,format,mount --root-mountpoint /mnt /var/log/pre-nixos/disko-config.nix`.
  - `systemctl is-active pre-nixos` inside the guest returned the buffered IPv4 output instead of `inactive`, so the network assertion also failed.

## Artefacts
- `harness.log` – harness interaction transcript
- `serial.log` – guest serial console, including the `disko` usage output and traceback
