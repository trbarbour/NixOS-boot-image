# Boot image VM regression - 2025-10-15T02:54:23Z

## Environment
- Command: `TMPDIR=/tmp nix develop .#bootImageTest -c pytest tests/test_boot_image_vm.py -vv`
- Host nix version: 2.32.1 (`nix --version`)
- Devshell nix version: `/nix/store/l9xhiy5wqs3cflxsfhxk0isbjv96rhd1-nix-2.18.8/bin/nix`
- Boot ISO: `/nix/store/8hc5dz30wqkw6xjznq5978d9a3p9bd0s-nixos-24.05.20241230.b134951-x86_64-linux.iso`

## Result
| Test | Status | Notes |
| --- | --- | --- |
| `test_boot_image_provisions_clean_disk` | ❌ Fail | `disko --mode disko --root-mountpoint /mnt /var/log/pre-nixos/disko-config.nix` exited 1 because `nixpkgs` was missing from the search path, leaving `/run/pre-nixos/storage-status` at `STATE=failed`/`DETAIL=auto-applied`. |
| `test_boot_image_configures_network` | ❌ Fail | LAN obtained `10.0.2.15/24`, but `systemctl is-active pre-nixos` returned the same IPv4 output because the service never recovered from the `disko` failure, so SSH validation never ran. |

Pytest completed in ~12m49s (`769.44s`). Harness and serial logs copied to `docs/work-notes/2025-10-15T02-54-23Z-boot-image-vm-regression/`.

## Follow-up
- Investigate why `disko` inside the boot ISO cannot locate `nixpkgs` when invoked via `pre-nixos.apply`, despite succeeding during unit coverage. Ensure the service sets `NIX_PATH` or uses absolute `nixpkgs` references before retrying the VM regression.
- Confirm the fallback to `--mode disko` propagates the correct environment into the VM so `disko` can import its `cli.nix` without hitting the missing `nixpkgs` error.
