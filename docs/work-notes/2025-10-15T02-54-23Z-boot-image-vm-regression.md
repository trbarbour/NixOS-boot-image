# 2025-10-15T02:54:23Z Boot image VM regression run

## Summary
- Rebuilt the boot ISO with `nix build .#bootImage`; `result` now points to `/nix/store/8hc5dz30wqkw6xjznq5978d9a3p9bd0s-nixos-24.05.20241230.b134951-x86_64-linux.iso`.
- Executed `TMPDIR=/tmp nix develop .#bootImageTest -c pytest tests/test_boot_image_vm.py -vv`; both VM tests ran to completion but failed because `pre-nixos.service` exited 1 after `disko --mode disko` could not import `nixpkgs`.
- Captured harness and serial logs under `docs/work-notes/2025-10-15T02-54-23Z-boot-image-vm-regression/` for comparison against earlier runs.

## Command log
```shell
nix build .#bootImage
readlink -f result

time nix develop .#bootImageTest -c env TMPDIR=/tmp pytest tests/test_boot_image_vm.py -vv
```

## Observations
- `/run/pre-nixos/storage-status` never advanced past `STATE=failed`/`DETAIL=auto-applied` even after the storage commands reported success.
- The serial console records `disko --mode disko --root-mountpoint /mnt /var/log/pre-nixos/disko-config.nix` exiting with `error: file 'nixpkgs' was not found in the Nix search path`, triggering a `CalledProcessError` inside `pre_nixos.apply`.
- Networking came up (`lan` received `10.0.2.15/24`), but `systemctl is-active pre-nixos` echoed the cached IPv4 output because the service remained in a failed state, preventing SSH validation.

## Next steps
- Ensure the `pre-nixos` unit sets `NIX_PATH` (or embeds the nixpkgs location) so `disko` can locate its libraries when invoked inside the boot ISO.
- Re-run the VM regression after adjusting the environment to confirm storage provisioning and SSH complete successfully.
- Once the storage failure is resolved, re-verify that `systemctl is-active pre-nixos` returns `inactive` and that the harness can proceed with SSH checks.
